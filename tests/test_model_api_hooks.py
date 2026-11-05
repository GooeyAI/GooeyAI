import asyncio
from unittest.mock import patch

import pytest
from litellm.proxy._types import ProxyException, UserAPIKeyAuth

from bots.models import AppUser
from daras_ai_v2 import settings
from model_api import hooks
from workspaces.models import Workspace


def test_pre_call_hook_serves_listed_model_to_paying_workspace(transactional_db):
    key = make_key(balance=100, is_paying=True)
    data = {"model": "gpt-4.1-mini"}
    assert run_pre_call_hook(key, data) is data


def test_pre_call_hook_accepts_openai_prefixed_model_id(transactional_db):
    key = make_key(balance=100, is_paying=True)
    data = {"model": "openai/gpt-4.1-mini"}
    assert run_pre_call_hook(key, data) is data


def test_pre_call_hook_refuses_unlisted_model(transactional_db):
    key = make_key(balance=100, is_paying=True)
    with pytest.raises(ProxyException) as e:
        run_pre_call_hook(key, {"model": "gpt-6-astra"})
    assert e.value.code == "400"
    assert e.value.type == "invalid_request_error"


def test_pre_call_hook_refuses_free_workspace_with_free_credits(transactional_db):
    key = make_key(balance=1000, is_paying=False)
    with pytest.raises(ProxyException) as e:
        run_pre_call_hook(key, {"model": "gpt-4.1-mini"})
    assert e.value.code == "402"
    assert e.value.type == "payment_required"


def test_pre_call_hook_refuses_paying_workspace_without_credits(transactional_db):
    key = make_key(balance=0, is_paying=True)
    with pytest.raises(ProxyException) as e:
        run_pre_call_hook(key, {"model": "gpt-4.1-mini"})
    assert e.value.code == "402"
    assert e.value.type == "insufficient_credits"


def run_pre_call_hook(key: UserAPIKeyAuth, data: dict) -> dict:
    with patch.object(settings, "MODEL_API_ALLOWED_MODELS", ["gpt-4.1-mini"]):
        return asyncio.run(
            hooks.gooey_model_api.async_pre_call_hook(key, None, data, "acompletion")
        )


def make_key(balance: int, is_paying: bool) -> UserAPIKeyAuth:
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    workspace = Workspace(
        name="myteam",
        created_by=user,
        is_personal=True,
        balance=balance,
        is_paying=is_paying,
    )
    workspace.create_with_owner()
    return UserAPIKeyAuth(
        metadata={"gooey_workspace_id": workspace.id, "gooey_user_id": user.id}
    )
