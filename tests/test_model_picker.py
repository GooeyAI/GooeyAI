import gooey_gui as gui
from starlette.testclient import TestClient

from ai_models.models import AIModelSpec, ModelProvider
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.language_model_settings_widgets import (
    _llm_prices_per_million,
    language_model_picker,
    llm_picker_options,
)
from gooey_gui.core.renderer import NestingCtx, RenderTreeNode
from server import app
from usage_costs.eco import co2e_grams_per_million
from usage_costs.models import ModelCategory, ModelPricing, ModelSku

client = TestClient(app)


def test_picker_trigger_and_options(transactional_db):
    for name, priority, is_deprecated in [
        ("first", 2, False),
        ("second", 1, False),
        ("retired", 0, True),
    ]:
        AIModelSpec.objects.create(
            category=AIModelSpec.Categories.llm,
            name=name,
            label=name,
            model_id=name,
            provider=ModelProvider.openai,
            priority=priority,
            is_deprecated=is_deprecated,
        )

    # an unknown pick falls back to the first model, and the form follows
    gui.session_state.clear()
    gui.session_state["selected_model"] = "gone"
    root = RenderTreeNode("root")
    with NestingCtx(root):
        language_model_picker()
    assert root.to_dict()["children"][0]["props"]["selected"]["name"] == "first"
    assert gui.session_state["selected_model"] == "first"

    # a deprecated pick stays listed, so the dialog can still show it
    assert _picker_option_names("retired") == ["first", "second", "retired"]
    assert _picker_option_names(None) == ["first", "second"]


def test_co2e_grams_per_million():
    per_input, per_output = co2e_grams_per_million("gpt-4o", "openai", None)
    # decoding costs more than prefill, so a swapped pair fails here
    assert 0 < per_input < per_output
    assert co2e_grams_per_million("not-a-model", "openai", None) is None


def test_llm_prices_per_million(transactional_db):
    for model_id, sku, unit_cost, unit_quantity in [
        ("priced", ModelSku.llm_prompt, 1.25, 1_000_000),
        ("priced", ModelSku.llm_completion, 0.00001, 1),
        # no completion price: a one-sided range would read as free output
        ("prompt_only", ModelSku.llm_prompt, 3, 1_000_000),
    ]:
        ModelPricing.objects.create(
            model_id=model_id,
            sku=sku,
            unit_cost=unit_cost,
            unit_quantity=unit_quantity,
            category=ModelCategory.LLM,
            provider=ModelProvider.openai,
            model_name=model_id,
        )
    llms = [
        AIModelSpec(model_id=model_id)
        for model_id in ["priced", "prompt_only", "unpriced"]
    ]

    assert _llm_prices_per_million(llms) == {"priced": "$1.25 → $10"}


def test_picker_groups_regions_by_label(transactional_db):
    for name, label, region, provider, is_deprecated in [
        ("flash", "Gemini Flash", "", ModelProvider.google, False),
        ("flash_eu_de", "Gemini Flash", "eu-central-1", ModelProvider.requesty, False),
        ("flash_eu_be", "Gemini Flash", "europe-west1", ModelProvider.requesty, False),
        # synced but not turned on
        ("flash_us", "Gemini Flash", "us-central1", ModelProvider.requesty, True),
        ("glm_eu", "GLM 5.2", "eu", ModelProvider.requesty, False),
        ("other", "Other", "", ModelProvider.openai, False),
    ]:
        AIModelSpec.objects.create(
            category=AIModelSpec.Categories.llm,
            name=name,
            label=label,
            model_id=name,
            provider=provider,
            region=region,
            is_deprecated=is_deprecated,
        )

    AIModelSpec.objects.create(
        category=AIModelSpec.Categories.llm,
        name="private",
        label="Private",
        model_id="private",
        zero_data_retention=True,
    )

    options = {o.label: o for o in llm_picker_options(None)}
    assert set(options) == {"Gemini Flash", "GLM 5.2", "Other", "Private"}
    flash = options["Gemini Flash"]
    # the global spec leads; picking a card saves that region's spec
    assert flash.name == "flash"
    assert [(r.name, r.label, r.area) for r in flash.regions] == [
        ("flash", "Global", None),
        ("flash_eu_be", "EU · Belgium", "EU"),
        ("flash_eu_de", "EU · Frankfurt", "EU"),
    ]
    # a model that only runs in one region still shows it
    assert [r.label for r in options["GLM 5.2"].regions] == ["EU"]
    assert options["Other"].regions == []
    # a global model with ZDR gets a card, so the ZDR filter can find it
    assert [(r.label, r.zero_data_retention) for r in options["Private"].regions] == [
        ("Global", True)
    ]

    # a saved region keeps its own spec, shown under its model on the trigger
    gui.session_state.clear()
    gui.session_state["selected_model"] = "flash_eu_de"
    root = RenderTreeNode("root")
    with NestingCtx(root):
        language_model_picker()
    selected = root.to_dict()["children"][0]["props"]["selected"]
    assert selected["name"] == "flash" and len(selected["regions"]) == 3
    assert gui.session_state["selected_model"] == "flash_eu_de"


def _picker_option_names(selected: str | None) -> list[str]:
    # the body the dialog's fetchServerAPI sends
    r = client.post(get_route_path(llm_picker_options), json={"selected": selected})
    r.raise_for_status()
    return [option["name"] for option in r.json()]
