from unittest.mock import patch

import pytest

from model_api import routing
from model_api.routing import ModelNotFound, ModelNotPriced, resolve_model


@pytest.mark.parametrize(
    "model, call_type, expected",
    [
        ("gpt-4.1-mini", "acompletion", "openai/gpt-4.1-mini"),
        ("gpt-4.1-mini", "aresponses", "openai/gpt-4.1-mini"),
        ("openai/gpt-4.1-mini", "acompletion", "openai/gpt-4.1-mini"),
        ("o3", "acompletion", "openai/o3"),
    ],
)
def test_resolves_native_ids(model, call_type, expected):
    assert resolve_model(model, call_type) == expected


@pytest.mark.parametrize(
    "model, call_type",
    [
        ("not-a-real-model", "acompletion"),
        # a family Gooey doesn't serve yet
        ("claude-sonnet-4-5", "acompletion"),
        # the route fixes the family, whatever the ID says
        ("gpt-4.1-mini", "anthropic_messages"),
        ("gpt-4.1-mini", "agenerate_content"),
    ],
)
def test_unserved_ids_are_not_found(model, call_type):
    with pytest.raises(ModelNotFound):
        resolve_model(model, call_type)


def test_route_family_uses_the_policy_table():
    with patch.dict(routing.MODEL_PROVIDERS, {"anthropic": "anthropic"}):
        assert (
            resolve_model("claude-sonnet-4-5", "anthropic_messages")
            == "anthropic/claude-sonnet-4-5"
        )
        assert (
            resolve_model("anthropic/claude-sonnet-4-5", "anthropic_messages")
            == "anthropic/claude-sonnet-4-5"
        )


def test_aliases_resolve_before_inference():
    with patch.dict(routing.MODEL_ALIASES, {"gooey-mini": "gpt-4.1-mini"}):
        assert resolve_model("gooey-mini", "acompletion") == "openai/gpt-4.1-mini"


def test_unpriced_models_are_refused():
    unpriced = {"input_cost_per_token": 0, "output_cost_per_token": 1e-06}
    with patch.object(routing.litellm, "get_model_info", return_value=unpriced):
        with pytest.raises(ModelNotPriced):
            resolve_model("gpt-4.1-mini", "acompletion")
