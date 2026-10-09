from unittest.mock import patch

import pytest

from model_api import routing
from model_api.routing import ModelNotFound, ModelNotPriced, resolve_model


@pytest.fixture(autouse=True)
def provider_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/service-account.json")


@pytest.mark.parametrize(
    "model, call_type, expected",
    [
        ("gpt-4.1-mini", "acompletion", "openai/gpt-4.1-mini"),
        ("gpt-4.1-mini", "aresponses", "openai/gpt-4.1-mini"),
        ("openai/gpt-4.1-mini", "acompletion", "openai/gpt-4.1-mini"),
        ("o3", "acompletion", "openai/o3"),
        ("claude-sonnet-4-5", "acompletion", "anthropic/claude-sonnet-4-5"),
        ("claude-sonnet-4-5", "anthropic_messages", "anthropic/claude-sonnet-4-5"),
        (
            "anthropic/claude-sonnet-4-5",
            "anthropic_messages",
            "anthropic/claude-sonnet-4-5",
        ),
        ("gemini-2.5-pro", "acompletion", "vertex_ai/gemini-2.5-pro"),
        ("gemini-2.5-pro", "agenerate_content", "vertex_ai/gemini-2.5-pro"),
        ("gemini/gemini-2.5-pro", "acompletion", "vertex_ai/gemini-2.5-pro"),
        # a recognisable ID on another family's route is bridged, not misrouted
        ("gpt-4.1-mini", "anthropic_messages", "openai/gpt-4.1-mini"),
        ("gpt-4.1-mini", "agenerate_content", "openai/gpt-4.1-mini"),
    ],
)
def test_resolves_native_ids(model, call_type, expected):
    assert resolve_model(model, call_type) == expected


@pytest.mark.parametrize(
    "model, call_type",
    [
        ("not-a-real-model", "acompletion"),
        # a family Gooey doesn't serve
        ("mistral/mistral-large-latest", "acompletion"),
    ],
)
def test_unserved_ids_are_not_found(model, call_type):
    with pytest.raises(ModelNotFound):
        resolve_model(model, call_type)


def test_families_without_a_key_are_not_served(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS")
    with pytest.raises(ModelNotFound):
        resolve_model("claude-sonnet-4-5", "anthropic_messages")
    with pytest.raises(ModelNotFound):
        resolve_model("gemini-2.5-pro", "agenerate_content")
    assert resolve_model("gpt-4.1-mini", "acompletion") == "openai/gpt-4.1-mini"


def test_the_route_places_ids_litellm_cannot():
    # unknown to LiteLLM, so the Messages route picks the family; with no
    # price for it, it's refused rather than misrouted
    with pytest.raises(ModelNotPriced):
        resolve_model("claude-from-the-future", "anthropic_messages")
    with pytest.raises(ModelNotFound):
        resolve_model("claude-from-the-future", "acompletion")


def test_aliases_resolve_before_inference():
    with patch.dict(routing.MODEL_ALIASES, {"gooey-mini": "gpt-4.1-mini"}):
        assert resolve_model("gooey-mini", "acompletion") == "openai/gpt-4.1-mini"


def test_unpriced_models_are_refused():
    unpriced = {"input_cost_per_token": 0, "output_cost_per_token": 1e-06}
    with patch.object(routing.litellm, "get_model_info", return_value=unpriced):
        with pytest.raises(ModelNotPriced):
            resolve_model("gpt-4.1-mini", "acompletion")
