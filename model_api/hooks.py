__import__("gooeysite.wsgi")  # Note: this must always be at the top

import sentry_sdk
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import ProxyException
from starlette.concurrency import run_in_threadpool

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import InsufficientCredits, UserError
from gooeysite.bg_db_conn import db_middleware
from model_api import billing
from model_api.routing import ModelNotFound, ModelNotPriced, resolve_model
from model_api.streams import MeteredStream

USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")

# Responses fields that store a response or read one back
STATEFUL_RESPONSES_FIELDS = ("previous_response_id", "conversation", "background")


class GooeyModelAPI(CustomLogger):
    """
    LiteLLM Proxy callbacks: resolve the model and reserve credits before each
    call, then charge it exactly once from whichever callback ends it.
    """

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        native_model = data["model"]
        try:
            data["model"] = resolve_model(native_model, call_type)
        except ModelNotFound as e:
            raise proxy_error(404, "invalid_request_error", f"Model {e} not found.")
        except ModelNotPriced as e:
            raise proxy_error(
                400, "invalid_request_error", f"Model {e} is not available: no pricing."
            )
        if call_type == "aresponses":
            make_stateless(data)

        gooey = user_api_key_dict.metadata
        try:
            call = await run_db(
                billing.reserve,
                workspace_id=gooey["gooey_workspace_id"],
                user_id=gooey["gooey_user_id"],
                api_key_id=gooey["gooey_api_key_id"],
                model=native_model,
                litellm_model=data["model"],
                call_type=call_type,
                request_data=data,
            )
        except InsufficientCredits as e:
            raise proxy_error(
                402,
                "insufficient_credits",
                f"Insufficient credits: this call needs up to {e.error_params['price']} "
                f"credits. Add credits at {billing_url()}.",
            )
        except UserError as e:
            raise proxy_error(403, "permission_error", e.message.strip())

        # the Proxy forwards whichever metadata key the route uses into the
        # callbacks' litellm_params["metadata"]
        metadata_key = "litellm_metadata" if "litellm_metadata" in data else "metadata"
        data.setdefault(metadata_key, {})["gooey_call_id"] = call.call_id
        return data

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        call_id = get_gooey_call_id(kwargs)
        if not call_id:
            return
        try:
            await run_db(
                billing.settle,
                call_id,
                cost_usd=kwargs.get("response_cost"),
                usage=get_usage(kwargs),
                source="success",
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        call_id = get_gooey_call_id(kwargs)
        if not call_id:
            # e.g. a rejected key: the call never reached the pre-call hook
            return
        try:
            # a stream that broke mid-way reports its partial cost
            if kwargs.get("response_cost"):
                await run_db(
                    billing.settle,
                    call_id,
                    cost_usd=kwargs["response_cost"],
                    usage=get_usage(kwargs),
                    source="failure",
                )
            else:
                await run_db(billing.release, call_id)
        except Exception as e:
            sentry_sdk.capture_exception(e)

    async def async_post_call_failure_hook(
        self, request_data, original_exception, user_api_key_dict, traceback_str=None
    ):
        # covers failures after the reservation that never reach the logging
        # callbacks; a later partial cost still settles a released call
        call_id = get_request_call_id(request_data)
        if not call_id:
            return
        try:
            await run_db(billing.release, call_id)
        except Exception as e:
            sentry_sdk.capture_exception(e)

    async def async_post_call_streaming_iterator_hook(
        self, user_api_key_dict, response, request_data
    ):
        call_id = get_request_call_id(request_data)
        if not call_id or not hasattr(response, "aclose"):
            async for chunk in response:
                yield chunk
            return

        async def settle_incomplete(chunks: list):
            try:
                await run_db(
                    billing.settle_incomplete_stream,
                    call_id,
                    request_data=request_data,
                    chunks=chunks,
                )
            except Exception as e:
                sentry_sdk.capture_exception(e)

        stream = MeteredStream(response, on_incomplete=settle_incomplete)
        async for chunk in stream.relay():
            yield chunk


def make_stateless(data: dict):
    """
    Keep a Responses call from storing or reaching stored state. Every workspace
    shares Gooey's provider keys, so a stored response or conversation would be
    reachable from any workspace that learned its ID.
    """
    for field in STATEFUL_RESPONSES_FIELDS:
        if data.get(field):
            raise proxy_error(
                400,
                "invalid_request_error",
                f"`{field}` isn't supported: send the whole conversation in `input`.",
            )
    input_items = data.get("input")
    if isinstance(input_items, list) and any(
        isinstance(item, dict) and item.get("type") == "item_reference"
        for item in input_items
    ):
        raise proxy_error(
            400,
            "invalid_request_error",
            "`item_reference` inputs aren't supported: send the items themselves.",
        )
    data["store"] = False


async def run_db(fn, *args, **kwargs):
    return await run_in_threadpool(db_middleware(fn), *args, **kwargs)


def get_gooey_call_id(kwargs: dict) -> str | None:
    metadata = (kwargs.get("litellm_params") or {}).get("metadata") or {}
    return metadata.get("gooey_call_id")


def get_request_call_id(request_data: dict) -> str | None:
    metadata = request_data.get("litellm_metadata") or request_data.get("metadata")
    return (metadata or {}).get("gooey_call_id")


def get_usage(kwargs: dict) -> dict:
    logged = kwargs.get("standard_logging_object") or {}
    return {field: logged.get(field) for field in USAGE_FIELDS}


def billing_url() -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/account/billing/"


def proxy_error(status_code: int, type_: str, message: str) -> ProxyException:
    return ProxyException(message=message, type=type_, param=None, code=status_code)


gooey_model_api = GooeyModelAPI()
