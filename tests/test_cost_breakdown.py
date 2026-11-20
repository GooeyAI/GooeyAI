from decimal import Decimal
from unittest.mock import patch

import pytest

from ai_models.models import ModelProvider
from bots.models import SavedRun
from bots.models.workflow import Workflow
from gooey_gui.types.run_cost_props import CostLineProps
from usage_costs.breakdown import cost_breakdown, format_usd, usage_cost_sections
from usage_costs.models import ModelCategory, ModelPricing, ModelSku, UsageCost

LIPSYNC = CostLineProps(label="Lipsync", usd=0.01)


@pytest.fixture(autouse=True)
def one_credit_is_one_cent():
    with patch("daras_ai_v2.settings.ADDON_CREDITS_PER_DOLLAR", 100):
        yield


def test_standard_run_adds_up_to_the_charge(transactional_db):
    """Three GLM rounds, rounded up from $0.0345 to the $0.04 debit."""
    sr = SavedRun.objects.create(workflow=Workflow.VIDEO_BOTS)
    for _ in range(3):
        _usage(sr, ModelSku.llm_prompt, 1800, "2.5")
        _usage(sr, ModelSku.llm_completion, 1400, "5")

    breakdown = cost_breakdown(
        usage_sections=usage_cost_sections(sr),
        charges=[],
        multiplier=1,
        charged_credits=4,
    )

    # the rounding up to a whole cent is not a line, so no charges section
    (model,) = breakdown.sections
    assert model.label == "GLM 5.3"
    assert model.usd == pytest.approx(0.0345)
    assert [(line.label, line.quantity, line.unit_price) for line in model.lines] == [
        ("Input tokens", 5400, "$2.50 / 1M"),
        ("Output tokens", 4200, "$5.00 / 1M"),
    ]
    assert breakdown.total_usd == pytest.approx(0.04)
    assert _billed(breakdown) == pytest.approx(0.0345)


def test_cached_input_tokens_are_their_own_line(transactional_db):
    """A model with a cached price records its cached tokens apart, cheaper,
    and they read first: input before output, cached before uncached."""
    sr = SavedRun.objects.create(workflow=Workflow.VIDEO_BOTS)
    _usage(sr, ModelSku.llm_cached_prompt, 4000, "0.25")
    _usage(sr, ModelSku.llm_prompt, 1000, "2.5")
    _usage(sr, ModelSku.llm_completion, 200, "10")

    (model,) = usage_cost_sections(sr)
    assert [(line.label, line.quantity, line.unit_price) for line in model.lines] == [
        ("Cached input tokens", 4000, "$0.25 / 1M"),
        ("Input tokens", 1000, "$2.50 / 1M"),
        ("Output tokens", 200, "$10.00 / 1M"),
    ]
    assert model.usd == pytest.approx(0.001 + 0.0025 + 0.002)


def test_multiplier_and_late_charges_are_their_own_lines(transactional_db):
    sr = SavedRun.objects.create(workflow=Workflow.VIDEO_BOTS)
    _usage(sr, ModelSku.llm_completion, 1000, "10")  # $0.01

    breakdown = cost_breakdown(
        usage_sections=usage_cost_sections(sr),
        charges=[LIPSYNC],
        multiplier=2,
        # (0.01 + 0.01) x 2 = 0.04; 0.10 means 6 credits came after the run
        charged_credits=10,
    )

    run = breakdown.sections[-1]
    assert [(line.label, line.usd) for line in run.lines] == [
        ("Lipsync", 0.01),
        ("Workflow price × 2", pytest.approx(0.02)),
        ("Other charges", pytest.approx(0.06)),
    ]
    assert _billed(breakdown) == pytest.approx(0.10)


@pytest.mark.parametrize(
    "usd, text",
    [
        (0.07, "$0.07"),
        (0.0345, "$0.03"),
        (0.021, "$0.02"),
        (0.0055, "$0.0055"),
        (0.000025, "$0.000025"),
        (2.5, "$2.50"),
        (1234.5, "$1,234.50"),
        (0, "$0.00"),
    ],
)
def test_format_usd(usd, text):
    assert format_usd(usd) == text


def _usage(sr: SavedRun, sku: ModelSku, quantity: int, usd_per_million: str):
    pricing, _ = ModelPricing.objects.get_or_create(
        model_id="glm-5.3",
        sku=sku,
        defaults=dict(
            model_name="GLM 5.3",
            unit_cost=Decimal(usd_per_million),
            unit_quantity=1_000_000,
            category=ModelCategory.LLM,
            provider=ModelProvider.openai,
        ),
    )
    UsageCost.objects.create(
        saved_run=sr,
        pricing=pricing,
        quantity=quantity,
        unit_cost=pricing.unit_cost,
        unit_quantity=pricing.unit_quantity,
        dollar_amount=pricing.unit_cost * quantity / pricing.unit_quantity,
    )


def _billed(breakdown) -> float:
    return sum(line.usd for section in breakdown.sections for line in section.lines)
