from contextlib import contextmanager

import pytest

from daras_ai_v2 import embedding_model, settings, vector_search
from daras_ai_v2.embedding_model import (
    MAX_EMBEDDING_MEDIA_BYTES,
    EmbeddingInput,
    _convert_for_gemini,
    _embedding_input_part,
    _run_vertex_embedding,
)
from daras_ai_v2.exceptions import UserError

BUCKET = "gooey-test-bucket"
MEDIA = f"https://storage.googleapis.com/{BUCKET}/daras_ai/media"

UNTRUSTED_URLS = [
    # any host: gs_url_to_uri would drop it, letting the path pick the bucket
    "https://evil.example/other-bucket/secret.png",
    # the right host, someone else's bucket
    "https://storage.googleapis.com/other-bucket/daras_ai/media/u/secret.png",
    # our prefix smuggled into the query string
    f"https://evil.example/x.png?storage.googleapis.com/{BUCKET}/daras_ai/media",
    # climbing out of the prefix once percent-decoded
    f"{MEDIA}/u%2F..%2F..%2F..%2Fother/x.png",
]


@pytest.fixture(autouse=True)
def gcs_settings(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", BUCKET)
    monkeypatch.setattr(settings, "GS_MEDIA_PATH", "daras_ai/media")


@pytest.fixture
def media(monkeypatch):
    """
    Stub out the network and storage around _embedding_input_part, recording each step.
    `media.head` is the type a HEAD of one of our uploads reports.
    """

    class Recorder:
        head = "image/png"
        events = []

    rec = Recorder()

    def head(url):
        rec.events.append(("head", url))
        return rec.head

    def download(**kwargs):
        rec.events.append(("download", kwargs))
        return b"bytes", "image/gif"

    def convert(url, data, mime_type):
        rec.events.append(("convert", mime_type))
        return data, "image/png"

    @contextmanager
    def temp_upload(filename, data, content_type=None, **kwargs):
        rec.events.append(("copy", filename))
        yield f"{MEDIA}/copy/{filename}"
        rec.events.append(("deleted", filename))

    monkeypatch.setattr(embedding_model, "get_mimetype_from_url", head)
    monkeypatch.setattr(vector_search, "download_content_bytes", download)
    monkeypatch.setattr(embedding_model, "_convert_for_gemini", convert)
    monkeypatch.setattr(embedding_model, "temp_upload_file_from_bytes", temp_upload)
    return rec


def part_for(url):
    with _embedding_input_part(EmbeddingInput(url=url)) as part:
        return part


@pytest.mark.parametrize("mime_type", ["image/png", "audio/x-wav", "video/mp4"])
def test_our_upload_in_a_format_gemini_reads_is_used_as_is(media, mime_type):
    # the type comes from the server, not the url's extension
    media.head = mime_type
    url = f"{MEDIA}/6b1f0c4e/file"
    assert part_for(url) == {
        "file_data": {
            "mime_type": mime_type,
            "file_uri": f"gs://{BUCKET}/daras_ai/media/6b1f0c4e/file",
        }
    }
    assert media.events == [("head", url)]


def test_our_upload_in_a_format_gemini_cant_read_is_converted_and_copied(media):
    media.head = "image/gif"
    url = f"{MEDIA}/6b1f0c4e/cat.gif"
    part = part_for(url)
    assert part["file_data"] == {
        "mime_type": "image/png",
        "file_uri": f"gs://{BUCKET}/daras_ai/media/copy/cat.png",
    }
    (_, (_, download), (_, converted), *_) = media.events
    assert download["f_url"] == url
    assert converted == "image/gif"


@pytest.mark.parametrize("url", UNTRUSTED_URLS)
def test_other_urls_are_downloaded_and_copied_never_sent_to_vertex(media, url):
    part = part_for(url)
    # vertex gets our own copy, never a gs:// uri built from the caller's url
    assert part["file_data"]["file_uri"].startswith(
        f"gs://{BUCKET}/daras_ai/media/copy/"
    )
    # not taken for one of ours, so no HEAD, and downloaded through the shared helper
    (_, download), *_ = media.events
    assert download == {
        "f_url": url,
        "mime_type": "",
        "max_bytes": MAX_EMBEDDING_MEDIA_BYTES,
        "raise_on_error": True,
    }


def test_copies_last_only_until_their_own_vertex_call_returns(monkeypatch, media):
    monkeypatch.setattr(
        embedding_model, "get_google_auth_session", lambda: (None, "project")
    )

    def embed(*, session, model_uri, content):
        (part,) = content["parts"]
        name = part["file_data"]["file_uri"].rsplit("/", 1)[-1]
        assert ("deleted", name) not in media.events
        media.events.append(("embedded", name))
        return [0.0] * 3072

    monkeypatch.setattr(embedding_model, "_vertex_embed_content", embed)
    _run_vertex_embedding(
        inputs=[EmbeddingInput(url="https://example.com/a.png")], model_id="m"
    )
    assert [e for e in media.events if e[0] in ("copy", "embedded", "deleted")] == [
        ("copy", "a.png"),
        ("embedded", "a.png"),
        ("deleted", "a.png"),
    ]


def test_each_input_is_fetched_and_embedded_independently(monkeypatch, media):
    # one bad input doesn't stop the others reaching vertex -- an accepted tradeoff of
    # fetching and embedding in the same thread, instead of fetching everything first
    monkeypatch.setattr(
        embedding_model, "get_google_auth_session", lambda: (None, "project")
    )
    embedded = []

    def embed(*, session, model_uri, content):
        embedded.append(content["parts"][0])
        return [0.0] * 3072

    def download(**kwargs):
        raise UserError("unreachable")

    monkeypatch.setattr(embedding_model, "_vertex_embed_content", embed)
    monkeypatch.setattr(vector_search, "download_content_bytes", download)
    with pytest.raises(UserError):
        _run_vertex_embedding(
            inputs=[
                EmbeddingInput(text="a cat"),
                EmbeddingInput(url="https://example.com/x.png"),
            ],
            model_id="m",
        )
    assert embedded == [{"text": "a cat"}]


def test_media_needs_a_bucket_and_checks_before_fetching(monkeypatch, media):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "")
    with pytest.raises(UserError, match="GS_BUCKET_NAME"):
        part_for("https://example.com/cat.png")
    assert media.events == []


def test_a_copy_outside_our_prefix_is_refused(monkeypatch, media):
    # the gs:// uri always comes from user_uploaded_url_to_gs_uri, which won't build one
    # for anything but our own uploads, even if the copy somehow landed elsewhere
    @contextmanager
    def temp_upload(*args, **kwargs):
        yield "https://evil.example/other-bucket/x.png"

    monkeypatch.setattr(embedding_model, "temp_upload_file_from_bytes", temp_upload)
    with pytest.raises(UserError):
        part_for("https://example.com/cat.png")


@pytest.mark.parametrize(
    "mime_type", ["audio/mpeg", "audio/wav", "audio/x-wav", "application/pdf"]
)
def test_formats_gemini_reads_pass_through_unchanged(mime_type):
    assert _convert_for_gemini("u", b"data", mime_type) == (b"data", mime_type)


@pytest.mark.parametrize("mime_type", ["text/html", "application/zip", ""])
def test_other_kinds_of_file_are_rejected(mime_type):
    # an empty type (unknown, or a bare application/octet-stream) gets a clear error
    with pytest.raises(UserError, match="not an image, audio, video or PDF"):
        _convert_for_gemini("https://example.com/page", b"<html>", mime_type)
