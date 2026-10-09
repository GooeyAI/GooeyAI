import io

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from daras_ai_v2 import embedding_model, settings
from daras_ai_v2.embedding_model import (
    EmbeddingInput,
    EmbeddingModels,
    _convert_for_gemini,
    _download_public_media,
    _embedding_input_to_part,
    _is_user_media_url,
    create_multimodal_embeddings,
)
from daras_ai_v2.exceptions import UserError

BUCKET = "gooey-test-bucket"
MEDIA = f"https://storage.googleapis.com/{BUCKET}/daras_ai/media"
REHOSTED = f"{MEDIA}/rehosted/copy.png"

UNTRUSTED_URLS = [
    # any host: gs_url_to_uri drops it, so the path alone would pick the bucket
    "https://evil.example/other-bucket/secret.pdf",
    # a host that isn't ours, mimicking our own bucket path
    f"https://evil.example/{BUCKET}/daras_ai/media/6b1f0c4e/cat.png",
    # the right host, someone else's bucket
    "https://storage.googleapis.com/other-bucket/daras_ai/media/6b1f0c4e/secret.pdf",
    # our bucket, but outside the user media prefix
    f"https://storage.googleapis.com/{BUCKET}/static/index.html",
    # the prefix alone, naming no file
    MEDIA,
    # our prefix smuggled into the query string
    f"https://evil.example/other-bucket/x.png?storage.googleapis.com/{BUCKET}/daras_ai/media",
    # plain http
    f"http://storage.googleapis.com/{BUCKET}/daras_ai/media/6b1f0c4e/cat.png",
    # climbing out of the prefix, literally and percent-encoded
    f"{MEDIA}/../../static/index.html",
    f"{MEDIA}/..%2F..%2Fstatic/index.html",
    f"{MEDIA}/6b1f0c4e%2F..%2F..%2F..%2Fother/x.png",
]


@pytest.fixture(autouse=True)
def gcs_settings(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", BUCKET)
    monkeypatch.setattr(settings, "GS_MEDIA_PATH", "daras_ai/media")


@pytest.fixture
def rehost(monkeypatch):
    """Stub out fetching, converting and uploading, recording what was fetched."""
    fetched = []

    def download_public_media(url):
        fetched.append(url)
        return b"image bytes", "image/png"

    def no_user_download(url):
        raise AssertionError("should not download a file we can use as-is")

    monkeypatch.setattr(
        embedding_model, "_download_public_media", download_public_media
    )
    monkeypatch.setattr(embedding_model, "_download_user_media", no_user_download)
    monkeypatch.setattr(
        embedding_model, "_convert_for_gemini", lambda url, data, mime: (data, mime)
    )
    monkeypatch.setattr(
        embedding_model, "upload_file_from_bytes", lambda *args, **kwargs: REHOSTED
    )
    return fetched


def test_our_upload_in_a_gemini_format_is_used_as_is(rehost):
    part = _embedding_input_to_part(EmbeddingInput(url=f"{MEDIA}/6b1f0c4e/cat.png"))
    assert part == {
        "file_data": {
            "mime_type": "image/png",
            "file_uri": f"gs://{BUCKET}/daras_ai/media/6b1f0c4e/cat.png",
        }
    }
    assert rehost == []


def test_our_wav_upload_is_sent_as_audio_wav(rehost):
    # python's mimetypes says audio/x-wav, which isn't a type gemini lists
    part = _embedding_input_to_part(EmbeddingInput(url=f"{MEDIA}/6b1f0c4e/clip.wav"))
    assert part["file_data"]["mime_type"] == "audio/wav"


@pytest.mark.parametrize("url", UNTRUSTED_URLS)
def test_urls_outside_our_media_prefix_are_not_trusted(url):
    assert not _is_user_media_url(url)


@pytest.mark.parametrize("url", UNTRUSTED_URLS)
def test_untrusted_url_is_fetched_and_rehosted_not_sent_to_vertex(rehost, url):
    part = _embedding_input_to_part(EmbeddingInput(url=url))
    # vertex gets our own copy, never a gs:// uri built from the caller's url
    assert (
        part["file_data"]["file_uri"]
        == f"gs://{BUCKET}/daras_ai/media/rehosted/copy.png"
    )
    assert rehost == [url]


def test_vertex_is_never_given_a_url_outside_our_prefix(monkeypatch):
    monkeypatch.setattr(
        embedding_model,
        "_media_url_for_vertex",
        lambda url: ("https://evil.example/other-bucket/secret.png", "image/png"),
    )
    with pytest.raises(RuntimeError):
        _embedding_input_to_part(EmbeddingInput(url=f"{MEDIA}/6b1f0c4e/cat.png"))


def test_media_needs_a_bucket_configured(monkeypatch, rehost):
    # local dev stores uploads on disk, which vertex can't read
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "")
    with pytest.raises(UserError, match="GS_BUCKET_NAME"):
        _embedding_input_to_part(EmbeddingInput(url="https://example.com/cat.png"))
    assert rehost == []


def fake_response(body: bytes, headers: dict) -> requests.Response:
    r = requests.Response()
    r.status_code = 200
    r.reason = "OK"
    r.url = "https://example.com/cat.png"
    r.headers = CaseInsensitiveDict(headers)
    r.raw = io.BytesIO(body)
    return r


def test_public_download_sends_none_of_our_credentials(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        return fake_response(b"png bytes", {"Content-Type": "image/png"})

    monkeypatch.setattr(embedding_model.requests, "get", get)
    assert _download_public_media("https://example.com/cat.png") == (
        b"png bytes",
        "image/png",
    )
    (kwargs,) = calls
    assert "auth" not in kwargs
    assert "authorization" not in {k.lower() for k in kwargs.get("headers", {})}


@pytest.mark.parametrize(
    "body, headers",
    [
        # refused up front, from the declared length
        (b"", {"Content-Length": "11"}),
        # no length given, so refused once the body runs past the cap
        (b"x" * 11, {}),
    ],
)
def test_public_download_is_capped(monkeypatch, body, headers):
    monkeypatch.setattr(embedding_model, "MAX_EMBEDDING_MEDIA_BYTES", 10)
    monkeypatch.setattr(
        embedding_model.requests,
        "get",
        lambda url, **kwargs: fake_response(body, headers),
    )
    with pytest.raises(UserError, match="limit"):
        _download_public_media("https://example.com/big.mp4")


def test_content_type_falls_back_to_the_url(monkeypatch):
    monkeypatch.setattr(
        embedding_model.requests,
        "get",
        lambda url, **kwargs: fake_response(
            b"", {"Content-Type": "application/octet-stream"}
        ),
    )
    assert _download_public_media("https://example.com/clip.wav")[1] == "audio/wav"


@pytest.mark.parametrize("mime_type", ["audio/mpeg", "audio/wav", "application/pdf"])
def test_formats_gemini_reads_pass_through_unchanged(mime_type):
    assert _convert_for_gemini("u", b"data", mime_type) == (b"data", mime_type)


@pytest.mark.parametrize("mime_type", ["text/html", "application/zip", ""])
def test_other_kinds_of_file_are_rejected(mime_type):
    with pytest.raises(UserError, match="not an image, audio, video or PDF"):
        _convert_for_gemini("https://example.com/page", b"<html>", mime_type)


def test_a_file_that_cant_be_embedded_never_reaches_vertex(monkeypatch):
    def fail(**kwargs):
        raise AssertionError("vertex was called")

    monkeypatch.setattr(embedding_model, "_run_vertex_embedding", fail)
    monkeypatch.setattr(
        embedding_model,
        "_download_public_media",
        lambda url: (b"<html>", "text/html"),
    )
    with pytest.raises(UserError):
        create_multimodal_embeddings(
            [
                EmbeddingInput(text="a cat"),
                EmbeddingInput(url="https://example.com/not-a-picture"),
            ],
            EmbeddingModels.gemini_embedding_2,
        )
