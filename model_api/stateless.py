from litellm.proxy._types import ProxyException

# Responses fields that store a response or read one back
STATEFUL_RESPONSES_FIELDS = ("previous_response_id", "conversation", "background")


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


def proxy_error(status_code: int, type_: str, message: str) -> ProxyException:
    return ProxyException(message=message, type=type_, param=None, code=status_code)
