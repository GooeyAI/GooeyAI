from __future__ import annotations

from typing import ClassVar, Literal

from gooey_gui.types import StrictComponentModel

Modality = Literal["text", "image", "audio"]


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


class ModelPickerProps(StrictComponentModel):
    """The layout v2 model trigger and its "Choose a model" dialog. The pick and its effort
    are written to `name` and `effort_name` in the form state on "Use model"."""

    _component: ClassVar[Literal["ModelPicker"]] = "ModelPicker"

    name: str
    effort_name: str
    efforts: dict[str, str]  # value -> label, in display order
    options: list[ModelPickerOption]
    co2e_methodology_url: str
