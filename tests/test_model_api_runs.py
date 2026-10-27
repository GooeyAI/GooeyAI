from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from starlette.testclient import TestClient

from app_users.models import AppUserTransaction
from bots.models import AppUser, SavedRun, Workflow
from daras_ai_v2.all_pages import all_api_pages, all_home_pages, workflow_map
from model_api.hooks import answering_model, deduct_cost
from recipes.model_api_page import ModelApiPage
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
        "call_id": "call-1",
    }


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


@pytest.fixture
def model_api_root_pr(transactional_db):
    # force_authentication renames the default workspace's owner, after which
    # creating a root published run fails, so create it first
    return ModelApiPage.get_root_pr()


def test_model_api_runs_show_in_history(model_api_root_pr, force_authentication):
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


def make_workspace() -> tuple[Workspace, AppUser]:
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    workspace = Workspace(name="myteam", created_by=user, is_personal=True)
    workspace.create_with_owner()
    workspace.add_balance(amount=1000, invoice_id="test_topup")
    return workspace, user


def logged_call(workspace: Workspace, user: AppUser) -> dict:
    """A LiteLLM standard_logging_object, trimmed to what billing reads."""
    return {
        "model": "openai/gpt-4.1-mini",
        "model_group": "gpt-4.1-mini",
        "stream": True,
        "user_agent": "opencode/2.1.2",
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
        "startTime": 1000.0,
        "endTime": 1002.5,
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
