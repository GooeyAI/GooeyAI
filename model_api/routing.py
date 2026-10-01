import litellm

# The Model Provider Gooey serves each family of models through. A family that
# isn't listed isn't served, since Gooey holds no credentials for it.
# TODO: anthropic and gemini families (providers PR)
MODEL_PROVIDERS = {
    "openai": "openai",
}

# Native IDs LiteLLM can't resolve on its own, e.g. Cursor custom model names.
MODEL_ALIASES: dict[str, str] = {}

# Routes that speak one provider's protocol fix the family, whatever the ID.
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
    family = CALL_TYPE_FAMILIES.get(call_type)
    if family:
        model = model.removeprefix(f"{family}/")
    else:
        family, model = infer_family(model)

    provider = MODEL_PROVIDERS.get(family)
    if not provider:
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
