__import__("gooeysite.wsgi")  # Note: this must always be at the top

import litellm
import sentry_sdk
from asgiref.sync import sync_to_async
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import ProxyException

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import InsufficientCredits, UserError
from gooeysite.bg_db_conn import db_middleware
from payments import credits
from workspaces.models import Workspace


class GooeyBilling(CustomLogger):
    """
    LiteLLM Proxy callbacks: check the balance before each call, then deduct
    its cost once it ends.
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
        # the key's custom_auth metadata, as the Proxy logged it
        logged_metadata = kwargs["standard_logging_object"]["metadata"]
        await deduct_cost(
            logged_metadata["user_api_key_auth_metadata"], call_id, cost_usd
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
def deduct_cost(gooey: dict, call_id: str, cost_usd: float):
    """
    Deduct a call's provider cost from the key's workspace. Charging the same
    `call_id` again is a no-op; gooey_auth refuses client-set call ids.
    """
    amount = credits.credits_for_cost(cost_usd)
    if not amount:
        return
    workspace = Workspace.objects.get(id=gooey["gooey_workspace_id"])
    user = AppUser.objects.get(id=gooey["gooey_user_id"])
    credits.deduct_credits(
        workspace, user, amount, invoice_id=f"gooey_model_api_{call_id}"
    )


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
