import uuid
from unittest.mock import patch

import pytest
from furl import furl
from starlette.testclient import TestClient

from app_users.models import AppUser
from bots.models import BotIntegration, Platform, PublishedRun, SavedRun, Workflow
from bots.models.message_thread import MessageThread
from daras_ai_v2 import exceptions
from daras_ai_v2.base import BasePage
from recipes.VideoBots import VideoBotsPage
from server import app
from widgets.workflow_queries import recent_run_ids

client = TestClient(app)

SEND_MESSAGE = "/__/gooey-builder/send-message"
CREDITS_CARD = "gooey-builder-insufficient-credits"
OWNERS_REDIRECT = "https://gooey.ai/owners-workflow/"


@pytest.fixture
def video_bots_root(transactional_db):
    # created before force_authentication renames the default workspace's owner,
    # which would make the lazy create collide with that user
    return VideoBotsPage.get_root_pr()


@pytest.fixture
def builder(video_bots_root, force_authentication):
    """A configured Builder deployment, with runs never actually executed."""
    pr = _make_published_run(force_authentication, title="builder")
    bi = BotIntegration.objects.create(
        platform=Platform.WEB, name="builder", published_run=pr
    )
    with (
        patch("daras_ai_v2.settings.GOOEY_BUILDER_INTEGRATION_ID", bi.id),
        patch.object(BasePage, "call_runner_task", return_value=None),
    ):
        yield pr


@pytest.fixture
def non_admin():
    with patch("daras_ai_v2.settings.ADMIN_EMAILS", []):
        yield


@pytest.fixture
def owner(transactional_db):
    return AppUser.objects.create(uid="owner-uid", is_anonymous=False, balance=1000)


def test_owner_continues_the_same_thread(builder, force_authentication, non_admin):
    source = _make_conversation(builder, user=force_authentication)

    r = _send(builder_run_url=source.get_app_url())

    assert r.status_code == 200, r.text
    new_sr = _sr_from_url(r.json())
    thread = source.message_thread
    thread.refresh_from_db()
    assert new_sr.message_thread_id == thread.id
    assert thread.last_run_id == new_sr.id


def test_admin_is_not_blocked_and_leaves_the_source_alone(
    builder, force_authentication, owner
):
    source = _make_conversation(builder, user=owner)
    before = _snapshot(source)

    r = _send(builder_run_url=source.get_app_url())

    assert r.status_code == 200, r.text
    assert _sr_from_url(r.json()).uid == force_authentication.uid
    assert _snapshot(source) == before


def test_agent_viewer_forks_with_copied_history(
    builder, force_authentication, non_admin, owner
):
    user = force_authentication
    source = _make_conversation(builder, user=owner)
    workflow_sr = _make_workflow_child(source)
    before = _snapshot(source)

    r = _send(
        workflow_url=workflow_sr.get_app_url(),
        builder_run_url=source.get_app_url(),
    )

    assert r.status_code == 200, r.text
    child = _sr_from_url(r.json())
    workspace = user.get_or_create_personal_workspace()[0]
    assert (child.uid, child.workspace_id) == (user.uid, workspace.id)
    assert child.surface == SavedRun.Surface.builder_child
    fork = child.parent_builder_saved_run
    _assert_is_fork(fork, source, user)
    assert _history(fork) == ["earlier", "earlier reply", "Hi there", "hello back"]
    assert fork.state["input_prompt"] == "follow up"
    assert _snapshot(source) == before
    # the owner's workflow run is cloned, never written to
    workflow_sr.refresh_from_db()
    assert workflow_sr.parent_builder_saved_run_id == source.id
    assert child.id in recent_run_ids(
        user, workspace, limit=10, include_builder_runs=True
    )


def test_new_link_viewer_forks_into_a_standalone_thread(
    builder, force_authentication, non_admin, owner
):
    user = force_authentication
    source = _make_conversation(builder, user=owner)
    before = _snapshot(source)

    r = _send(builder_run_url=source.get_app_url())

    assert r.status_code == 200, r.text
    assert furl(r.json()).path.segments[0] == "new"
    fork = _sr_from_url(r.json())
    _assert_is_fork(fork, source, user)
    assert _history(fork) == ["earlier", "earlier reply", "Hi there", "hello back"]
    assert _snapshot(source) == before
    workspace = user.get_or_create_personal_workspace()[0]
    assert fork.id in recent_run_ids(
        user, workspace, limit=10, include_builder_runs=True
    )


def test_viewer_cannot_pick_the_published_run_through_the_url(
    builder, force_authentication, non_admin, owner
):
    source = _make_conversation(builder, user=owner)
    other_pr = _make_published_run(owner, title="someone else's bot")
    spoofed = furl(source.get_app_url()).set(path=furl(other_pr.get_app_url()).path)

    r = _send(builder_run_url=str(spoofed))

    assert r.status_code == 200, r.text
    fork = _sr_from_url(r.json())
    assert fork.parent_published_run() == builder


def test_viewer_edit_of_an_earlier_turn_forks_from_that_turn(
    builder, force_authentication, non_admin, owner
):
    source = _make_conversation(builder, user=owner)
    earlier_turn = source.message_thread.first_run
    before = _snapshot(source)

    r = _send(
        builder_run_url=source.get_app_url(),
        input_data={
            "input_prompt": "earlier, edited",
            "edit_run_url": earlier_turn.get_app_url(),
        },
    )

    assert r.status_code == 200, r.text
    fork = _sr_from_url(r.json())
    _assert_is_fork(fork, source, force_authentication)
    assert fork.state["input_prompt"] == "earlier, edited"
    # history is cut back to what came before the edited turn
    assert _history(fork) == []
    assert _snapshot(source) == before


def test_viewer_rerun_of_the_latest_turn_forks(
    builder, force_authentication, non_admin, owner
):
    source = _make_conversation(builder, user=owner)
    before = _snapshot(source)

    # a re-run names the run but sends no prompt
    r = _send(
        builder_run_url=source.get_app_url(),
        input_data={"edit_run_url": source.get_app_url()},
    )

    assert r.status_code == 200, r.text
    fork = _sr_from_url(r.json())
    _assert_is_fork(fork, source, force_authentication)
    assert fork.state["input_prompt"] == "Hi there"
    assert _history(fork) == ["earlier", "earlier reply"]
    assert _snapshot(source) == before


@pytest.mark.parametrize("is_owner", [True, False], ids=["owner", "viewer"])
def test_edit_outside_the_conversation_is_rejected(
    builder, force_authentication, non_admin, owner, is_owner
):
    # the owner case is the one only the edit check can reject
    run_owner = force_authentication if is_owner else owner
    source = _make_conversation(builder, user=run_owner)
    elsewhere = _make_sr(user=run_owner, state={"bot_script": "private"})
    run_count = SavedRun.objects.count()

    r = _send(
        builder_run_url=source.get_app_url(),
        input_data={"edit_run_url": elsewhere.get_app_url()},
    )

    assert r.status_code == 404
    assert SavedRun.objects.count() == run_count


def test_private_runs_stay_unreachable(builder, force_authentication, non_admin, owner):
    source = _make_conversation(builder, user=owner)
    other_source = _make_conversation(builder, user=owner)
    workflow_sr = _make_workflow_child(source)
    # not a Builder conversation, so not something a /new/ link can share
    private_run = _make_sr(user=owner, state={"bot_script": "private"})
    missing_run = SavedRun(workflow=Workflow.VIDEO_BOTS, run_id="gone", uid=owner.uid)
    run_count = SavedRun.objects.count()

    responses = [
        # a workflow page can only continue the conversation that built it
        _send(
            workflow_url=workflow_sr.get_app_url(),
            builder_run_url=other_source.get_app_url(),
        ),
        _send(builder_run_url=private_run.get_app_url()),
        _send(
            workflow_url=missing_run.get_app_url(),
            builder_run_url=source.get_app_url(),
        ),
        _send(builder_run_url=missing_run.get_app_url()),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404, 404]
    assert SavedRun.objects.count() == run_count


@pytest.mark.parametrize("is_owner", [True, False], ids=["owner", "viewer"])
def test_only_the_owner_takes_the_pending_redirect(
    builder, force_authentication, non_admin, owner, is_owner
):
    source = _make_conversation(
        builder, user=force_authentication if is_owner else owner
    )
    source.redirect_url = OWNERS_REDIRECT
    source.save(update_fields=["redirect_url"])

    r = client.post(_new_url(source), json={}, follow_redirects=False)

    source.refresh_from_db()
    if is_owner:
        assert r.headers.get("location") == OWNERS_REDIRECT
        assert source.redirect_url == ""
    else:
        assert r.status_code == 200, r.text
        assert source.redirect_url == OWNERS_REDIRECT


@pytest.mark.parametrize("is_owner", [True, False], ids=["owner", "viewer"])
def test_only_the_owner_sees_the_credits_card(
    builder, force_authentication, non_admin, owner, is_owner
):
    source = _make_conversation(
        builder, user=force_authentication if is_owner else owner
    )
    source.error_type = exceptions.InsufficientCredits.__name__
    source.save(update_fields=["error_type"])

    r = client.post(_new_url(source), json={}, follow_redirects=False)

    assert r.status_code == 200, r.text
    assert (CREDITS_CARD in r.text) == is_owner


def test_new_link_requires_login(builder, owner):
    from auth.auth_backend import authlocal

    source = _make_conversation(builder, user=owner)
    authlocal.clear()

    r = client.post(_new_url(source), json={}, follow_redirects=False)

    assert r.is_redirect, r.text
    assert "login" in r.headers["location"]


def _send(**body):
    body.setdefault("input_data", {"input_prompt": "follow up"})
    return client.post(SEND_MESSAGE, json=body)


def _assert_is_fork(fork: SavedRun, source: SavedRun, user: AppUser):
    assert fork.uid == user.uid
    assert fork.workspace == user.get_or_create_personal_workspace()[0]
    assert fork.surface == SavedRun.Surface.builder_prompt
    assert fork.message_thread_id != source.message_thread_id
    assert fork.message_thread.first_run_id == fork.id
    assert fork.message_thread.last_run_id == fork.id


def _history(sr: SavedRun) -> list[str]:
    return [entry["content"] for entry in sr.state.get("messages") or []]


def _snapshot(source: SavedRun) -> dict:
    """Everything a send could have changed about the source conversation."""
    source.refresh_from_db()
    thread = source.message_thread
    thread.refresh_from_db()
    return dict(
        state=source.state,
        redirect_url=source.redirect_url,
        title=thread.title,
        first_run_id=thread.first_run_id,
        last_run_id=thread.last_run_id,
        run_ids=sorted(thread.saved_runs.values_list("id", flat=True)),
    )


def _make_conversation(builder: PublishedRun, *, user: AppUser) -> SavedRun:
    """Two turns: an earlier one, and the latest one whose history records it."""
    thread = MessageThread.objects.create(title="Hi there")
    common = dict(
        user=user,
        surface=SavedRun.Surface.builder_prompt,
        parent_version=builder.versions.latest("id"),
        message_thread=thread,
    )
    earlier = _make_sr(
        **common,
        state={
            "input_prompt": "earlier",
            "raw_input_text": "earlier",
            "raw_output_text": ["earlier reply"],
        },
    )
    latest = _make_sr(
        **common,
        state={
            "messages": [
                {"role": "user", "content": "earlier"},
                {
                    "role": "assistant",
                    "content": "earlier reply",
                    "run_url": earlier.get_app_url(),
                },
            ],
            "input_prompt": "Hi there",
            "raw_input_text": "Hi there",
            "raw_output_text": ["hello back"],
            "output_text": ["hello back"],
        },
    )
    thread.first_run = earlier
    thread.last_run = latest
    thread.save(update_fields=["first_run", "last_run"])
    return latest


def _make_workflow_child(builder_sr: SavedRun) -> SavedRun:
    return _make_sr(
        user=builder_sr.created_by,
        surface=SavedRun.Surface.builder_child,
        parent_builder_saved_run=builder_sr,
    )


def _make_published_run(user: AppUser, *, title: str) -> PublishedRun:
    return PublishedRun.objects.create_with_version(
        workflow=Workflow.VIDEO_BOTS,
        published_run_id=uuid.uuid4().hex[:12],
        saved_run=_make_sr(user=user),
        user=user,
        workspace=user.get_or_create_personal_workspace()[0],
        title=title,
    )


def _make_sr(*, user: AppUser, **kwargs) -> SavedRun:
    # an explicit workspace: the field default re-creates a user force_authentication renamed
    kwargs.setdefault("workspace", user.get_or_create_personal_workspace()[0])
    kwargs.setdefault("uid", user.uid)
    kwargs.setdefault("workflow", Workflow.VIDEO_BOTS)
    kwargs.setdefault("run_id", uuid.uuid4().hex)
    return SavedRun.objects.create(**kwargs)


def _sr_from_url(url: str) -> SavedRun:
    """The run a send redirected to: a workflow run url, or a /new/{title}-{run_id}/ page."""
    f = furl(url)
    if f.path.segments[0] == "new":
        run_id = f.path.segments[1].rsplit("-", 1)[-1]
        return SavedRun.objects.get(run_id=run_id)
    return SavedRun.objects.get(run_id=f.args["run_id"], uid=f.args["uid"])


def _new_url(builder_sr: SavedRun) -> str:
    from routers.ask_gooey_new import get_gooey_builder_run_url

    return str(furl(get_gooey_builder_run_url(builder_sr)).path)
