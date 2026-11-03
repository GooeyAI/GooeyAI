import mimetypes
import typing
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from aifail import http_should_retry, retry_if
from furl import furl
from loguru import logger

from daras_ai.image_input import (
    gs_url_to_uri,
    is_gs_upload_url,
    safe_filename,
    temp_upload_file_from_bytes,
)
from daras_ai_v2 import settings
from daras_ai_v2.asr import get_google_auth_session
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.functional import get_initializer

# gemini-embedding-2 emits 128..3072 dims (Matryoshka, auto-renormalized). 3072 is the max
# and exactly matches vector_search.EMBEDDING_SIZE, so it needs no zero padding to be fed
# into the Vespa `tensor<float>(x[3072])` field.
GEMINI_EMBEDDING_DIMENSIONS = 3072

# gemini-embedding-2 is only served from Vertex's multi-region "rep" endpoints, which take
# just "us" or "eu" -- not a specific region like the classic {region}-aiplatform.googleapis.com
# host this codebase uses elsewhere for Gemini chat/vision calls (see _call_gemini_api).
# There is also no batch call for this model, unlike the older text embedding models: every
# content needs its own :embedContent request, so we fan them out across a thread pool.
GEMINI_EMBEDDING_LOCATION = "us"
VERTEX_EMBEDDING_MAX_WORKERS = 10


def run_gemini_embedding(
    *, texts: list[str], media_urls: list[str], model_id: str
) -> list[list[float]]:
    """
    Embed each input with its own :embedContent call, so each gets its own vector --
    bundling several parts into one `content` would return one aggregated vector instead.
    """
    logger.info(f"{model_id=}, {len(texts)=}, {len(media_urls)=}")
    session, project = get_google_auth_session()
    # the model is addressed by its fully qualified resource path
    model_uri = (
        f"projects/{project}/locations/{GEMINI_EMBEDDING_LOCATION}"
        f"/publishers/google/models/{model_id}"
    )

    def embed_text(text: str) -> list[float]:
        return _vertex_embed_content(
            session=session, model_uri=model_uri, part={"text": text}
        )

    def embed_media(url: str) -> list[float]:
        # any copy made of the file only lasts for its own call
        with _gemini_file_part(url) as part:
            return _vertex_embed_content(
                session=session, model_uri=model_uri, part=part
            )

    with ThreadPoolExecutor(
        max_workers=VERTEX_EMBEDDING_MAX_WORKERS, initializer=get_initializer()
    ) as pool:
        text_embeddings = pool.map(embed_text, texts)
        media_embeddings = pool.map(embed_media, media_urls)
        return [*text_embeddings, *media_embeddings]


@retry_if(http_should_retry)
def _vertex_embed_content(*, session, model_uri: str, part: dict) -> list[float]:
    r = session.post(
        f"https://aiplatform.{GEMINI_EMBEDDING_LOCATION}.rep.googleapis.com"
        f"/v1/{model_uri}:embedContent",
        json={
            "content": {"parts": [part]},
            "embedContentConfig": {"outputDimensionality": GEMINI_EMBEDDING_DIMENSIONS},
        },
    )
    raise_for_status(r)
    return r.json()["embedding"]["values"]


# a fetched file is held in memory and re-uploaded, so cap how big one can be
MAX_EMBEDDING_MEDIA_BYTES = 50 * 1024 * 1024


@contextmanager
def _gemini_file_part(url: str) -> typing.Iterator[dict]:
    """
    A `file_data` part Gemini can read this url's file from, valid until the `with`
    block exits.

    Vertex reads gs:// uris with our own service account, so only files uploaded to
    our bucket are referenced directly. Any other url is downloaded and re-uploaded
    for the call.
    """
    if not settings.GS_BUCKET_NAME:
        raise UserError(
            "Embedding files needs Google Cloud Storage (GS_BUCKET_NAME) configured."
        )
    mime_type = mimetypes.guess_type(_url_filename(url))[0]
    if is_gs_upload_url(url) and mime_type:
        yield {"file_data": {"mime_type": mime_type, "file_uri": gs_url_to_uri(url)}}
        return

    data, mime_type = _download_media(url)
    filename = safe_filename(_url_filename(url) or "file")
    with temp_upload_file_from_bytes(filename, data, mime_type) as copy_url:
        yield {
            "file_data": {"mime_type": mime_type, "file_uri": gs_url_to_uri(copy_url)}
        }


def _download_media(url: str) -> tuple[bytes, str]:
    """
    Download a file with the same helpers doc search uses, so Google Drive, OneDrive
    and YouTube links work as well as plain urls.
    """
    from daras_ai_v2.vector_search import (
        doc_url_to_file_metadata,
        download_content_bytes,
    )

    meta = doc_url_to_file_metadata(url)
    if meta.total_bytes > MAX_EMBEDDING_MEDIA_BYTES:
        raise _too_big_error(url)
    data, mime_type = download_content_bytes(
        f_url=url, mime_type=meta.mime_type, export_links=meta.export_links
    )
    if not data:
        raise UserError(f"Couldn't download {url}.")
    # the size isn't always known upfront, so check again once it's downloaded
    if len(data) > MAX_EMBEDDING_MEDIA_BYTES:
        raise _too_big_error(url)
    if not mime_type or mime_type == "application/octet-stream":
        # servers often report a generic type, so fall back to the file's name
        mime_type = mimetypes.guess_type(meta.name)[0] or mime_type
    return data, mime_type


def _too_big_error(url: str) -> UserError:
    return UserError(
        f"{url} is bigger than the {MAX_EMBEDDING_MEDIA_BYTES // (1024 * 1024)} MB "
        "that can be embedded."
    )


def _url_filename(url: str) -> str:
    segments = furl(url).path.segments
    return segments[-1] if segments else ""
