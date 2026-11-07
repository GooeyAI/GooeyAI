from __future__ import annotations

from typing import ClassVar, Literal

from gooey_gui.types import StrictComponentModel

Modality = Literal["text", "image", "audio"]


class ModelPickerRegion(StrictComponentModel):
    """One spec of a model offered in several regions (specs that share a label)."""

    name: str  # AIModelSpec.name, the value written to the form
    label: str  # e.g. "EU · Frankfurt", or "Global"
    country_code: str | None = None  # for the flag; None for global and multi-region
    area: str | None = None  # the Region filter's value, e.g. "EU"; None for global
    # as on the option, but for this region's spec
    price: str | None = None
    co2e: str | None = None
    zero_data_retention: bool


class ModelPickerOption(StrictComponentModel):
    name: str  # AIModelSpec.name, the value written to the form
    label: str
    creator: str | None = None
    icon_url: str | None = None
    # input → output USD per 1M tokens, e.g. "$2 → $10"; None when either is unpriced
    price: str | None = None
    # input → output grams CO2e per 1M tokens, e.g. "36 g → 150 g"; None when unknown
    co2e: str | None = None
    context_window: int
    reasoning: bool
    inputs: list[Modality]
    outputs: list[Modality]
    # empty for a model that only runs globally; otherwise `name` is one of them
    regions: list[ModelPickerRegion] = []


class ModelPickerProps(StrictComponentModel):
    """The layout v2 model trigger and its "Choose a model" dialog. The pick and its effort
    are written to `name` and `effort_name` in the form state on "Use model"."""

    _component: ClassVar[Literal["ModelPicker"]] = "ModelPicker"

    name: str
    effort_name: str
    efforts: dict[str, str]  # value -> label, in display order
    selected: ModelPickerOption  # the trigger's model
    # POST {selected} here for every option; the dialog fetches it on first open
    options_url: str
    co2e_methodology_url: str
