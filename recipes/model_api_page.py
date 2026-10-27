import typing

from pydantic import BaseModel

import gooey_gui as gui
from api_keys.models import ApiKey
from bots.models import Workflow
from daras_ai_v2.base import BasePage, StateKeys
from daras_ai_v2.exceptions import UserError
from routers.root import RecipeTabs


class ModelApiPage(BasePage):
    """
    A call made through the Model API (model_api/), recorded as a run so its
    charge shows in run history and credit usage. model_api/hooks.py records
    these runs; they're never started from this page.
    """

    title = "Model API"
    workflow = Workflow.MODEL_API
    slug_versions = ["model-api"]

    class RequestModel(BasePage.RequestModel):
        model: str | None = None
        route: str | None = None
        stream: bool | None = None
        api_key_id: int | None = None
        user_agent: str | None = None

    class ResponseModel(BaseModel):
        provider_model: str | None = None
        prompt_tokens: int = 0
        completion_tokens: int = 0
        total_tokens: int = 0
        cost_usd: float = 0
        call_id: str | None = None

    def get_tabs(self):
        return [
            tab
            for tab in super().get_tabs()
            if tab in {RecipeTabs.run, RecipeTabs.history}
        ]

    def render_selected_tab(self):
        # no examples, saved or API tabs: these runs can't be started or shared
        if self.tab == RecipeTabs.history:
            return super().render_selected_tab()
        self.render_call_details(gui.session_state)

    def render_run_preview_output(self, state: dict):
        gui.caption(call_summary(state))

    @classmethod
    def preview_input(cls, state: dict) -> str | None:
        return state.get("model")

    def run(self, state: dict) -> typing.Iterator[str | None]:
        raise UserError(
            "Model API runs record calls made with the Model API; they can't be run here."
        )
        yield

    def render_call_details(self, state: dict):
        if not state.get("call_id"):
            gui.write(
                "Calls you make with the Model API show up as runs in your history, "
                "with their tokens and cost."
            )
            return

        api_key = ApiKey.objects.filter(id=state.get("api_key_id")).first()
        rows = [
            ("Model", model_label(state)),
            ("Tokens", tokens_label(state)),
            (
                "Cost",
                f"${state.get('cost_usd', 0):.6f} ({state.get('price', 0)} credits)",
            ),
            ("Duration", f"{state.get(StateKeys.run_time, 0):.1f}s"),
            ("Route", route_label(state)),
            ("API key", api_key and f"`{api_key.preview}`" or "Deleted key"),
            ("Client", state.get("user_agent") or "-"),
            ("Call ID", f"`{state['call_id']}`"),
        ]
        gui.write(
            "| | |\n| --- | --- |\n"
            + "\n".join(f"| {label} | {value} |" for label, value in rows)
        )


def call_summary(state: dict) -> str:
    return f"{model_label(state)} · {tokens_label(state)} · {state.get('price', 0)} credits"


def model_label(state: dict) -> str:
    model, provider_model = state.get("model"), state.get("provider_model")
    if provider_model and provider_model != model:
        return f"{model} ({provider_model})"
    return model or "-"


def tokens_label(state: dict) -> str:
    return (
        f"{state.get('prompt_tokens', 0):,} in, "
        f"{state.get('completion_tokens', 0):,} out"
    )


def route_label(state: dict) -> str:
    route = state.get("route") or "-"
    if state.get("stream"):
        return f"{route} (streamed)"
    return route
