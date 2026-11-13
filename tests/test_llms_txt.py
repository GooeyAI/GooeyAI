import re

import pytest
from starlette.testclient import TestClient

from daras_ai_v2 import settings
from daras_ai_v2.github_tools import GITHUB_REPO
from server import app

client = TestClient(app)

TEST_APP_BASE_URL = "https://llms-txt.example.test"
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")


@pytest.fixture
def llms_txt(monkeypatch):
    # APP_BASE_URL defaults to localhost, so point it somewhere else to prove
    # the links are built from the setting when the request is served.
    monkeypatch.setattr(settings, "APP_BASE_URL", TEST_APP_BASE_URL)
    r = client.get("/llms.txt")
    assert r.status_code == 200, r.text
    return r


def test_llms_txt_response(llms_txt):
    assert llms_txt.headers["content-type"] == "text/plain; charset=utf-8"
    assert "max-age=3600" in llms_txt.headers["cache-control"]
    assert llms_txt.text.startswith("# ")
    assert "\nLast updated: " in llms_txt.text


def test_llms_txt_links(llms_txt):
    links = LINK_PATTERN.findall(llms_txt.text)
    assert links

    # the only hosts allowed besides this site, none of them typed into the page
    external_prefixes = (settings.DOCS_URL, settings.BLOG_URL, GITHUB_REPO)
    site_links = [url for url in links if not url.startswith(external_prefixes)]
    assert site_links

    for url in links:
        assert url.startswith("https://"), url
        assert "localhost" not in url and "127.0.0.1" not in url, url
    for url in site_links:
        assert url.startswith(TEST_APP_BASE_URL + "/"), url
