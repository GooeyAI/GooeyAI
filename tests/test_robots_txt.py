from starlette.testclient import TestClient

from daras_ai_v2 import settings
from server import app

client = TestClient(app)


def test_robots_txt(monkeypatch):
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://gooey.ai/")
    r = client.get("/robots.txt")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    assert r.text == "User-agent: *\nSitemap: https://gooey.ai/sitemap.xml\n"


def test_robots_txt_sitemap_is_served(db):
    r = client.get("/sitemap.xml", follow_redirects=True)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/xml")
