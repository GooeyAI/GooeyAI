import json
from contextlib import contextmanager
from decimal import Decimal

import pytest
import requests
from django.core.exceptions import ValidationError
from openai.resources.chat.completions import Completions
from openai.types.chat import ChatCompletion

from ai_models import requesty
from ai_models.models import AIModelCreator, AIModelSpec, ModelProvider
from bots.models import SavedRun
from bots.models.workflow import Workflow
from celeryapp.tasks import threadlocal
from daras_ai_v2 import settings
from daras_ai_v2.language_model import run_language_model
from usage_costs.eco import run_eco_cost
from usage_costs.models import ModelCategory, ModelPricing, ModelSku, UsageCost

EU_FLASH = "vertex/gemini-2.5-flash@europe-west1"


@pytest.fixture
def catalog(transactional_db, monkeypatch) -> list[dict]:
    """Requesty's catalog, served to the sync. Tests edit the list to change it."""
    monkeypatch.setattr(settings, "REQUESTY_API_KEY", "rq-test")
    monkeypatch.setattr(
        settings, "REQUESTY_BASE_URL", "https://router.eu.requesty.ai/v1"
    )
    AIModelCreator.objects.create(name="Google")
    entries = [
        _entry(EU_FLASH),
        _entry("vertex/gemini-2.5-flash@us-central1", geolocation="us"),
        _entry("vertex/gemini-2.5-flash@eu", input_price=3.3e-07),
        _entry(
            "nebius/glm-5.2",
            model_canonical_name="glm-5.2",
            model_lab="zai",
            cached_price=None,
            max_output_tokens=None,
        ),
        _entry(
            "bedrock/claude-sonnet-4-5@eu-central-1",
            model_canonical_name="claude-sonnet-4-5",
            model_lab="anthropic",
        ),
        # neither is synced: global rows stay on our direct specs, coding/ repeats vertex/
        _entry("vertex/gemini-2.5-flash", geolocation="global"),
        _entry("coding/gemini-2.5-flash@europe-west1"),
    ]

    def get(url, timeout):
        assert url == "https://router.eu.requesty.ai/v1/models"
        r = requests.Response()
        r.status_code = 200
        r._content = json.dumps({"object": "list", "data": entries}).encode()
        return r

    monkeypatch.setattr(requesty.requests, "get", get)
    return entries


def _entry(model_id: str, **overrides) -> dict:
    """A catalog entry shaped like Requesty's `GET /v1/models`."""
    return {
        "id": model_id,
        "geolocation": "eu",
        "model_canonical_name": "gemini-2.5-flash",
        "model_lab": "google",
        "input_price": 3e-07,
        "output_price": 2.5e-06,
        "cached_price": 3e-08,
        "context_window": 1048576,
        "max_output_tokens": 65536,
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_output_json_object": True,
        "description": "fields we don't use are ignored",
    } | overrides


def test_sync_creates_hidden_specs_and_prices(catalog):
    requesty.sync_requesty_models()

    specs = {s.model_id: s for s in AIModelSpec.objects.all()}
    assert set(specs) == {
        EU_FLASH,
        "vertex/gemini-2.5-flash@us-central1",
        "vertex/gemini-2.5-flash@eu",
        "nebius/glm-5.2",
        "bedrock/claude-sonnet-4-5@eu-central-1",
    }
    eu = specs[EU_FLASH]
    assert (eu.name, eu.label, eu.region, eu.creator.name) == (
        "requesty_vertex_gemini_2_5_flash_europe_west1",
        "gemini-2.5-flash",
        "europe-west1",
        "Google",
    )
    assert (eu.provider, eu.api_key, eu.base_url) == (
        ModelProvider.requesty,
        "rq-test",
        "https://router.eu.requesty.ai/v1",
    )
    # hidden until an admin turns it on; ZDR is never taken from the catalog
    assert eu.is_deprecated and not eu.zero_data_retention
    assert eu.llm_is_vision_model and eu.llm_is_thinking_model and eu.llm_supports_json
    # a host without a region suffix runs in its area
    assert specs["nebius/glm-5.2"].region == "eu"
    assert specs["nebius/glm-5.2"].creator is None
    # Requesty wraps Claude's JSON in a code fence, so JSON mode is off for it
    assert not specs["bedrock/claude-sonnet-4-5@eu-central-1"].llm_supports_json

    assert _prices(EU_FLASH) == {
        ModelSku.llm_prompt: Decimal("0.3"),
        ModelSku.llm_completion: Decimal("2.5"),
        ModelSku.llm_cached_prompt: Decimal("0.03"),
    }
    assert set(_prices("nebius/glm-5.2")) == {
        ModelSku.llm_prompt,
        ModelSku.llm_completion,
    }


def test_resync_keeps_admin_edits(catalog, monkeypatch):
    ModelPricing.objects.create(
        model_id="vertex/gemini-2.5-flash@eu",
        sku=ModelSku.llm_prompt,
        unit_cost=9,
        unit_quantity=1_000_000,
        category=ModelCategory.LLM,
        provider=ModelProvider.openai,
        model_name="hand-made",
    )
    requesty.sync_requesty_models()
    AIModelSpec.objects.filter(model_id=EU_FLASH).update(
        label="Gemini 2.5 Flash",
        is_deprecated=False,
        zero_data_retention=True,
        llm_supports_json=False,
    )
    AIModelSpec.objects.filter(model_id="nebius/glm-5.2").update(is_deprecated=False)

    catalog[0] |= {"input_price": 4e-07, "context_window": 2_000_000}
    del catalog[3]  # glm-5.2 leaves the catalog
    monkeypatch.setattr(settings, "REQUESTY_API_KEY", "rq-rotated")
    requesty.sync_requesty_models()

    eu = AIModelSpec.objects.get(model_id=EU_FLASH)
    assert (eu.label, eu.is_deprecated, eu.zero_data_retention) == (
        "Gemini 2.5 Flash",
        False,
        True,
    )
    # capabilities are set once, so an admin's correction survives
    assert (eu.llm_supports_json, eu.llm_context_window) == (False, 1048576)
    # prices and the key follow Requesty and settings
    assert _prices(EU_FLASH)[ModelSku.llm_prompt] == Decimal("0.4")
    assert eu.api_key == "rq-rotated"
    # turning it off would break published runs, so it's only logged
    assert not AIModelSpec.objects.get(model_id="nebius/glm-5.2").is_deprecated
    # another provider's price is left alone
    assert _prices("vertex/gemini-2.5-flash@eu")[ModelSku.llm_prompt] == Decimal(9)


def test_sync_changes_nothing_on_a_partial_catalog(catalog):
    requesty.sync_requesty_models()
    catalog[0]["input_price"] = 4e-07
    del catalog[1:3]

    with pytest.raises(ValueError, match="partial catalog"):
        requesty.sync_requesty_models()
    assert _prices(EU_FLASH)[ModelSku.llm_prompt] == Decimal("0.3")


def test_sync_needs_a_key(catalog, monkeypatch):
    monkeypatch.setattr(settings, "REQUESTY_API_KEY", "")
    with pytest.raises(ValueError, match="REQUESTY_API_KEY"):
        requesty.sync_requesty_models()
    assert not AIModelSpec.objects.exists()


def test_regional_run_routes_bills_and_estimates(catalog, monkeypatch):
    requesty.sync_requesty_models()
    spec = AIModelSpec.objects.get(model_id="vertex/gemini-2.5-flash@eu")
    AIModelSpec.objects.filter(pk=spec.pk).update(
        is_deprecated=False, region="eu-central-1"
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
    # Requesty converts the effort itself, and adds no cache writes we don't bill
    assert request["extra_body"] == {"requesty": {"auto_cache": False}}
    # billed at the regional row's own price
    assert dict(
        UsageCost.objects.filter(saved_run=sr).values_list("pricing__sku", "unit_cost")
    ) == {ModelSku.llm_prompt: Decimal("0.33"), ModelSku.llm_completion: Decimal("2.5")}
    assert run_eco_cost(sr).region.country_code == "DE"


def test_requesty_claude_gets_no_vendor_workarounds(catalog, monkeypatch):
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
        api_key="rq-test",
        base_url="https://router.eu.requesty.ai/v1",
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
    # claude rejects temperature with thinking on
    assert "temperature" not in request

    # a key-less row would otherwise send the OpenAI key to Requesty
    AIModelSpec.objects.filter(pk=claude.pk).update(api_key="")
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

    keyless = AIModelSpec(
        name="r", label="R", model_id="r", provider=ModelProvider.requesty
    )
    with pytest.raises(ValidationError, match="API key"):
        keyless.clean()

    # eu-central-1 and germanywestcentral are both "EU · Frankfurt"
    AIModelSpec.objects.create(
        name="flash_de", label="Flash", model_id="a", region="eu-central-1"
    )
    twin = AIModelSpec(
        name="flash_de2", label="Flash", model_id="b", region="germanywestcentral"
    )
    with pytest.raises(ValidationError, match="already runs in EU · Frankfurt"):
        twin.clean()
    twin.is_deprecated = True
    twin.clean()


def _prices(model_id: str) -> dict[int, Decimal]:
    return dict(
        ModelPricing.objects.filter(model_id=model_id).values_list("sku", "unit_cost")
    )


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
