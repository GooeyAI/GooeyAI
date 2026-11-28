from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from starlette.testclient import TestClient

from app_users.models import AppUserTransaction
from bots.models import AppUser, MessageThread, SavedRun, Workflow
from daras_ai_v2.all_pages import all_api_pages, all_home_pages, workflow_map
from model_api.hooks import answering_model, client_session_id, deduct_cost
from model_api.sessions import display_title
from recipes.model_api_page import ModelApiPage
from recipes.VideoBots import VideoBotsPage
from server import app
from widgets.credit_usage import _month_range, _monthly_usage_by_workflow, _this_month
from workspaces.models import Workspace


def test_deduct_cost_records_one_run_per_call(transactional_db):
    workspace, user = make_workspace()
    logged = logged_call(workspace, user)

    with patch("daras_ai_v2.settings.ADDON_CREDITS_PER_DOLLAR", 100):
        async_to_sync(deduct_cost)(logged, "call-1", 0.0123)
        async_to_sync(deduct_cost)(logged, "call-1", 0.0123)  # a repeated callback

    workspace.refresh_from_db()
    assert workspace.balance == 1000 - 2
    run = SavedRun.objects.get(workflow=Workflow.MODEL_API)
    assert run.run_id == "call-1"
    assert run.transaction == AppUserTransaction.objects.get(
        invoice_id="gooey_model_api_call-1"
    )
    assert run.price == 2
    assert run.workspace == workspace
    assert run.uid == user.uid
    assert run.surface == SavedRun.Surface.api
    assert run.run_time.total_seconds() == 2.5
    assert run.state == {
        "model": "gpt-4.1-mini",
        "provider_model": "gpt-4.1-mini-2025-04-14",
        "route": "/v1/chat/completions",
        "stream": True,
        "api_key_id": 7,
        "user_agent": "opencode/2.1.2",
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
        "cost_usd": 0.0123,
        "started_at": 1000.0,
        "ended_at": 1002.5,
        "call_id": "call-1",
    }
    assert run.message_thread is None  # no session id


def test_answering_model_falls_back_to_the_routed_model():
    logged = {"model": "openai/gpt-4.1-mini", "response": None}
    assert answering_model(logged) == "gpt-4.1-mini"


def test_free_calls_get_no_run(transactional_db):
    workspace, user = make_workspace()

    async_to_sync(deduct_cost)(logged_call(workspace, user), "call-1", 0.0)

    assert not SavedRun.objects.filter(workflow=Workflow.MODEL_API).exists()


def test_credit_usage_shows_model_api_charges(transactional_db):
    workspace, user = make_workspace()
    with patch("daras_ai_v2.settings.ADDON_CREDITS_PER_DOLLAR", 100):
        async_to_sync(deduct_cost)(logged_call(workspace, user), "call-1", 0.03)
        this_month = _this_month()
        series = _monthly_usage_by_workflow(
            workspace, _month_range(this_month, this_month)
        )

    assert [(s.id, s.title, s.usd) for s in series] == [
        (Workflow.MODEL_API.short_slug, "Model API", [0.03])
    ]


def test_calls_in_a_session_share_one_thread(transactional_db):
    workspace, user = make_workspace()
    with patch("daras_ai_v2.settings.ADDON_CREDITS_PER_DOLLAR", 100):
        # callbacks out of order: the later call is recorded first
        for call_id, start in [("call-2", 1010.0), ("call-1", 1000.0)]:
            async_to_sync(deduct_cost)(
                logged_call(workspace, user, start=start), call_id, 0.0123, "ses_1"
            )

    thread = MessageThread.objects.get()
    assert display_title(thread) == "OpenCode session"
    assert sorted(thread.saved_runs.values_list("run_id", flat=True)) == [
        "call-1",
        "call-2",
    ]
    assert thread.first_run.run_id == "call-1"
    assert thread.last_run.run_id == "call-2"
    totals = thread.last_run.state["session"]
    assert totals | {"cost_usd": None} == {
        "calls": 2,
        "credits": 4,
        "prompt_tokens": 2400,
        "completion_tokens": 600,
        "cost_usd": None,
        "started_at": 1000.0,
        "ended_at": 1012.5,
        "models": ["gpt-4.1-mini"],
    }
    assert totals["cost_usd"] == pytest.approx(0.0246)


def test_sessions_are_scoped_to_the_workspace(transactional_db):
    for uid in ["user_a", "user_b"]:
        workspace, user = make_workspace(uid)
        async_to_sync(deduct_cost)(
            logged_call(workspace, user), f"call-{uid}", 0.0123, "ses_1"
        )

    assert MessageThread.objects.count() == 2
    for thread in MessageThread.objects.all():
        assert thread.saved_runs.count() == 1


@pytest.mark.parametrize(
    "litellm_params, session_id",
    [
        ({"metadata": {"session_id": "ses_1"}}, "ses_1"),
        ({"litellm_metadata": {"session_id": "ses_1"}}, "ses_1"),
        # LiteLLM fills litellm_session_id from a W3C traceparent, which
        # clients reuse across sessions
        ({"litellm_session_id": "4bf92f35", "metadata": {}}, None),
        ({}, None),
    ],
)
def test_client_session_id(litellm_params, session_id):
    assert client_session_id({"litellm_params": litellm_params}) == session_id


@pytest.fixture
def root_prs(transactional_db):
    # force_authentication renames the default workspace's owner, after which
    # creating a root published run fails, so create them first
    return [ModelApiPage.get_root_pr(), VideoBotsPage.get_root_pr()]


def test_history_lists_a_session_once(root_prs, force_authentication):
    workspace = force_authentication.get_or_create_personal_workspace()[0]
    workspace.add_balance(amount=1000, invoice_id="test_topup")
    for call_id, start, session_id in [
        ("call-1", 1000.0, "ses_1"),
        ("call-2", 1010.0, "ses_1"),
        ("call-3", 1020.0, None),
        ("call-4", 1030.0, None),
    ]:
        async_to_sync(deduct_cost)(
            logged_call(workspace, force_authentication, start=start),
            call_id,
            0.0123,
            session_id,
        )

    history = post_page("/history/api/")
    assert "run_id=call-1" not in history
    assert "run_id=call-2" in history
    assert "OpenCode session" in history
    assert "2 calls · 3,000 tokens" in history
    # calls without a session id stay one entry each
    assert "run_id=call-3" in history
    assert "run_id=call-4" in history

    run_page = post_page(f"/model-api/?run_id=call-1&uid={force_authentication.uid}")
    assert "OpenCode session" in run_page
    assert "2,400 in, 600 out" in run_page  # the session
    assert "1,200 in, 300 out" in run_page  # this call


def test_history_keeps_agent_runs_per_message(root_prs, force_authentication):
    workspace = force_authentication.get_or_create_personal_workspace()[0]
    runs = [
        SavedRun.objects.create(
            workflow=Workflow.VIDEO_BOTS,
            run_id=f"agent-{i}",
            uid=force_authentication.uid,
            workspace=workspace,
            surface=SavedRun.Surface.api,
        )
        for i in range(2)
    ]
    thread = MessageThread.objects.create(first_run=runs[0], last_run=runs[1])
    SavedRun.objects.filter(id__in=[r.id for r in runs]).update(message_thread=thread)

    history = post_page("/history/api/")
    assert "run_id=agent-0" in history
    assert "run_id=agent-1" in history


def test_model_api_runs_show_in_history(root_prs, force_authentication):
    workspace = force_authentication.get_or_create_personal_workspace()[0]
    workspace.add_balance(amount=1000, invoice_id="test_topup")
    async_to_sync(deduct_cost)(
        logged_call(workspace, force_authentication), "call-1", 0.0123
    )

    history = post_page("/history/api/")
    assert "run_id=call-1" in history
    assert "Model API" in history

    run_page = post_page(f"/model-api/?run_id=call-1&uid={force_authentication.uid}")
    assert "call-1" in run_page
    assert "1,200 in, 300 out" in run_page
    assert "/v1/chat/completions (streamed)" in run_page


def test_model_api_is_not_an_api_or_explore_page():
    assert workflow_map[Workflow.MODEL_API] is ModelApiPage
    assert ModelApiPage not in all_api_pages
    assert ModelApiPage not in all_home_pages
    assert not [route.path for route in app.routes if "model-api" in route.path]


def make_workspace(uid: str = "test_user") -> tuple[Workspace, AppUser]:
    user = AppUser.objects.create(uid=uid, is_anonymous=False)
    workspace = Workspace(name="myteam", created_by=user, is_personal=True)
    workspace.create_with_owner()
    workspace.add_balance(amount=1000, invoice_id="test_topup")
    return workspace, user


def logged_call(workspace: Workspace, user: AppUser, start: float = 1000.0) -> dict:
    """A LiteLLM standard_logging_object, trimmed to what billing reads."""
    return {
        "model": "openai/gpt-4.1-mini",
        "model_group": "gpt-4.1-mini",
        "stream": True,
        "user_agent": "opencode/2.1.2",
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
        "startTime": start,
        "endTime": start + 2.5,
        "messages": [{"role": "user", "content": "never stored"}],
        "response": {"model": "gpt-4.1-mini-2025-04-14", "choices": ["never stored"]},
        "metadata": {
            "user_api_key_request_route": "/v1/chat/completions",
            "user_api_key_auth_metadata": {
                "gooey_workspace_id": workspace.id,
                "gooey_user_id": user.id,
                "gooey_api_key_id": 7,
            },
        },
    }


def post_page(url: str) -> str:
    client = TestClient(app)
    for _ in range(10):
        r = client.post(url, json={}, follow_redirects=False)
        if r.is_redirect:
            url = r.headers["Location"]
            continue
        assert r.is_success, r.content
        return str(r.json())
    raise AssertionError(f"Too many redirects: {url}")
