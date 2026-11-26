import pytest
from starlette.testclient import TestClient

import gooey_gui as gui
from api_keys.models import ApiKey
from app_users.models import AppUser
from auth.auth_backend import authlocal
from bots.models import RetentionPolicy, SavedRun
from daras_ai_v2.manage_api_keys_widget import (
    CREATE_API_KEY_BUTTON_KEY,
    manage_api_keys,
)
from gooey_gui.core.renderer import NestingCtx, RenderTreeNode
from recipes.Translation import TranslationPage
from routers.api import create_new_run
from server import app

client = TestClient(app)


@pytest.fixture
def user(transactional_db):
    user = AppUser.objects.create(
        uid="paid-only-features-user",
        email="paid-only-features@example.com",
        is_anonymous=False,
        balance=10**9,
        disable_rate_limits=True,
    )
    # the API's test auth runs every request as this user
    authlocal.append(user)
    try:
        yield user
    finally:
        authlocal.clear()


@pytest.fixture
def workspace(user):
    # ...in their personal workspace
    workspace, _ = user.get_or_create_personal_workspace()
    return workspace


def test_free_workspace_cannot_use_delete_retention_policy(workspace, user):
    _set_paying(workspace, False)

    for endpoint in [_sync_endpoint(), _async_endpoint()]:
        r = _post_run(endpoint, retention_policy="delete")
        assert r.status_code == 402, r.text
        assert "only available to paid workspaces" in r.json()["detail"]["error"]

    # rejected before a run is created, so nothing is stored for this user
    assert not SavedRun.objects.filter(uid=user.uid).exists()


def test_free_workspace_can_still_keep_runs(workspace, mock_celery_tasks):
    _set_paying(workspace, False)

    for retention_policy in [None, "keep"]:
        r = _post_run(_sync_endpoint(), retention_policy=retention_policy)
        assert r.status_code == 200, r.text


def test_paid_workspace_can_use_delete_retention_policy(workspace, mock_celery_tasks):
    _set_paying(workspace, True)

    r = _post_run(_sync_endpoint(), retention_policy="delete")
    assert r.status_code == 200, r.text

    sr = SavedRun.objects.get(run_id=r.json()["id"])
    assert sr.retention_policy == RetentionPolicy.delete
    assert sr.state == {}


def test_create_new_run_rejects_delete_for_free_workspace(workspace, user):
    from fastapi import HTTPException

    _set_paying(workspace, False)
    with pytest.raises(HTTPException) as exc_info:
        create_new_run(
            page_cls=TranslationPage,
            query_params={},
            retention_policy=RetentionPolicy.delete,
            current_user=user,
            workspace=workspace,
            request_body={},
        )
    assert exc_info.value.status_code == 402


def test_free_workspace_cannot_create_api_key(workspace, user):
    _set_paying(workspace, False)

    _press_create_api_key(workspace, user)

    assert not ApiKey.objects.filter(workspace=workspace).exists()


def test_paid_workspace_can_create_api_key(workspace, user):
    _set_paying(workspace, True)

    _press_create_api_key(workspace, user)

    assert ApiKey.objects.filter(workspace=workspace).count() == 1


def _set_paying(workspace, is_paying: bool):
    workspace.is_paying = is_paying
    workspace.save(update_fields=["is_paying"])


def _sync_endpoint() -> str:
    return f"/v2/{TranslationPage.slug_versions[0]}/"


def _async_endpoint() -> str:
    return f"/v3/{TranslationPage.slug_versions[0]}/async/"


def _post_run(endpoint: str, retention_policy: str | None):
    state = TranslationPage.get_root_pr().saved_run.state
    body = TranslationPage.get_example_request(state)[1]
    if retention_policy:
        body["settings"] = {"retention_policy": retention_policy}
    return client.post(
        endpoint,
        json=body,
        headers={"Authorization": "Token None"},
        follow_redirects=False,
    )


def _press_create_api_key(workspace, user):
    gui.set_session_state({CREATE_API_KEY_BUTTON_KEY: True})
    with NestingCtx(RenderTreeNode("root")):
        manage_api_keys(workspace=workspace, user=user)
