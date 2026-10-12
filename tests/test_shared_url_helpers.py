import io
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from daras_ai import image_input
from daras_ai.image_input import (
    google_readable_gs_uri,
    is_user_uploaded_url,
    user_uploaded_url_to_gs_uri,
)
from daras_ai_v2 import asr, gcs_v2, language_model, settings, vector_search
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.vector_search import DOWNLOAD_TIMEOUT, download_content_bytes

BUCKET = "gooey-test-bucket"
MEDIA = f"https://storage.googleapis.com/{BUCKET}/daras_ai/media"
OURS = f"{MEDIA}/6b1f0c4e/cat.png"
PRIVATE = gcs_v2.GCS_BUCKET_URL


@pytest.fixture(autouse=True)
def gcs_settings(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", BUCKET)
    monkeypatch.setattr(settings, "GS_MEDIA_PATH", "daras_ai/media")


# is_user_uploaded_url


@pytest.mark.parametrize(
    "url",
    [
        OURS,
        f"http://storage.googleapis.com/{BUCKET}/daras_ai/media/6b1f0c4e/cat.png",
        f"{OURS}?x-goog-signature=abc",
        f"{MEDIA}/6b1f0c4e/Adobe%20Express%20-%20file.png",
        f"{OURS}/",
    ],
)
def test_our_uploads_are_recognised(url):
    assert is_user_uploaded_url(url)


@pytest.mark.parametrize(
    "url",
    [
        # our prefix anywhere but the start of the path used to be enough
        f"https://evil.example/x.png?storage.googleapis.com/{BUCKET}/daras_ai/media",
        f"https://evil.example/storage.googleapis.com/{BUCKET}/daras_ai/media/u/x.png",
        f"http://10.0.0.5:8080/?u=storage.googleapis.com/{BUCKET}/daras_ai/media/u",
        f"https://storage.googleapis.com@evil.example/{BUCKET}/daras_ai/media/u/x.png",
        # the right host, but not our bucket or not our upload prefix
        "https://storage.googleapis.com/other-bucket/daras_ai/media/u/x.png",
        f"https://storage.googleapis.com/{BUCKET}-evil/daras_ai/media/u/x.png",
        f"https://storage.googleapis.com/{BUCKET}/static/index.html",
        MEDIA,
        f"{MEDIA}/",
        # climbing out of the prefix, literally or percent-encoded
        f"{MEDIA}/../../static/index.html",
        f"{MEDIA}/..%2F..%2Fstatic/index.html",
        f"{MEDIA}/u%2F..%2F..%2F..%2Fother/x.png",
        f"ftp://storage.googleapis.com/{BUCKET}/daras_ai/media/u/x.png",
    ],
)
def test_other_urls_are_not_mistaken_for_our_uploads(url):
    assert not is_user_uploaded_url(url)


def test_local_disk_uploads_are_recognised_without_a_bucket(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "")
    monkeypatch.setattr(settings, "APP_BASE_URL", "http://localhost:3000")
    assert is_user_uploaded_url("http://localhost:3000/media/6b1f0c4e/cat.png")
    assert not is_user_uploaded_url("http://localhost:3001/media/6b1f0c4e/cat.png")
    assert not is_user_uploaded_url("http://evil.example/media/6b1f0c4e/cat.png")
    assert not is_user_uploaded_url("http://evil.example/?localhost:3000/media/u/x")


# user_uploaded_url_to_gs_uri


def test_strict_gs_uri_for_our_upload():
    assert (
        user_uploaded_url_to_gs_uri(OURS)
        == f"gs://{BUCKET}/daras_ai/media/6b1f0c4e/cat.png"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/other-bucket/secret.wav",
        "https://storage.googleapis.com/other-bucket/secret.wav",
    ],
)
def test_strict_gs_uri_refuses_anything_else(url):
    # gs_url_to_uri alone would turn these into gs://other-bucket/secret.wav
    with pytest.raises(UserError):
        user_uploaded_url_to_gs_uri(url)


def test_strict_gs_uri_needs_a_bucket(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "")
    # says what's missing, rather than that the file isn't an upload
    with pytest.raises(UserError, match="GS_BUCKET_NAME"):
        user_uploaded_url_to_gs_uri("http://localhost:3000/media/6b1f0c4e/cat.png")


# google_readable_gs_uri


@pytest.fixture
def temp_uploads(monkeypatch):
    """Stub out downloading and temp uploads, recording each copy's lifetime."""
    events = []

    def download(**kwargs):
        events.append(("download", kwargs))
        return b"png bytes", "image/png"

    @contextmanager
    def temp_upload(filename, data, content_type=None, **kwargs):
        events.append(("upload", filename))
        yield f"{MEDIA}/copy/{filename}"
        events.append(("deleted", filename))

    monkeypatch.setattr(vector_search, "download_content_bytes", download)
    monkeypatch.setattr(image_input, "temp_upload_file_from_bytes", temp_upload)
    return events


def test_our_upload_is_referenced_directly(temp_uploads):
    with google_readable_gs_uri(OURS) as uri:
        assert uri == f"gs://{BUCKET}/daras_ai/media/6b1f0c4e/cat.png"
    assert temp_uploads == []


def test_other_urls_are_downloaded_and_rehosted_only_for_the_block(temp_uploads):
    url = "https://storage.googleapis.com/other-bucket/secret.png"
    with google_readable_gs_uri(url, max_bytes=123) as uri:
        # google gets our own copy, never a gs:// uri built from the caller's url
        assert uri == f"gs://{BUCKET}/daras_ai/media/copy/secret.png"
        assert ("deleted", "secret.png") not in temp_uploads
    (_, kwargs), *_ = temp_uploads
    assert kwargs["f_url"] == url
    assert kwargs["raise_on_error"] and kwargs["max_bytes"] == 123
    assert temp_uploads[-1] == ("deleted", "secret.png")


@pytest.mark.parametrize(
    "url", ["https://example.com/cat.png", "http://localhost:3000/media/u/cat.png"]
)
def test_rehosting_needs_a_bucket_and_checks_before_downloading(
    monkeypatch, temp_uploads, url
):
    # google can't read files stored on this server, so there's no point downloading
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "")
    with pytest.raises(UserError, match="GS_BUCKET_NAME"):
        with google_readable_gs_uri(url):
            pass
    assert temp_uploads == []


# download_content_bytes


def fake_response(body=b"data", headers=None, status=200) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r.reason = "OK"
    r.url = "https://example.com/file"
    r.headers = CaseInsensitiveDict(headers or {"Content-Type": "image/png"})
    r.raw = io.BytesIO(body)
    return r


@pytest.fixture
def fetches(monkeypatch):
    """Record every url download_content_bytes requests, and what it sends."""
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return fake_response()

    monkeypatch.setattr(vector_search.requests, "get", get)
    monkeypatch.setattr(
        vector_search, "requests_scraping_kwargs", lambda: {"proxies": "proxy"}
    )
    monkeypatch.setattr(gcs_v2, "private_to_signed_url", lambda url: url + "?signed")
    return calls


def running_workspace(monkeypatch, workspace_id):
    sr = SimpleNamespace(workspace_id=workspace_id) if workspace_id else None
    monkeypatch.setattr(vector_search, "get_running_saved_run", lambda: sr)


def test_external_urls_go_through_the_proxy_with_a_timeout(fetches):
    assert download_content_bytes(f_url="https://example.com/x.png", mime_type="") == (
        b"data",
        "image/png",
    )
    ((url, kwargs),) = fetches
    assert url == "https://example.com/x.png"
    assert kwargs["proxies"] == "proxy"
    assert kwargs["timeout"] == DOWNLOAD_TIMEOUT
    assert "auth" not in kwargs


def test_our_uploads_skip_the_proxy(fetches):
    download_content_bytes(f_url=OURS, mime_type="")
    ((url, kwargs),) = fetches
    assert url == OURS and "proxies" not in kwargs


def test_a_lookalike_of_our_url_still_goes_through_the_proxy(fetches):
    # used to skip the proxy, so it could reach addresses only the server can
    url = f"http://10.0.0.5:8080/?u=storage.googleapis.com/{BUCKET}/daras_ai/media/u"
    download_content_bytes(f_url=url, mime_type="")
    ((_, kwargs),) = fetches
    assert kwargs["proxies"] == "proxy"


def test_private_files_of_the_running_workspace_are_signed(monkeypatch, fetches):
    running_workspace(monkeypatch, 5)
    url = f"{PRIVATE}/workspaces/5/functions/out.csv"
    download_content_bytes(f_url=url, mime_type="")
    ((fetched, kwargs),) = fetches
    assert fetched == url + "?signed" and "proxies" not in kwargs


@pytest.mark.parametrize(
    "workspace_id, url",
    [
        (5, f"{PRIVATE}/workspaces/6/functions/out.csv"),
        (5, f"{PRIVATE}/workspaces/5/../6/functions/out.csv"),
        (5, f"{PRIVATE}/workspaces/5%2F..%2F6/functions/out.csv"),
        (5, f"{PRIVATE}.evil/workspaces/5/functions/out.csv"),
        (5, f"{PRIVATE}/other/out.csv"),
        # no run to check the workspace against
        (None, f"{PRIVATE}/workspaces/5/functions/out.csv"),
    ],
)
def test_other_private_files_are_not_signed(monkeypatch, fetches, workspace_id, url):
    running_workspace(monkeypatch, workspace_id)
    download_content_bytes(f_url=url, mime_type="")
    ((fetched, kwargs),) = fetches
    # fetched as-is through the proxy, so a private file fails like it would for anyone
    assert fetched == url and kwargs["proxies"] == "proxy"


def test_unreachable_urls_return_empty_by_default_or_raise_if_asked(monkeypatch):
    def get(url, **kwargs):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr(vector_search.requests, "get", get)
    assert download_content_bytes(f_url="https://example.com/x", mime_type="") == (
        b"",
        "",
    )
    with pytest.raises(UserError, match="Couldn't download"):
        download_content_bytes(
            f_url="https://example.com/x", mime_type="", raise_on_error=True
        )


@pytest.mark.parametrize(
    "body, headers",
    [
        # refused up front, from the declared length
        (b"", {"Content-Length": "11"}),
        # no length given, so refused once the body runs past the cap
        (b"x" * 11, {}),
    ],
)
def test_max_bytes_refuses_bigger_files(monkeypatch, body, headers):
    monkeypatch.setattr(
        vector_search.requests, "get", lambda url, **kw: fake_response(body, headers)
    )
    with pytest.raises(UserError, match="bigger than"):
        download_content_bytes(
            f_url="https://example.com/x", mime_type="", max_bytes=10
        )


def test_max_bytes_allows_files_within_it(monkeypatch):
    monkeypatch.setattr(
        vector_search.requests, "get", lambda url, **kw: fake_response(b"x" * 10, {})
    )
    data, _ = download_content_bytes(
        f_url="https://example.com/x", mime_type="", max_bytes=10
    )
    assert data == b"x" * 10


@pytest.mark.parametrize(
    "url, client",
    [
        ("https://drive.google.com/file/d/abc/view", "gdrive_download"),
        ("https://www.youtube.com/watch?v=abc", "download_youtube_to_wav"),
    ],
)
def test_max_bytes_also_applies_to_files_downloaded_by_their_own_clients(
    monkeypatch, url, client
):
    # these don't go through the streamed path, so they're checked once downloaded
    def download(*args, **kwargs):
        data = b"x" * 11
        return (data, "image/png") if client == "gdrive_download" else data

    monkeypatch.setattr(vector_search, client, download)
    with pytest.raises(UserError, match="bigger than"):
        download_content_bytes(f_url=url, mime_type="", max_bytes=10)
    # and without a cap they come back as before
    assert download_content_bytes(f_url=url, mime_type="")[0] == b"x" * 11


# asr


@pytest.fixture
def wav_download(monkeypatch):
    uploads = []
    wav = b"RIFF already a 16k mono wav"
    monkeypatch.setattr(asr.requests, "get", lambda url, **kw: fake_response(wav))
    monkeypatch.setattr(asr, "audio_bytes_to_wav", lambda data: (data, len(data)))

    def upload(filename, data, content_type):
        uploads.append(filename)
        return f"{MEDIA}/copy/{filename}"

    monkeypatch.setattr(asr, "upload_file_from_bytes", upload)
    return uploads


def test_external_wav_is_reuploaded_even_when_no_conversion_is_needed(wav_download):
    # returning the caller's url would hand google a gs:// uri built from its path
    url = "https://evil.example/other-bucket/secret.wav"
    audio_url, _ = asr.audio_url_to_wav_url(url)
    assert audio_url == f"{MEDIA}/copy/secret.wav.wav"
    assert user_uploaded_url_to_gs_uri(audio_url).startswith(f"gs://{BUCKET}/")


def test_our_own_wav_is_used_as_is(wav_download):
    audio_url, _ = asr.audio_url_to_wav_url(f"{MEDIA}/6b1f0c4e/clip.wav")
    assert audio_url == f"{MEDIA}/6b1f0c4e/clip.wav"
    assert wav_download == []


# gemini vision


def test_rehosted_images_live_until_gemini_returns(monkeypatch):
    events = []

    @contextmanager
    def readable(url):
        events.append(("open", url))
        yield "gs://copy/" + url.rsplit("/", 1)[-1]
        events.append(("closed", url))

    def call_gemini(**kwargs):
        events.append(
            (
                "call",
                [p["fileData"]["fileUri"] for p in kwargs["contents"][0]["parts"][1:]],
            )
        )
        return "a cat"

    monkeypatch.setattr(language_model, "google_readable_gs_uri", readable)
    monkeypatch.setattr(language_model, "_call_gemini_api", call_gemini)
    result = language_model._run_gemini_pro_vision(
        model_id="gemini",
        prompt="what is this?",
        images=["https://example.com/a.png", "https://example.com/b.png"],
        max_output_tokens=10,
        temperature=0,
    )
    assert result == ["a cat"]
    assert events == [
        ("open", "https://example.com/a.png"),
        ("open", "https://example.com/b.png"),
        ("call", ["gs://copy/a.png", "gs://copy/b.png"]),
        ("closed", "https://example.com/b.png"),
        ("closed", "https://example.com/a.png"),
    ]
