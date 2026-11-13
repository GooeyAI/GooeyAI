from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from gooey_gui.types.run_debug_info_props import AuthorProps


class EcoRegionProps(BaseModel):
    """Where the run's electricity came from, for the modal's region block."""

    country_code: str  # ISO 3166-1 alpha-2; the modal shows its flag and name
    # tooltip when the serving site isn't known; None when the provider pins it
    assumption: str | None = None
    gco2e_per_kwh: float
    gco2e_per_kwh_min: float
    gco2e_per_kwh_max: float
    # energy source -> share of generation, 0..1, largest first
    mix: dict[str, float]


class EcoModelTokens(BaseModel):
    """One model's tokens in the run, shown under the cost."""

    model_id: str
    label: str
    input_tokens: int  # includes cached_input_tokens
    output_tokens: int
    cached_input_tokens: int = 0


class EcoCostProps(BaseModel):
    """A run's summed eco estimate, as `usage_costs.eco.run_eco_cost` returns it."""

    confidence: Literal["low", "medium", "high"]
    reasons: list[str] = []
    models: list[EcoModelTokens] = []
    co2e_grams: float
    co2e_min: float
    co2e_max: float
    energy_wh: float
    water_ml: float
    water_data_center_ml: float
    region: EcoRegionProps | None = None


class CostLineProps(BaseModel):
    """One line of the cost breakdown. Amounts are for one run, in USD; the
    modal scales `usd` and `quantity` with its runs slider."""

    label: str
    note: str = ""  # the line under the label
    usd: float
    # with unit_price, the note becomes "5,400 × $2.50 / 1M"
    quantity: float | None = None
    unit_price: str | None = None
    url: str | None = None  # the line's own run, e.g. a tool call's


class CostSectionProps(BaseModel):
    """A model and its lines, or the run's own charges, which have no label."""

    label: str | None = None
    icon_url: str | None = None  # the model creator's logo, before its label
    usd: float | None = None  # the model's subtotal, beside its label
    lines: list[CostLineProps] = []
    collapsed: bool = False  # the lines start folded behind the label


class CostBreakdownProps(BaseModel):
    """What one run was billed, line by line, for the modal's Cost tab. The
    lines add up to `total_usd`."""

    sections: list[CostSectionProps]
    total_usd: float


class RunCostProps(BaseModel):
    """Everything the "Run Cost & Environment Impact" modal shows: the run's
    price and its breakdown (Cost tab), its eco figures (Eco tab), and who ran
    and paid for it. The modal scales them client-side with a runs slider.
    Opened from the top bar's and the run bar's cost readout."""

    # None until the run's first model call records usage
    eco: EcoCostProps | None = None
    run_cost_usd: float
    cost_breakdown: CostBreakdownProps | None = None
    methodology_url: str
    run_by: AuthorProps | None = None
    charged_to: AuthorProps | None = None
    balance: str | None = None
    balance_url: str | None = None
    # a running run shows an estimate so far; a failed or cancelled one is not
    # charged
    status: Literal["done", "running", "failed", "cancelled"] = "done"
    # "39s · 8:02 PM", formatted in the viewer's zone
    run_time_s: float
    created_at: str  # ISO 8601
