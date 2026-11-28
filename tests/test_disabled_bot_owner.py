from types import SimpleNamespace

import pytest
from furl import furl
from starlette.testclient import TestClient

from app_users.models import AppUser
from auth.token_authentication import DISABLED_ACCOUNT_ERROR_MESSAGE
from bots.models import BotIntegration, Platform
from bots.models.convo_msg import ConvoBlockedStatus
from daras_ai_v2 import bots
from server import app
from workspaces.models import Workspace

client = TestClient(app)


@pytest.fixture
def owner(transactional_db):
    return AppUser.objects.create(uid="owner_uid", is_anonymous=False)


@pytest.fixture
def bi(owner):
    workspace = Workspace.objects.create(created_by=owner, is_personal=True)
    return BotIntegration.objects.create(
        name="test bot", platform=Platform.WEB, created_by=owner, workspace=workspace
    )


def test_stream_rejects_disabled_owner(bi, owner):
    owner.is_disabled = True
    owner.save()

    r = client.post(
        "/v3/integrations/stream/",
        json={"integration_id": bi.api_integration_id(), "input_text": "hi"},
        follow_redirects=False,
    )
    assert r.is_success, r.text

    r = client.get(str(furl(r.headers["Location"]).path), follow_redirects=False)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == DISABLED_ACCOUNT_ERROR_MESSAGE
    assert not bi.conversations.exists()


def test_msg_handler_skips_disabled_owner(bi, owner, monkeypatch):
    calls = []
    monkeypatch.setattr(bots, "msg_handler_raw", calls.append)
    bot = SimpleNamespace(
        convo=SimpleNamespace(blocked_status=ConvoBlockedStatus.NORMAL), bi=bi
    )

    owner.is_disabled = True
    owner.save()
    bots.msg_handler(bot)
    assert calls == []


def test_is_owner_disabled(bi, owner):
    assert not bi.is_owner_disabled()

    # a different (disabled) creator inside an active workspace
    creator = AppUser.objects.create(
        uid="creator_uid", is_anonymous=False, is_disabled=True
    )
    bi.created_by = creator
    assert bi.is_owner_disabled()

    # an active creator inside a disabled owner's workspace
    creator.is_disabled = False
    owner.is_disabled = True
    bi.workspace.created_by = owner
    assert bi.is_owner_disabled()

    bi.created_by = None
    bi.workspace = None
    assert not bi.is_owner_disabled()
