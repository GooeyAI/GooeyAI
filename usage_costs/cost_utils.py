from __future__ import annotations

import typing
from decimal import Decimal

from django.db.models import Q, Sum
from loguru import logger


if typing.TYPE_CHECKING:
    from usage_costs.models import ModelSku, ModelPricing, UsageCost
    from bots.models.saved_run import SavedRun


def record_cost_auto(
    model: str,
    sku: ModelSku,
    quantity: int | float | Decimal,
    unit_cost_multiplier: float = 1,
) -> UsageCost | None:
    from celeryapp.tasks import get_running_saved_run

    sr = get_running_saved_run()
    if not sr:
        return None
    pricing = get_model_pricing(model, sku)
    if not pricing:
        return None
    unit_cost = pricing.unit_cost * Decimal(str(unit_cost_multiplier))
    return create_usage_cost(
        sr=sr,
        pricing=pricing,
        quantity=quantity,
        unit_cost=unit_cost,
        unit_quantity=pricing.unit_quantity,
    )


def get_model_pricing(model_id: str, sku: ModelSku) -> ModelPricing | None:
    from usage_costs.models import ModelPricing

    try:
        return ModelPricing.objects.get(model_id=model_id, sku=sku)
    except ModelPricing.DoesNotExist:
        logger.warning(f"Model pricing not found for model_id: {model_id}, sku: {sku}")
        return None


def create_usage_cost(
    sr: SavedRun,
    pricing: ModelPricing,
    quantity: int | float | Decimal,
    unit_cost: Decimal,
    unit_quantity: int,
) -> UsageCost:
    from usage_costs.models import UsageCost

    quantity_dec = Decimal(str(quantity))
    return UsageCost.objects.create(
        saved_run=sr,
        pricing=pricing,
        quantity=quantity_dec,
        unit_cost=unit_cost,
        unit_quantity=unit_quantity,
        dollar_amount=unit_cost * quantity_dec / unit_quantity,
    )


def get_token_counts(sr: SavedRun) -> dict[str, int]:
    from usage_costs.models import ModelSku

    totals = sr.usage_costs.aggregate(
        input_tokens=Sum(
            "quantity",
            filter=Q(
                pricing__sku__in=[ModelSku.llm_prompt, ModelSku.llm_cached_prompt]
            ),
        ),
        output_tokens=Sum("quantity", filter=Q(pricing__sku=ModelSku.llm_completion)),
    )
    return {
        "input_tokens": int(totals["input_tokens"] or 0),
        "output_tokens": int(totals["output_tokens"] or 0),
    }
