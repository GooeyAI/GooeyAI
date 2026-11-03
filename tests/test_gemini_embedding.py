from contextlib import contextmanager

import pytest

from daras_ai.image_input import gs_url_to_uri
from daras_ai_v2 import gemini_embedding, settings, vector_search
from daras_ai_v2.gemini_embedding import (
    MAX_EMBEDDING_MEDIA_BYTES,
    _download_media,
    _gemini_file_part,
    run_gemini_embedding,
)
from daras_ai_v2.exceptions import UserError
from files.models import FileMetadata

BUCKET = "gooey-test-bucket"
MEDIA = f"https://storage.googleapis.com/{BUCKET}/daras_ai/media"

UNTRUSTED_URLS = [
    # any host: a gs:// uri built from its path would let the path pick the bucket
    "https://evil.example/other-bucket/secret.png",
    # the right host, someone else's bucket
    "https://storage.googleapis.com/other-bucket/daras_ai/media/u/secret.png",
    # our bucket, but outside the media folder
    f"https://storage.googleapis.com/{BUCKET}/private/secret.png",
    # our prefix smuggled into the query string
    f"https://evil.example/x.png?storage.googleapis.com/{BUCKET}/daras_ai/media",
    # climbing out of the prefix once percent-decoded
    f"{MEDIA}/u%2F..%2F..%2F..%2Fother/x.png",
]


@pytest.fixture(autouse=True)
def gcs_settings(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", BUCKET)
    monkeypatch.setattr(settings, "GS_MEDIA_PATH", "daras_ai/media")


def test_gs_url_to_uri_accepts_our_uploads():
    assert gs_url_to_uri(f"{MEDIA}/6b1f0c4e/cat.png?x=1") == (
        f"gs://{BUCKET}/daras_ai/media/6b1f0c4e/cat.png"
    )


@pytest.mark.parametrize("url", UNTRUSTED_URLS)
def test_gs_url_to_uri_refuses_every_other_url(url):
    with pytest.raises(UserError, match="isn't a file uploaded to Gooey"):
        gs_url_to_uri(url)


def test_gs_url_to_uri_refuses_everything_without_a_bucket(monkeypatch):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "")
    with pytest.raises(UserError):
        gs_url_to_uri(f"{MEDIA}/6b1f0c4e/cat.png")


@pytest.fixture
def media(monkeypatch):
    """Stub out the network and storage around _gemini_file_part, recording each step."""
    events = []

    def download(url):
        events.append(("download", url))
        return b"bytes", "image/png"

    @contextmanager
    def temp_upload(filename, data, content_type=None, **kwargs):
        events.append(("copy", filename))
        yield f"{MEDIA}/copy/{filename}"
        events.append(("deleted", filename))

    monkeypatch.setattr(gemini_embedding, "_download_media", download)
    monkeypatch.setattr(gemini_embedding, "temp_upload_file_from_bytes", temp_upload)
    return events


def part_for(url):
    with _gemini_file_part(url) as part:
        return part


@pytest.mark.parametrize(
    "name, mime_type",
    [
        ("cat.png", "image/png"),
        ("clip.mp4", "video/mp4"),
        ("doc.pdf", "application/pdf"),
        ("clip.webm", "video/webm"),
    ],
)
def test_our_upload_in_a_format_gemini_reads_is_used_as_is(media, name, mime_type):
    assert part_for(f"{MEDIA}/6b1f0c4e/{name}") == {
        "file_data": {
            "mime_type": mime_type,
            "file_uri": f"gs://{BUCKET}/daras_ai/media/6b1f0c4e/{name}",
        }
    }
    assert media == []


@pytest.mark.parametrize("name", ["file", "cat.unknownext"])
def test_our_upload_without_a_known_format_is_downloaded(media, name):
    # the server's content type decides
    url = f"{MEDIA}/6b1f0c4e/{name}"
    part = part_for(url)
    assert part["file_data"]["file_uri"] == f"gs://{BUCKET}/daras_ai/media/copy/{name}"
    assert media[0] == ("download", url)


@pytest.mark.parametrize("url", UNTRUSTED_URLS)
def test_other_urls_are_downloaded_and_copied_never_sent_to_vertex(media, url):
    part = part_for(url)
    # vertex gets our own copy, never a gs:// uri built from the caller's url
    assert part["file_data"]["file_uri"].startswith(
        f"gs://{BUCKET}/daras_ai/media/copy/"
    )
    assert media[0] == ("download", url)


def test_copies_last_only_until_their_own_vertex_call_returns(monkeypatch, media):
    monkeypatch.setattr(
        gemini_embedding, "get_google_auth_session", lambda: (None, "project")
    )

    def embed(*, session, model_uri, part):
        name = part["file_data"]["file_uri"].rsplit("/", 1)[-1]
        assert ("deleted", name) not in media
        media.append(("embedded", name))
        return [0.0] * 3072

    monkeypatch.setattr(gemini_embedding, "_vertex_embed_content", embed)
    run_gemini_embedding(
        texts=[], media_urls=["https://example.com/a.png"], model_id="m"
    )
    assert media[1:] == [("copy", "a.png"), ("embedded", "a.png"), ("deleted", "a.png")]


def test_media_needs_a_bucket_and_checks_before_fetching(monkeypatch, media):
    monkeypatch.setattr(settings, "GS_BUCKET_NAME", "")
    with pytest.raises(UserError, match="GS_BUCKET_NAME"):
        part_for("https://example.com/cat.png")
    assert media == []


@pytest.fixture
def remote(monkeypatch):
    """Stub doc search's metadata and download helpers with one remote file."""

    class Remote:
        name = "file"
        meta_mime_type = ""
        total_bytes = 0
        data = b"data"
        mime_type = "image/png"
        downloads = []

    rec = Remote()

    def metadata(url):
        meta = FileMetadata(
            name=rec.name, mime_type=rec.meta_mime_type, total_bytes=rec.total_bytes
        )
        meta.export_links = {"x": "y"}
        return meta

    def download(**kwargs):
        rec.downloads.append(kwargs)
        return rec.data, rec.mime_type

    monkeypatch.setattr(vector_search, "doc_url_to_file_metadata", metadata)
    monkeypatch.setattr(vector_search, "download_content_bytes", download)
    return rec


def test_download_passes_the_metadata_along(remote):
    # gdrive and onedrive links need the metadata's type and export links to download
    remote.meta_mime_type = "image/webp"
    remote.mime_type = "image/webp"
    url = "https://drive.google.com/file/d/abc/view"
    assert _download_media(url) == (b"data", "image/webp")
    assert remote.downloads == [
        dict(f_url=url, mime_type="image/webp", export_links={"x": "y"})
    ]


def test_download_falls_back_to_the_files_name_for_a_generic_type(remote):
    remote.name = "clip.mp4"
    remote.mime_type = "application/octet-stream"
    assert _download_media("https://example.com/view") == (b"data", "video/mp4")


def test_download_refuses_a_big_file_before_downloading(remote):
    remote.total_bytes = MAX_EMBEDDING_MEDIA_BYTES + 1
    with pytest.raises(UserError, match="bigger than"):
        _download_media("https://example.com/big.png")
    assert remote.downloads == []


def test_download_refuses_a_big_file_of_unknown_size(remote):
    remote.data = b"x" * (MAX_EMBEDDING_MEDIA_BYTES + 1)
    with pytest.raises(UserError, match="bigger than"):
        _download_media("https://example.com/big.png")


def test_unreachable_url_is_a_user_error(remote):
    # download_content_bytes logs the error and returns nothing
    remote.data, remote.mime_type = b"", ""
    with pytest.raises(UserError, match="Couldn't download"):
        _download_media("https://example.com/cat.png")
