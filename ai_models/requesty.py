"""Keeps Requesty's regional models in AIModelSpec and their prices in ModelPricing."""

import re
from decimal import Decimal

import requests
from django.db import transaction
from loguru import logger
from pydantic import BaseModel, ValidationError

from ai_models.models import AIModelCreator, AIModelSpec, ModelProvider
from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from usage_costs.models import ModelCategory, ModelPricing, ModelSku

# `coding/` rows repeat `vertex/` ones
SKIPPED_HOSTS = {"coding"}
# a catalog this much smaller than what we have is likely a partial response
MAX_SHRINK = 0.25
PER_MILLION = 1_000_000


class RequestyModel(BaseModel):
    """One entry of `GET /v1/models`. Prices are USD per token."""

    id: str
    geolocation: str
    model_canonical_name: str
    model_lab: str
    input_price: Decimal
    output_price: Decimal
    cached_price: Decimal | None = None
    context_window: int
    max_output_tokens: int | None = None
    supports_vision: bool
    supports_reasoning: bool
    supports_output_json_object: bool

    @property
    def region(self) -> str:
        """The id's `@` suffix, e.g. eu-central-1, else the host's area, e.g. eu."""
        _, at, region = self.id.partition("@")
        return region if at else self.geolocation

    @property
    def spec_name(self) -> str:
        return "requesty_" + re.sub(r"[^a-z0-9]+", "_", self.id.lower()).strip("_")


def sync_requesty_models() -> None:
    """Creates hidden specs for new regional models, and keeps every spec's prices,
    key and router current. Runs daily."""
    if not settings.REQUESTY_API_KEY:
        raise ValueError("Set REQUESTY_API_KEY before syncing Requesty models.")
    catalog = fetch_regional_models()
    specs = AIModelSpec.objects.filter(provider=ModelProvider.requesty)
    if len(catalog) < specs.count() * (1 - MAX_SHRINK):
        raise ValueError(
            f"Requesty listed {len(catalog)} regional models but we have {specs.count()}. "
            "Refusing to sync from what looks like a partial catalog."
        )
    creators = {
        creator.name.lower(): creator for creator in AIModelCreator.objects.all()
    }
    # another provider's price for the same model id is never overwritten
    others = set(
        ModelPricing.objects.filter(model_id__in=[model.id for model in catalog])
        .exclude(provider=ModelProvider.requesty)
        .values_list("model_id", "sku")
    )
    if others:
        logger.warning(f"Not overwriting other providers' prices for {sorted(others)}")

    with transaction.atomic():
        for model in catalog:
            spec = _save_spec(model, creators)
            _save_prices(model, spec, others)

    gone = sorted(
        specs.filter(is_deprecated=False)
        .exclude(model_id__in=[model.id for model in catalog])
        .values_list("name", flat=True)
    )
    if gone:
        # turning them off automatically would break published runs overnight
        logger.error(f"Enabled Requesty models are gone from its catalog: {gone}")


def fetch_regional_models() -> list[RequestyModel]:
    r = requests.get(f"{settings.REQUESTY_BASE_URL}/models", timeout=30)
    raise_for_status(r)
    catalog = []
    for entry in r.json(parse_float=Decimal)["data"]:
        if entry.get("geolocation") == "global":
            continue
        if entry["id"].split("/", 1)[0] in SKIPPED_HOSTS:
            continue
        try:
            catalog.append(RequestyModel.model_validate(entry))
        except ValidationError as e:
            logger.warning(f"Skipping Requesty model {entry['id']}: {e}")
    return catalog


def _save_spec(
    model: RequestyModel, creators: dict[str, AIModelCreator]
) -> AIModelSpec:
    """Capabilities are set once, so admins can correct them; the key and router follow settings."""
    router = dict(
        api_key=settings.REQUESTY_API_KEY, base_url=settings.REQUESTY_BASE_URL
    )
    spec, _ = AIModelSpec.objects.update_or_create(
        provider=ModelProvider.requesty,
        model_id=model.id,
        defaults=router,
        create_defaults=router
        | dict(
            category=AIModelSpec.Categories.llm,
            name=model.spec_name,
            label=model.model_canonical_name,
            region=model.region,
            creator=creators.get(model.model_lab.lower()),
            llm_context_window=model.context_window,
            llm_max_output_tokens=model.max_output_tokens or 0,
            llm_is_vision_model=model.supports_vision,
            llm_is_thinking_model=model.supports_reasoning,
            # Requesty lists Claude as JSON-capable, but its replies come in ```json fences
            llm_supports_json=(
                model.supports_output_json_object and model.model_lab != "anthropic"
            ),
            # openai's reasoning models reject temperature
            llm_supports_temperature=not (
                model.model_lab == "openai" and model.supports_reasoning
            ),
            # hidden until an admin turns it on
            is_deprecated=True,
        ),
    )
    return spec


def _save_prices(
    model: RequestyModel, spec: AIModelSpec, others: set[tuple[str, int]]
) -> None:
    for sku, price in [
        (ModelSku.llm_prompt, model.input_price),
        (ModelSku.llm_completion, model.output_price),
        (ModelSku.llm_cached_prompt, model.cached_price),
    ]:
        if price is None or (model.id, sku) in others:
            continue
        unit_cost = price * PER_MILLION
        ModelPricing.objects.update_or_create(
            model_id=model.id,
            sku=sku,
            defaults=dict(unit_cost=unit_cost),
            create_defaults=dict(
                unit_cost=unit_cost,
                unit_quantity=PER_MILLION,
                model_name=spec.name,
                category=ModelCategory.LLM,
                provider=ModelProvider.requesty,
                pricing_url=f"{settings.REQUESTY_BASE_URL}/models",
                notes="Synced daily from Requesty's catalog.",
            ),
        )
