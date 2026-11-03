from collections import defaultdict

import fastapi
import gooey_gui as gui
from django.db.models import QuerySet
from ecocost.display import format_grams
from gooey_gui.types.model_picker_props import ModelPickerOption, ModelPickerProps
from pydantic import BaseModel, Field

from ai_models.models import AIModelSpec, ModelProvider
from daras_ai_v2 import settings
from daras_ai_v2.enum_selector_widget import enum_selector, BLANK_OPTION
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.language_model import (
    ResponseFormatType,
    ReasoningEffort,
)
from routers.custom_api_router import CustomAPIRouter
from usage_costs.eco import co2e_grams_per_million
from usage_costs.models import ModelPricing, ModelSku

router = CustomAPIRouter()


class LanguageModelSettings(BaseModel):
    avoid_repetition: bool | None = Field(
        None,
        title="Avoid Repetition",
        description="Avoid repeating the same words or phrases in the response.",
    )
    num_outputs: int | None = Field(
        None,
        title="Answer Outputs",
        description="How many answers should the agent/copilot generate? Additional answer outputs increase the cost of each run.",
    )
    quality: float | None = Field(
        None,
        title="Attempts",
        description="Generate multiple responses and choose the best one",
    )
    max_tokens: int | None = Field(
        None,
        title="Max Output Tokens",
        description="The maximum number of tokens to generate in the completion. Increase to generate longer responses.",
    )
    sampling_temperature: float | None = Field(
        None,
        title="Creativity (aka Sampling Temperature)",
        description="Higher values allow the LLM to take more risks. Try values larger than 1 for more creative applications or 0 to ensure that LLM gives the same answer when given the same user input. ",
    )
    reasoning_effort: ReasoningEffort.api_choices | None = Field(
        None,
        title="Reasoning Effort",
        description=(
            "Constrains effort on reasoning for reasoning models. "
            "Increasing reasoning effort can improve response quality by enabling more thorough analysis for complex problems. "
            "Reducing reasoning effort can result in faster responses and fewer tokens used on reasoning in a response. "
            "We suggest starting at the minimum and increasing the effort incrementally to find the optimal range for your use case"
        ),
    )
    response_format_type: ResponseFormatType | None = Field(
        None, title="Response Format"
    )


def language_model_selector(
    label: str = "##### 🔠 Language Model Settings",
    label_visibility: str = "visible",
    key: str = "selected_model",
):
    llm_models = AIModelSpec.objects.filter(
        category=AIModelSpec.Categories.llm,
    ).order_for_frontend(
        selected_models=gui.session_state.get(key),
    )
    options = {model.name: model.display_html() for model in llm_models}
    return gui.selectbox(
        options=options,
        format_func=options.__getitem__,
        label=label,
        label_visibility=label_visibility,
        key=key,
    )


def language_model_picker():
    """Layout v2's model trigger and "Choose a model" dialog, which also sets the
    reasoning effort."""
    key = "selected_model"
    llms = _live_llms(gui.session_state.get(key))
    # as `gui.selectbox` does: a missing or unknown pick falls back to the first model
    llm = llms.filter(name=gui.session_state.get(key)).first() or llms.first()
    if not llm:
        return
    gui.session_state[key] = llm.name

    deprecated = ReasoningEffort._deprecated()
    gui.model_component(
        ModelPickerProps(
            name=key,
            effort_name="reasoning_effort",
            efforts={e.name: e.label for e in ReasoningEffort if e not in deprecated},
            selected=_model_picker_options([llm])[0],
            options_url=get_route_path(llm_picker_options),
            co2e_methodology_url=settings.ECO_COST_METHODOLOGY_URL,
        )
    )


# The full list grows with every model we add, so it isn't in the page's render tree.
@router.post("/__/llm-models/picker/")
def llm_picker_options(
    selected: str | None = fastapi.Body(None, embed=True),
) -> list[ModelPickerOption]:
    """Every option in "Choose a model", fetched when the dialog first opens."""
    return _model_picker_options(list(_live_llms(selected)))


def _live_llms(selected: str | None) -> QuerySet[AIModelSpec]:
    """Non-deprecated LLMs, plus `selected` even if deprecated, in display order."""
    return AIModelSpec.objects.filter(
        category=AIModelSpec.Categories.llm,
    ).order_for_frontend(selected_models=selected)


def _model_picker_options(llms: list[AIModelSpec]) -> list[ModelPickerOption]:
    prices = _llm_prices_per_million(llms)
    return [_model_picker_option(llm, prices.get(llm.model_id)) for llm in llms]


def _llm_prices_per_million(llms: list[AIModelSpec]) -> dict[str, str]:
    """model_id -> "$2 → $10", input → output USD per 1M tokens, in one query."""
    usd = defaultdict(dict)
    for pricing in ModelPricing.objects.filter(
        model_id__in={llm.model_id for llm in llms},
        sku__in=[ModelSku.llm_prompt, ModelSku.llm_completion],
    ):
        usd[pricing.model_id][pricing.sku] = (
            float(pricing.unit_cost) / pricing.unit_quantity * 1_000_000
        )
    return {
        model_id: (
            f"${prices[ModelSku.llm_prompt]:.3g} → ${prices[ModelSku.llm_completion]:.3g}"
        )
        for model_id, prices in usd.items()
        if len(prices) == 2
    }


def _model_picker_option(llm: AIModelSpec, price: str | None) -> ModelPickerOption:
    inputs = ["text"]
    if llm.llm_is_vision_model:
        inputs.append("image")
    if llm.llm_supports_input_audio:
        inputs.append("audio")
    outputs = ["text"]
    if llm.llm_is_audio_model:
        outputs.append("audio")
    co2e = None
    if grams := co2e_grams_per_million(
        llm.model_id, ModelProvider(llm.provider).name, llm.base_url or None
    ):
        co2e = " → ".join(format_grams(g) for g in grams)
    return ModelPickerOption(
        name=llm.name,
        label=llm.label,
        creator=llm.creator and llm.creator.name,
        icon_url=(llm.creator and llm.creator.photo_url) or None,
        price=price,
        co2e=co2e,
        context_window=llm.llm_context_window,
        reasoning=llm.llm_is_thinking_model,
        inputs=inputs,
        outputs=outputs,
    )


def language_model_settings(
    selected_models: str | list[str] | None = None, *, reasoning_effort: bool = True
) -> None:
    if isinstance(selected_models, str):
        selected_models = [selected_models]
    elif not selected_models:
        selected_models = []

    llms = list(AIModelSpec.objects.filter(name__in=selected_models))

    col1, _ = gui.columns(2)
    with col1:
        gui.selectbox(
            label=(
                "###### " + field_title(LanguageModelSettings, "response_format_type")
            ),
            help=field_desc(LanguageModelSettings, "response_format_type"),
            options=[None, "json_object"],
            key="response_format_type",
            format_func={
                None: BLANK_OPTION,
                "json_object": "JSON Object",
            }.__getitem__,
        )

    col1, col2 = gui.columns(2)
    with col1:
        if llms:
            max_output_tokens = min(
                llm.llm_max_output_tokens or llm.llm_context_window for llm in llms
            )
        else:
            max_output_tokens = 4096

        gui.slider(
            label="###### " + field_title(LanguageModelSettings, "max_tokens"),
            help=field_desc(LanguageModelSettings, "max_tokens"),
            key="max_tokens",
            min_value=10,
            max_value=max_output_tokens,
            step=2,
        )

    if any(llm.llm_supports_temperature for llm in llms):
        with col2:
            gui.slider(
                label=(
                    "###### "
                    + field_title(LanguageModelSettings, "sampling_temperature")
                ),
                help=field_desc(LanguageModelSettings, "sampling_temperature"),
                key="sampling_temperature",
                min_value=0.0,
                max_value=2.0,
            )

    col1, col2 = gui.columns(2)
    with col1:
        gui.slider(
            label="###### " + field_title(LanguageModelSettings, "num_outputs"),
            help=field_desc(LanguageModelSettings, "num_outputs"),
            key="num_outputs",
            min_value=1,
            max_value=4,
        )
    if any(
        not llm.llm_is_chat_model and llm.provider == ModelProvider.openai
        for llm in llms
    ):
        with col2:
            gui.slider(
                label="###### " + field_title(LanguageModelSettings, "quality"),
                help=field_desc(LanguageModelSettings, "quality"),
                key="quality",
                min_value=1.0,
                max_value=5.0,
                step=0.1,
            )

    if reasoning_effort and any(llm.llm_is_thinking_model for llm in llms):
        col1, _ = gui.columns(2)
        with col1:
            enum_selector(
                ReasoningEffort,
                label=(
                    "###### " + field_title(LanguageModelSettings, "reasoning_effort")
                ),
                help=field_desc(LanguageModelSettings, "reasoning_effort"),
                key="reasoning_effort",
                use_selectbox=True,
                allow_none=True,
            )
