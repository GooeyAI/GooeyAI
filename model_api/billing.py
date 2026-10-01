import json
import math
import uuid
from datetime import timedelta
from decimal import Decimal

import litellm
import sentry_sdk
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import InsufficientCredits, UserError
from model_api.models import ModelApiCall
from payments import credits
from workspaces.models import Workspace, WorkspaceMembership

OPEN_STATUSES = (ModelApiCall.Status.RESERVED, ModelApiCall.Status.SETTLING)

# request fields that make up the prompt, across the Proxy's protocols
PROMPT_FIELDS = (
    "messages",
    "input",
    "instructions",
    "system",
    "contents",
    "systemInstruction",
    "tools",
)
MAX_OUTPUT_FIELDS = ("max_tokens", "max_completion_tokens", "max_output_tokens")


def reserve(
    *,
    workspace_id: int,
    user_id: int,
    api_key_id: int | None,
    model: str,
    litellm_model: str,
    call_type: str,
    request_data: dict,
) -> ModelApiCall:
    """
    Reserve a call's worst-case cost before it runs, and return its ledger row.

    Raises InsufficientCredits when the balance, less what other open calls have
    reserved, can't cover it within MODEL_API_OVERDRAFT_LIMIT_CREDITS (after one
    auto-recharge attempt).
    """
    workspace = Workspace.objects.get(id=workspace_id)
    user = AppUser.objects.get(id=user_id)
    estimate = credits_for_cost(estimate_cost_usd(litellm_model, request_data))
    overdraft = settings.MODEL_API_OVERDRAFT_LIMIT_CREDITS

    owner = credits.get_balance_owner(workspace, user)
    if owner is None:
        raise UserError(credits.TEAM_MEMBER_MISSING_ERROR)
    needed = estimate + open_reserved_credits(owner) - overdraft
    for _ in credits.ensure_credits_and_auto_recharge(workspace, user, needed):
        pass

    with transaction.atomic():
        # serialises reservations against the same balance
        owner = type(owner).objects.select_for_update().get(pk=owner.pk)
        if owner.balance + overdraft - open_reserved_credits(owner) < estimate:
            raise InsufficientCredits(price=estimate)
        return ModelApiCall.objects.create(
            call_id=str(uuid.uuid4()),
            workspace=workspace,
            user=user,
            api_key_id=api_key_id,
            model=model,
            litellm_model=litellm_model,
            call_type=call_type,
            reserved_credits=estimate,
        )


def settle(
    call_id: str, *, cost_usd: float | None, usage: dict, source: str
) -> ModelApiCall | None:
    """
    Charge a call once. `cost_usd=None` (LiteLLM couldn't price it) charges the
    reservation. A released call can still be settled, so a late partial cost
    isn't lost; a call that's already settling or settled is left alone.
    """
    with transaction.atomic():
        call = ModelApiCall.objects.select_for_update().filter(call_id=call_id).first()
        if not call:
            return None
        if call.status not in (
            ModelApiCall.Status.RESERVED,
            ModelApiCall.Status.RELEASED,
        ):
            if cost_usd is not None and call.cost_usd != Decimal(str(cost_usd)):
                sentry_sdk.capture_message(
                    f"Model API call {call_id} settled again ({source}) with cost "
                    f"{cost_usd}, already charged at {call.cost_usd}"
                )
            return call

        if cost_usd is None:
            sentry_sdk.capture_message(
                f"Model API call {call_id} ({call.litellm_model}) had no cost; "
                f"charging its reservation of {call.reserved_credits} credits"
            )
            call.charged_credits = call.reserved_credits
        else:
            call.cost_usd = Decimal(str(cost_usd))
            call.charged_credits = credits_for_cost(cost_usd)
        call.status = ModelApiCall.Status.SETTLING
        call.usage = usage
        call.settled_by = source
        call.save()

    return finish_settlement(call)


def sweep_stale() -> dict[str, list[str]]:
    """
    Close calls still open well past the request timeout, e.g. because the
    Model API process died mid-call: finish settlements that stopped before
    their deduction, and release reservations that were never settled (with a
    Sentry alert, since that usage goes uncharged).
    """
    cutoff = timezone.now() - timedelta(seconds=settings.MODEL_API_STALE_CALL_SECONDS)
    stale = ModelApiCall.objects.filter(created_at__lt=cutoff)

    finished = []
    for call in stale.filter(status=ModelApiCall.Status.SETTLING):
        finish_settlement(call)
        finished.append(call.call_id)

    released = [
        call_id
        for call_id in stale.filter(status=ModelApiCall.Status.RESERVED).values_list(
            "call_id", flat=True
        )
        if release(call_id)
    ]
    if released:
        sentry_sdk.capture_message(
            f"Model API released {len(released)} abandoned reservations "
            f"without charging: {released[:20]}"
        )
    return {"finished": finished, "released": released}


def finish_settlement(call: ModelApiCall) -> ModelApiCall:
    """
    Deduct a settling call's charge and mark it settled. The deduction is
    idempotent by invoice id, so re-running this for a call stuck in `settling`
    never charges twice.
    """
    if call.charged_credits:
        call.transaction = credits.deduct_credits(
            call.workspace,
            call.user,
            call.charged_credits,
            invoice_id=call.invoice_id,
        )
    call.status = ModelApiCall.Status.SETTLED
    call.save(update_fields=["status", "transaction", "updated_at"])
    return call


def release(call_id: str) -> bool:
    """Release a reserved call that charged nothing. Returns whether it did."""
    return bool(
        ModelApiCall.objects.filter(
            call_id=call_id, status=ModelApiCall.Status.RESERVED
        ).update(status=ModelApiCall.Status.RELEASED)
    )


def estimate_cost_usd(litellm_model: str, request_data: dict) -> float:
    """
    Worst-case cost: the counted prompt plus every output token the call may
    produce, across all `n` choices. Errs high, since the reservation must cover
    the actual charge.
    """
    prompt_tokens = count_prompt_tokens(litellm_model, request_data)
    choices = max(1, int(request_data.get("n") or 1))
    completion_tokens = max_output_tokens(litellm_model, request_data) * choices
    prompt_cost, completion_cost = litellm.cost_per_token(
        model=litellm_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return prompt_cost + completion_cost


def count_prompt_tokens(litellm_model: str, request_data: dict) -> int:
    messages = request_data.get("messages")
    if isinstance(messages, list):
        try:
            return litellm.token_counter(
                model=litellm_model, messages=messages, tools=request_data.get("tools")
            )
        except Exception:
            pass  # protocol-specific shapes fall back to counting the raw JSON
    prompt = {key: request_data[key] for key in PROMPT_FIELDS if key in request_data}
    return litellm.token_counter(
        model=litellm_model, text=json.dumps(prompt, default=str)
    )


def max_output_tokens(litellm_model: str, request_data: dict) -> int:
    for key in MAX_OUTPUT_FIELDS:
        if request_data.get(key):
            return int(request_data[key])
    generation_config = request_data.get("generationConfig") or {}
    if generation_config.get("maxOutputTokens"):
        return int(generation_config["maxOutputTokens"])
    info = litellm.get_model_info(litellm_model)
    return info.get("max_output_tokens") or info.get("max_tokens") or 0


def credits_for_cost(cost_usd: float) -> int:
    """Provider cost in credits, rounded up to the next credit (1 credit = 1 cent)."""
    if cost_usd <= 0:
        return 0
    return math.ceil(Decimal(str(cost_usd)) * settings.ADDON_CREDITS_PER_DOLLAR)


def open_reserved_credits(owner: Workspace | WorkspaceMembership) -> int:
    calls = ModelApiCall.objects.filter(status__in=OPEN_STATUSES)
    if isinstance(owner, WorkspaceMembership):
        calls = calls.filter(workspace_id=owner.workspace_id, user_id=owner.user_id)
    else:
        calls = calls.filter(workspace=owner)
    return calls.aggregate(total=Sum("reserved_credits"))["total"] or 0
