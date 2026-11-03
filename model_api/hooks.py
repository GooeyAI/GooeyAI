__import__("gooeysite.wsgi")  # Note: this must always be at the top

import datetime

import litellm
import sentry_sdk
from asgiref.sync import sync_to_async
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import ProxyException

from app_users.models import AppUser, AppUserTransaction
from bots.models import SavedRun, Workflow
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import InsufficientCredits, UserError
from gooeysite.bg_db_conn import db_middleware
from model_api.sessions import add_to_session
from payments import credits
from workspaces.models import Workspace


class GooeyBilling(CustomLogger):
    """
    LiteLLM Proxy callbacks: check the balance before each call, then deduct
    its cost once it ends and record it as a Model API run.
    """

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        model = data["model"]
        if not is_priced(model):
            raise proxy_error(
                400, "invalid_request_error", f"Model {model} is not available."
            )

        gooey = user_api_key_dict.metadata
        try:
            await check_credits(gooey["gooey_workspace_id"], gooey["gooey_user_id"])
        except InsufficientCredits:
            raise proxy_error(
                402,
                "insufficient_credits",
                f"Insufficient credits. Add credits at {billing_url()}.",
            )
        except UserError:
            raise proxy_error(
                403,
                "permission_error",
                "This API key's creator is no longer a member of its workspace.",
            )
        return data

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        # also fires with the partial cost when a client disconnects mid-stream
        call_id = kwargs["litellm_call_id"]
        cost_usd = kwargs.get("response_cost")
        if cost_usd is None:
            sentry_sdk.capture_message(
                f"Model API call {call_id} ({kwargs.get('model')}) had no cost "
                "and was not charged"
            )
            return
        await deduct_cost(
            kwargs["standard_logging_object"],
            call_id,
            cost_usd,
            client_session_id(kwargs),
        )


@sync_to_async(thread_sensitive=False)
@db_middleware
def check_credits(workspace_id: int, user_id: int):
    """
    Raise InsufficientCredits unless the balance is positive, after one
    auto-recharge attempt. A call's cost is only known once it ends, so it's
    deducted afterwards and may take the balance below zero.
    """
    workspace = Workspace.objects.get(id=workspace_id)
    user = AppUser.objects.get(id=user_id)
    for _ in credits.ensure_credits_and_auto_recharge(workspace, user, 1):
        pass


@sync_to_async(thread_sensitive=False)
@db_middleware
def deduct_cost(
    logged: dict, call_id: str, cost_usd: float, session_id: str | None = None
):
    """
    Deduct a call's provider cost from the key's workspace, and record the call
    as a Model API run linked to that charge, so it shows in run history and
    credit usage. Calls that share a client `session_id` are grouped into one
    history entry. Charging the same `call_id` again is a no-op; gooey_auth
    refuses client-set call ids. Calls that cost nothing get no run either.
    """
    amount = credits.credits_for_cost(cost_usd)
    if not amount:
        return
    # the key's custom_auth metadata, as the Proxy logged it
    gooey = logged["metadata"]["user_api_key_auth_metadata"]
    workspace = Workspace.objects.get(id=gooey["gooey_workspace_id"])
    user = AppUser.objects.get(id=gooey["gooey_user_id"])
    transaction = credits.deduct_credits(
        workspace, user, amount, invoice_id=f"gooey_model_api_{call_id}"
    )
    run, created = record_run(workspace, user, transaction, logged, call_id, cost_usd)
    if created and session_id:
        add_to_session(run, workspace, user, session_id)


def record_run(
    workspace: Workspace,
    user: AppUser,
    transaction: AppUserTransaction,
    logged: dict,
    call_id: str,
    cost_usd: float,
) -> tuple[SavedRun, bool]:
    """
    The call's Model API run, keyed by its call id so a repeated callback
    keeps one run. Metadata only: no prompt or response text.
    """
    metadata = logged["metadata"]
    return SavedRun.objects.get_or_create(
        run_id=call_id,
        defaults=dict(
            workflow=Workflow.MODEL_API,
            uid=user.uid,
            workspace=workspace,
            surface=SavedRun.Surface.api,
            run_time=datetime.timedelta(
                seconds=logged["endTime"] - logged["startTime"]
            ),
            price=-transaction.amount,
            transaction=transaction,
            state=dict(
                model=logged.get("model_group") or logged["model"],
                provider_model=answering_model(logged),
                route=metadata.get("user_api_key_request_route"),
                stream=bool(logged.get("stream")),
                api_key_id=metadata["user_api_key_auth_metadata"].get(
                    "gooey_api_key_id"
                ),
                user_agent=logged.get("user_agent"),
                prompt_tokens=logged.get("prompt_tokens", 0),
                completion_tokens=logged.get("completion_tokens", 0),
                total_tokens=logged.get("total_tokens", 0),
                cost_usd=cost_usd,
                started_at=logged["startTime"],
                ended_at=logged["endTime"],
                call_id=call_id,
            ),
        ),
    )


def answering_model(logged: dict) -> str:
    """
    The model named in the response, else the one the Proxy routed to,
    without its provider prefix.
    """
    response = logged.get("response")
    if isinstance(response, dict) and response.get("model"):
        return response["model"]
    return logged["model"].split("/", 1)[-1]


def client_session_id(kwargs: dict) -> str | None:
    """
    The session id the client sent (`x-session-id` and similar headers, or
    `metadata.session_id`), as the Proxy put it in the request metadata. Not
    `litellm_session_id`: that falls back to the W3C trace id, which clients
    like OpenCode reuse across sessions.
    """
    litellm_params = kwargs.get("litellm_params") or {}
    for key in ("metadata", "litellm_metadata"):
        metadata = litellm_params.get(key) or {}
        if session_id := metadata.get("session_id"):
            return str(session_id)
    return None


def is_priced(model: str) -> bool:
    """Whether LiteLLM's cost map can price the model, so it can be billed."""
    # the cost map keys OpenAI models by their bare IDs
    info = litellm.model_cost.get(model.removeprefix("openai/")) or {}
    return bool(info.get("input_cost_per_token") and info.get("output_cost_per_token"))


def billing_url() -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/account/billing/"


def proxy_error(status_code: int, type_: str, message: str) -> ProxyException:
    return ProxyException(message=message, type=type_, param=None, code=status_code)


gooey_model_api = GooeyBilling()
