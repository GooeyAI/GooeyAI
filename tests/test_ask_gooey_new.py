import uuid
from unittest.mock import patch

import pytest
from furl import furl
from starlette.testclient import TestClient

from bots.models import BotIntegration, Platform, PublishedRun, SavedRun, Workflow
from daras_ai_v2.base import BasePage
from recipes.VideoBots import VideoBotsPage
from server import app

client = TestClient(app)


@pytest.fixture
def video_bots_root(transactional_db):
    # created before force_authentication renames the default workspace's owner,
    # which would make the lazy create collide with that user
    return VideoBotsPage.get_root_pr()


@pytest.fixture
def builder(video_bots_root, force_authentication):
    """A configured Builder deployment, with runs never actually executed."""
    user = force_authentication
    workspace = user.get_or_create_personal_workspace()[0]
    pr = PublishedRun.objects.create_with_version(
        workflow=Workflow.VIDEO_BOTS,
        published_run_id=uuid.uuid4().hex[:12],
        saved_run=SavedRun.objects.create(
            workflow=Workflow.VIDEO_BOTS,
            run_id=uuid.uuid4().hex,
            uid=user.uid,
            workspace=workspace,
        ),
        user=user,
        workspace=workspace,
        title="builder",
    )
    bi = BotIntegration.objects.create(
        platform=Platform.WEB, name="builder", published_run=pr
    )
    with (
        patch("daras_ai_v2.settings.GOOEY_BUILDER_INTEGRATION_ID", bi.id),
        patch.object(BasePage, "call_runner_task", return_value=None),
    ):
        yield pr


def test_q_starts_a_builder_conversation(builder, force_authentication):
    r = client.get(
        "/new/?q=%20Build%20a%20bot%20for%20farmers%20", follow_redirects=False
    )

    assert r.is_redirect, r.text
    location = furl(r.headers["location"])
    # a path, so the visitor stays on whichever host they came in on
    assert not location.host
    assert str(location.path).startswith("/new/build-a-bot-for-farmers-")
    sr = SavedRun.objects.get(run_id=location.path.segments[-2].rsplit("-", 1)[1])
    assert sr.surface == SavedRun.Surface.builder_prompt
    assert sr.uid == force_authentication.uid
    assert sr.state["input_prompt"] == "Build a bot for farmers"


def test_blank_q_just_shows_the_page(builder):
    r = client.get("/new/?q=%20%20", follow_redirects=False)

    assert r.is_success, r.text
    assert not _builder_prompts()


def test_draft_fills_in_without_sending(builder):
    r = client.get("/new/?draft=Build%20a%20bot", follow_redirects=False)

    assert r.is_success, r.text
    ask_gooey = _find_node(r.json()["children"], "AskGooeyNew")
    assert ask_gooey["props"]["initialPrompt"] == "Build a bot"
    assert not _builder_prompts()


def test_q_waits_for_login(builder):
    from auth.auth_backend import authlocal

    authlocal.clear()

    r = client.get("/new/?q=Build%20a%20bot", follow_redirects=False)

    assert r.is_redirect, r.text
    location = furl(r.headers["location"])
    assert str(location.path) == "/login/"
    # signing in comes back here with the prompt, which is sent then
    next_url = furl(location.args["next"])
    assert str(next_url.path) == "/new/"
    assert next_url.args["q"] == "Build a bot"
    assert not _builder_prompts()


def _builder_prompts():
    return list(SavedRun.objects.filter(surface=SavedRun.Surface.builder_prompt))


def _find_node(children: list[dict], name: str) -> dict | None:
    for node in children:
        if node["name"] == name:
            return node
        if found := _find_node(node.get("children") or [], name):
            return found
    return None
