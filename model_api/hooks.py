from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import ProxyException

from model_api.routing import ModelNotFound, ModelNotPriced, resolve_model


class GooeyModelAPI(CustomLogger):
    """LiteLLM Proxy callbacks: model resolution now, credits and billing next."""

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        # TODO: reserve credits before the call (billing PR)
        try:
            data["model"] = resolve_model(data["model"], call_type)
        except ModelNotFound as e:
            raise invalid_model_error(404, f"Model {e} not found.")
        except ModelNotPriced as e:
            raise invalid_model_error(400, f"Model {e} is not available: no pricing.")
        return data


def invalid_model_error(status_code: int, message: str) -> ProxyException:
    return ProxyException(
        message=message, type="invalid_request_error", param="model", code=status_code
    )


gooey_model_api = GooeyModelAPI()
