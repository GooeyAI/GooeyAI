from __future__ import annotations

import json
import typing
from textwrap import dedent

from django.utils.html import strip_tags

import gooey_gui as gui
from daras_ai.image_input import truncate_filename
from daras_ai_v2.gooey_builder import (
    get_builder_workflow_state,
    get_gooey_builder_photo_url,
)

if typing.TYPE_CHECKING:
    from bots.models import SavedRun
    from daras_ai_v2.base import BasePage

ASK_GOOEY_TRACEBACK_MAX_CHARS = 4000


def render_workflow_error_message(page: BasePage, err_msg: str):
    # same box as gui.error, plus an "Ask Gooey to fix" button
    with gui.component(
        "WorkflowErrorMessage",
        prompt=get_ask_gooey_fix_prompt(page.current_sr, err_msg),
        workflow_state=get_builder_workflow_state(page),
        photo_url=get_gooey_builder_photo_url(),
    ):
        gui.markdown(dedent(err_msg), unsafe_allow_html=True)


def get_ask_gooey_fix_prompt(sr: SavedRun, err_msg: str) -> str:
    prompt = (
        "This run failed with the following error. Please fix it. "
        f"\n\n{strip_tags(err_msg)}"
    )
    if sr.error_code:
        prompt += f"\n\nError code: {sr.error_code}"
    if sr.error_params:
        prompt += f"\n\nError params:\n```json\n{json.dumps(sr.error_params, indent=2, default=str)}\n```"
    err_traceback = sr.error_traceback
    if err_traceback:
        # cut from the middle - keeps the outermost call and the frame that raised
        err_traceback = truncate_filename(
            err_traceback, ASK_GOOEY_TRACEBACK_MAX_CHARS, sep="\n...\n"
        )
        prompt += f"\n\nTraceback:\n```\n{err_traceback}\n```"
    prompt += (
        "\n\nIf this is something that cannot be fixed by changing this worklfow, and needs a deeper bugfix inside our codebase, "
        "encourage them to raise an issue on our github: https://github.com/GooeyAI/GooeyAI/issues/new"
    )
    return prompt
