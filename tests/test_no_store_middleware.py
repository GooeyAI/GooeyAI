from starlette.testclient import TestClient

from app_users.models import AppUser
from auth.auth_backend import authlocal
from server import app

client = TestClient(app)

GUI_ROUTE_HEADERS = {"X-GOOEY-GUI-ROUTE": "1"}


def test_signed_in_pages_are_not_cached(db_fixtures, force_authentication):
    r = client.post("/explore/", json={}, headers=GUI_ROUTE_HEADERS)
    assert r.status_code == 200, r.text
    assert r.headers.get("cache-control") == "no-store"


def test_signed_in_static_files_keep_default_caching(db_fixtures, force_authentication):
    r = client.get("/static/js/auth.js")
    assert r.status_code == 200
    assert "cache-control" not in r.headers


def test_signed_out_pages_keep_default_caching(db_fixtures):
    r = client.post("/explore/", json={}, headers=GUI_ROUTE_HEADERS)
    assert r.status_code == 200, r.text
    assert "cache-control" not in r.headers


def test_anonymous_user_pages_keep_default_caching(db_fixtures):
    authlocal.append(AppUser.objects.create(uid="anon-no-store", is_anonymous=True))
    try:
        r = client.post("/explore/", json={}, headers=GUI_ROUTE_HEADERS)
    finally:
        authlocal.clear()
    assert r.status_code == 200, r.text
    assert "cache-control" not in r.headers
