import os

import litellm

# The Model Provider Gooey serves each family of models through, and the env
# var holding its key. A family that isn't listed, or whose key isn't set,
# isn't served: without the key, the provider's 401 would read to clients as a
# bad Gooey key.
# TODO: the gemini family
MODEL_PROVIDERS = {
    "openai": ("openai", "OPENAI_API_KEY"),
    "anthropic": ("anthropic", "ANTHROPIC_API_KEY"),
}

# Native IDs LiteLLM can't resolve on its own, e.g. Cursor custom model names.
MODEL_ALIASES: dict[str, str] = {}

# Routes that speak one provider's protocol, for IDs LiteLLM can't place on
# its own. A recognisable ID from another family is bridged instead.
CALL_TYPE_FAMILIES = {
    "anthropic_messages": "anthropic",
    "agenerate_content": "gemini",
    "agenerate_content_stream": "gemini",
}


class ModelNotFound(Exception):
    pass


class ModelNotPriced(Exception):
    pass


def resolve_model(model: str, call_type: str) -> str:
    """
    Return the LiteLLM routing ID (`provider/model`) for the native model ID a
    client sent, e.g. `gpt-4.1-mini` -> `openai/gpt-4.1-mini`.

    Raises ModelNotFound when no served family claims the ID, and ModelNotPriced
    when LiteLLM's cost map has no input or output price for it (so it can't be
    billed).
    """
    model = MODEL_ALIASES.get(model, model)
    family, model = infer_family(model)
    if not family:
        family = CALL_TYPE_FAMILIES.get(call_type)

    provider, key_env = MODEL_PROVIDERS.get(family) or (None, None)
    if not provider or not os.environ.get(key_env):
        raise ModelNotFound(model)

    litellm_model = f"{provider}/{model}"
    if not is_priced(litellm_model):
        raise ModelNotPriced(model)
    return litellm_model


def infer_family(model: str) -> tuple[str | None, str]:
    try:
        bare_model, provider, _, _ = litellm.get_llm_provider(model)
    except litellm.BadRequestError:
        return None, model
    return provider, bare_model


def is_priced(litellm_model: str) -> bool:
    try:
        info = litellm.get_model_info(litellm_model)
    except Exception:
        return False
    return bool(info.get("input_cost_per_token") and info.get("output_cost_per_token"))
