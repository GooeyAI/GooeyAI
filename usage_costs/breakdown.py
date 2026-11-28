"""A run's price, line by line, for the cost modal.

Built on read from the run's UsageCost rows, like the eco cost. A recipe adds
its own flat charges and hands the lines to `cost_breakdown`, which adds the
multiplier and anything charged beyond the lines.
"""

import math
from collections import defaultdict
from decimal import Decimal

from django.db.models import Max, Min, Sum

from bots.models import SavedRun
from daras_ai_v2 import settings
from daras_ai_v2.preview_img import media_preview_img
from gooey_gui.types.run_cost_props import (
    CostBreakdownProps,
    CostLineProps,
    CostSectionProps,
)
from usage_costs.models import ModelSku


def cost_breakdown(
    *,
    usage_sections: list[CostSectionProps],
    charges: list[CostLineProps],
    multiplier: float,
    charged_credits: int,
    final: bool = True,
) -> CostBreakdownProps:
    """The model sections, then the run's own charges: the recipe's flat
    lines, then the multiplier and the rounding up to `charged_credits`.
    Not `final` while the run is running: a gap to the total is usage still
    to come, not a charge."""
    subtotal = sum(
        line.usd for section in usage_sections for line in section.lines
    ) + sum(line.usd for line in charges)
    if multiplier != 1:
        charges.append(
            CostLineProps(
                label=f"Workflow price × {multiplier:g}",
                usd=subtotal * (multiplier - 1),
            )
        )
    total = credits_to_usd(charged_credits)
    remainder = total - subtotal * multiplier
    # under a cent is the rounding up to a whole credit, which is not a
    # charge of its own; more is one the lines don't itemise, e.g. call
    # minutes reported late
    if final and remainder >= credits_to_usd(1):
        charges.append(CostLineProps(label="Other charges", usd=remainder))

    if charges:
        usage_sections.append(CostSectionProps(lines=charges))
    return CostBreakdownProps(sections=usage_sections, total_usd=total)


def usage_cost_sections(
    sr: SavedRun, *, exclude_model_ids: tuple[str, ...] = ()
) -> list[CostSectionProps]:
    """One section per model that recorded usage on the run, its SKUs as
    lines: input and output tokens, GPU time and so on."""
    from ai_models.models import AIModelSpec

    rows = (
        sr.usage_costs.exclude(pricing__model_id__in=exclude_model_ids)
        .values("pricing__model_id", "pricing__model_name", "pricing__sku")
        .annotate(
            quantity=Sum("quantity"),
            dollars=Sum("dollar_amount"),
            unit_quantity=Max("unit_quantity"),
            first_at=Min("created_at"),
        )
        .order_by("first_at")
    )
    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_model[row["pricing__model_id"]].append(row)
    # model_id -> (label, creator photo); the newest live spec wins
    specs = {
        model_id: (label, photo_url)
        for model_id, label, photo_url in AIModelSpec.objects.filter(
            model_id__in=by_model
        )
        .order_by("-is_deprecated", "updated_at")
        .values_list("model_id", "label", "creator__photo_url")
    }
    sections = []
    for model_id, skus in by_model.items():
        skus.sort(key=lambda row: list(SKU_LABELS).index(row["pricing__sku"]))
        lines = [_sku_line(row) for row in skus]
        label, photo_url = specs.get(model_id) or (None, None)
        sections.append(
            CostSectionProps(
                label=label or skus[0]["pricing__model_name"] or model_id,
                icon_url=photo_url
                and (media_preview_img(photo_url, size="40x40") or photo_url),
                usd=sum(line.usd for line in lines),
                lines=lines,
            )
        )
    return sections


# every SKU, in line order: input before output, the order the model works in
SKU_LABELS = {
    ModelSku.llm_cached_prompt: "Cached input tokens",
    ModelSku.llm_prompt: "Input tokens",
    ModelSku.input_image_tokens: "Image input tokens",
    ModelSku.llm_completion: "Output tokens",
    ModelSku.output_image_tokens: "Image output tokens",
    ModelSku.gpu_ms: "GPU time (ms)",
    ModelSku.fal_billable_units: "Billable units",
    ModelSku.video_generation: "Video generation",
    ModelSku.ivr_call: "Call time (s)",
}
TOKEN_SKUS = {
    ModelSku.llm_prompt,
    ModelSku.llm_cached_prompt,
    ModelSku.llm_completion,
    ModelSku.input_image_tokens,
    ModelSku.output_image_tokens,
}


def _sku_line(row: dict) -> CostLineProps:
    sku = ModelSku(row["pricing__sku"])
    quantity = float(row["quantity"])
    usd = float(row["dollars"])
    unit_price = None
    if quantity:
        # the run's average, so rows priced with a multiplier still add up
        per_unit = usd / quantity
        if sku in TOKEN_SKUS:
            unit_price = f"{format_usd(per_unit * 1_000_000)} / 1M"
        elif row["unit_quantity"] > 1:
            unit_price = f"{format_usd(per_unit * row['unit_quantity'])} / {row['unit_quantity']:,}"
        else:
            unit_price = f"{format_usd(per_unit)} each"
    return CostLineProps(
        label=SKU_LABELS[sku],
        usd=usd,
        quantity=quantity,
        unit_price=unit_price,
    )


def credits_to_usd(credits: int | float | Decimal) -> float:
    return float(credits) / settings.ADDON_CREDITS_PER_DOLLAR


def format_usd(usd: float) -> str:
    """A unit price: $2.50, or two significant figures below a cent, such as a
    GPU millisecond's $0.000025."""
    if usd >= 0.01 or usd <= 0:
        return f"${usd:,.2f}"
    return f"${usd:.{1 - math.floor(math.log10(usd))}f}"
