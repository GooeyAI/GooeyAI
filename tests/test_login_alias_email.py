from time import time
from unittest import mock

import pytest
from starlette.testclient import TestClient

from app_users.models import AppUser
from daras_ai_v2 import settings
from routers.firebase_auth import alias_email_login_error
from server import app


def _owner():
    return AppUser.objects.create(
        uid="uid-owner", email="janedoe@gmail.com", balance=0, is_anonymous=False
    )


@pytest.mark.django_db
def test_alias_email_login_error():
    _owner()
    # aliases of a taken inbox under another uid are refused
    err = alias_email_login_error("uid-alias", "ja.ne.doe+x@googlemail.com")
    assert err and "janedoe@gmail.com" in err
    # the owner signing in as themselves, canonical or not, is fine
    assert alias_email_login_error("uid-owner", "janedoe@gmail.com") is None
    assert alias_email_login_error("uid-owner", "jane.doe@gmail.com") is None
    # an alias of an inbox that has no account yet is fine
    assert alias_email_login_error("uid-new", "jo.hn@gmail.com") is None
    # non-gmail and phone-only sign-ins are untouched
    assert alias_email_login_error("uid-new", "j.doe@hotmail.com") is None
    assert alias_email_login_error("uid-new", None) is None


@pytest.mark.skipif(
    not settings.ENABLE_FIREBASE_AUTH, reason="Firebase auth is not enabled"
)
@pytest.mark.django_db(transaction=True)
def test_login_with_alias_of_taken_inbox_shows_error_and_sets_no_session():
    _owner()
    client = TestClient(app)
    claims = dict(uid="uid-alias", email="jane.doe@gmail.com", auth_time=time())
    with (
        mock.patch("routers.firebase_auth.auth.verify_id_token", return_value=claims),
        mock.patch("routers.firebase_auth.auth.create_session_cookie") as create_cookie,
    ):
        r = client.post(
            "/login/?next=/copilot/", data={"idToken": "x"}, follow_redirects=False
        )
        # must be a redirect: the gooey-gui proxy swallows any other POST response
        assert r.status_code == 303, r.text
        assert r.headers["location"] == "/login/?next=%2Fcopilot%2F"
        create_cookie.assert_not_called()
        page = client.get(r.headers["location"])
    assert "already has an account as janedoe@gmail.com" in page.text
    # ?next is kept for the retry
    assert 'href="/login/sso/?next=%2Fcopilot%2F"' in page.text
    # the message is shown once, then cleared
    assert "already has an account" not in client.get("/login/").text
    assert "firebase_session" not in client.cookies
    assert not AppUser.objects.filter(uid="uid-alias").exists()
