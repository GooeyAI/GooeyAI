from ai_models.models import AIModelSpec
from daras_ai_v2.language_model_settings_widgets import _llm_prices_per_million
from usage_costs.eco import co2e_grams_per_million
from usage_costs.models import ModelPricing, ModelSku


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
            category=1,
            provider=1,
            model_name=model_id,
        )
    llms = [
        AIModelSpec(model_id=model_id)
        for model_id in ["priced", "prompt_only", "unpriced"]
    ]

    assert _llm_prices_per_million(llms) == {"priced": "$1.25 → $10"}
