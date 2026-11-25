from contextlib import contextmanager
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from openai.resources.chat.completions import Completions
from openai.types.chat import ChatCompletion

from ai_models.models import AIModelCreator, AIModelSpec, ModelProvider
from bots.models import SavedRun
from bots.models.workflow import Workflow
from celeryapp.tasks import threadlocal
from daras_ai_v2.language_model import run_language_model
from usage_costs.eco import run_eco_cost
from usage_costs.models import ModelCategory, ModelPricing, ModelSku, UsageCost


@pytest.fixture
def requesty_settings(transactional_db, monkeypatch):
    monkeypatch.setattr(settings, "REQUESTY_API_KEY", "rq-test")
    monkeypatch.setattr(
        settings, "REQUESTY_BASE_URL", "https://router.eu.requesty.ai/v1"
    )


def test_regional_run_routes_bills_and_estimates(requesty_settings, monkeypatch):
    spec = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="requesty_vertex_gemini_2_5_flash_eu",
        label="Gemini 2.5 Flash",
        model_id="vertex/gemini-2.5-flash@eu",
        provider=ModelProvider.requesty,
        region="eu-central-1",
        llm_is_thinking_model=True,
        llm_supports_json=True,
    )
    for sku, unit_cost in [
        (ModelSku.llm_prompt, "0.33"),
        (ModelSku.llm_completion, "2.5"),
    ]:
        ModelPricing.objects.create(
            model_id=spec.model_id,
            sku=sku,
            unit_cost=Decimal(unit_cost),
            unit_quantity=1_000_000,
            category=ModelCategory.LLM,
            provider=ModelProvider.requesty,
            model_name=spec.name,
        )
    calls = _fake_chat_completions(monkeypatch)
    sr = SavedRun.objects.create(workflow=Workflow.VIDEO_BOTS)

    with _running(sr):
        run_language_model(
            model=spec.name,
            prompt="Hello",
            reasoning_effort="low",
            response_format_type="json_object",
        )

    request = calls[0]
    assert request["base_url"] == "https://router.eu.requesty.ai/v1/"
    assert request["api_key"] == "rq-test"
    assert request["model"] == "vertex/gemini-2.5-flash@eu"
    assert request["reasoning_effort"] == "low"
    assert request["response_format"] == {"type": "json_object"}
    # Requesty converts the effort itself, and caches Claude prompts when asked
    assert request["extra_body"] == {"requesty": {"auto_cache": True}}
    # billed at the regional row's own price
    assert dict(
        UsageCost.objects.filter(saved_run=sr).values_list("pricing__sku", "unit_cost")
    ) == {ModelSku.llm_prompt: Decimal("0.33"), ModelSku.llm_completion: Decimal("2.5")}
    assert run_eco_cost(sr).region.country_code == "DE"


def test_requesty_claude_gets_no_vendor_workarounds(requesty_settings, monkeypatch):
    anthropic = AIModelCreator.objects.create(
        name="Anthropic", website_url="https://www.anthropic.com"
    )
    claude = AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="requesty_bedrock_claude_sonnet_5_eu_central_1",
        label="Claude Sonnet 5",
        model_id="bedrock/claude-sonnet-5@eu-central-1",
        provider=ModelProvider.requesty,
        creator=anthropic,
        region="eu-central-1",
        llm_is_thinking_model=True,
    )
    calls = _fake_chat_completions(monkeypatch)

    run_language_model(
        model=claude.name,
        prompt="Hello",
        reasoning_effort="high",
        response_format_type="json_object",
    )

    request = calls[0]
    # Requesty turns the effort into Claude's thinking budget
    assert request["reasoning_effort"] == "high"
    assert "thinking" not in request["extra_body"]
    # without JSON mode there's no forced-tool workaround, which Claude 5.1+ rejects
    assert not {"tools", "tool_choice", "response_format"} & set(request)

    # earlier tool calls without thinking blocks don't turn thinking off
    run_language_model(
        model=claude.name,
        messages=[
            {"role": "user", "content": "Weather in Paris?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "14C, cloudy"},
        ],
        reasoning_effort="high",
    )
    assert calls[1]["reasoning_effort"] == "high"

    # without REQUESTY_API_KEY the OpenAI key would otherwise go to Requesty
    monkeypatch.setattr(settings, "REQUESTY_API_KEY", "")
    with pytest.raises(ValueError, match="no Requesty API key"):
        run_language_model(model=claude.name, prompt="Hello")


def test_spec_rules_keep_regional_runs_safe(transactional_db):
    target = AIModelSpec(name="global", label="Global", model_id="g", region="")
    spec = AIModelSpec(
        name="eu", label="EU", model_id="e", region="eu", redirect_to=target
    )
    with pytest.raises(ValidationError, match="same region"):
        spec.clean()
    target.region = "eu"
    spec.clean()
    # a deprecated target would fail the run or loop back
    target.is_deprecated = True
    with pytest.raises(ValidationError, match="isn't deprecated"):
        spec.clean()
    target.is_deprecated = False

    keyless = AIModelSpec(
        name="r", label="R", model_id="r", provider=ModelProvider.requesty
    )
    # the key and router come from settings, so admins needn't enter them
    keyless.clean()

    # two providers may serve the same model in the same region
    AIModelSpec.objects.create(
        name="flash_de", label="Flash", model_id="a", region="eu-central-1"
    )
    twin = AIModelSpec(
        name="flash_de2", label="Flash", model_id="b", region="germanywestcentral"
    )
    twin.clean()


def _fake_chat_completions(monkeypatch) -> list[dict]:
    """Stands in for the OpenAI client's network call, recording what it was sent."""
    calls = []

    def create(self, **kwargs):
        calls.append(
            kwargs
            | {"base_url": str(self._client.base_url), "api_key": self._client.api_key}
        )
        return ChatCompletion.model_validate(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 0,
                "model": kwargs["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"a": 1}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 1_000_000,
                    "total_tokens": 2_000_000,
                },
            }
        )

    monkeypatch.setattr(Completions, "create", create)
    return calls


@contextmanager
def _running(sr: SavedRun):
    # how the celery runner tells usage recording which run to bill
    threadlocal.saved_run = sr
    try:
        yield
    finally:
        del threadlocal.saved_run
