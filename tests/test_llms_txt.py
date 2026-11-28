import re

import pytest
from furl import furl
from starlette.testclient import TestClient

from daras_ai_v2 import settings
from routers.root import HTML_COMMENT_RE, LLMS_TXT_PATH
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
    assert "\n> " in llms_txt.text
    assert "\nLast updated: " in llms_txt.text
    assert "<!--" not in llms_txt.text


def test_llms_txt_links(llms_txt):
    source_text = HTML_COMMENT_RE.sub("", LLMS_TXT_PATH.read_text())
    source_links = LINK_PATTERN.findall(source_text)
    served_links = LINK_PATTERN.findall(llms_txt.text)
    assert source_links
    assert len(served_links) == len(source_links)

    for source, served in zip(source_links, served_links):
        if source.startswith("/"):
            # pages on this site are written as paths and served under APP_BASE_URL
            assert served == str(furl(TEST_APP_BASE_URL) / source), served
        else:
            # a full url to this site would bypass APP_BASE_URL
            assert furl(source).host not in {"gooey.ai", "www.gooey.ai"}, source
            assert served == source
        assert served.startswith("https://"), served
        assert "localhost" not in served and "127.0.0.1" not in served, served
