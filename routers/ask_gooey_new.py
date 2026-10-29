import fastapi
from django.utils.text import slugify
from furl import furl
from starlette.requests import Request

import gooey_gui as gui
from bots.models import SavedRun
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.gooey_builder import (
    GooeyBuilderSendMessage,
    can_launch_gooey_builder,
    gooey_builder_send_message,
    render_standalone_gooey_builder,
)
from daras_ai_v2.meta_content import raw_build_meta_tags
from routers.base_auth import get_login_url
from routers.custom_api_router import CustomAPIRouter
from routers.root import get_og_url_path, sidebar_page_wrapper
from workspaces.models import Workspace

META_TITLE = "Ask Gooey: Ideas to Agents"
META_DESCRIPTION = "Build a Gooey.AI agent for impact in 1500+ languages with the best sovereign and private models for education, agriculture or health."

app = CustomAPIRouter()


@gui.route(app, "/new/")
def ask_gooey_new_page(request: Request):
    if not request.user or request.user.is_anonymous:
        raise gui.RedirectException(get_login_url(request))

    # a prompt sent here by link (e.g. the home page's static/js/ask_gooey_embed.js)
    # starts its builder conversation straight away, as if sent from the box below
    prompt = (request.query_params.get("q") or "").strip()
    if prompt and can_launch_gooey_builder(request, None):
        run_url = gooey_builder_send_message(
            request, GooeyBuilderSendMessage(input_data=dict(input_prompt=prompt))
        )
        raise gui.RedirectException(str(furl(run_url).set(origin=None)))

    with sidebar_page_wrapper(request, full_width_content=True):
        render_ask_gooey_new(
            request=request,
            workspace=None,
            # filled in but not sent: the embed's attach button lands here, to add
            # files before sending
            initial_prompt=request.query_params.get("draft") or "",
        )

    return {
        "meta": build_meta_tags(url=get_og_url_path(request)),
    }


@gui.route(app, "/new/{title}-{run_id}/")
def gooey_builder_run_route(request: Request, title: str, run_id: str):
    """Renders only the gooey builder chat for a builder prompt run, without
    the associated workflow. Redirects to the child workflow whenever the
    builder updates it."""
    if not request.user or request.user.is_anonymous:
        raise gui.RedirectException(get_login_url(request))

    try:
        builder_sr = SavedRun.objects.get(
            run_id=run_id, surface=SavedRun.Surface.builder_prompt
        )
    except SavedRun.DoesNotExist:
        raise fastapi.HTTPException(status_code=404)
    # the run_id is a capability: any signed-in holder may read it, and sending forks it

    # the builder embed sets this flag on "new conversation"; the standalone
    # page is tied to one builder run, so start fresh from the hero page
    if gui.session_state.pop("builderOnNewConversation", None):
        raise gui.RedirectException(get_route_path(ask_gooey_new_page))

    with (
        sidebar_page_wrapper(request, full_width_content=True),
        gui.div(
            className="w-100 d-flex flex-column",
            style={"height": "100dvh"},
        ),
    ):
        render_standalone_gooey_builder(
            event_key="gooey-builder",
            request=request,
            builder_sr=builder_sr,
        )

    return {
        "meta": build_meta_tags(url=get_og_url_path(request)),
    }


def get_gooey_builder_run_url(builder_sr: SavedRun) -> str:
    slug = (
        slugify(
            truncate_text_words(builder_sr.state.get("input_prompt") or "", maxlen=40)
        )
        or "untitled"
    )
    return str(
        furl(settings.APP_BASE_URL)
        / get_route_path(
            gooey_builder_run_route, dict(title=slug, run_id=builder_sr.run_id)
        )
    )


def build_meta_tags(url: str):
    return raw_build_meta_tags(
        url=url,
        title=META_TITLE,
        description=META_DESCRIPTION,
    )


def render_ask_gooey_new(
    request: fastapi.Request,
    workspace: Workspace | None,
    title: str = "What will you build today?",
    highlight: str = "",
    placeholder: str = "Build an agent for farmers in Kenya",
    initial_prompt: str = "",
):
    """Centered "What can I help with?" hero prompt for /explore.

    On submit it starts a builder-only conversation (no workflow attached) and
    the React component navigates the user to the standalone builder page at
    ``/new/<title>-<run_id>/``. ``initial_prompt`` is only filled in, not sent.
    """
    if not can_launch_gooey_builder(request, workspace):
        return
    gui.component(
        "AskGooeyNew",
        title=title,
        highlight=highlight,
        placeholder=placeholder,
        initialPrompt=initial_prompt,
    )
