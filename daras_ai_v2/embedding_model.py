import hashlib
import io
import mimetypes
import os
import typing
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from functools import partial

import numpy as np
import requests
from aifail import (
    http_should_retry,
    retry_if,
    try_all,
)
from furl import furl
from jinja2.lexer import whitespace_re
from loguru import logger

from daras_ai.image_input import gcs_bucket, gs_url_to_uri, upload_file_from_bytes
from daras_ai_v2 import gcs_v2, settings
from daras_ai_v2.asr import audio_bytes_to_wav, get_google_auth_session
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.functional import get_initializer
from daras_ai_v2.gpu_server import call_celery_task
from daras_ai_v2.language_model import get_openai_client, openai_should_retry
from daras_ai_v2.media_conversion import (
    resize_and_convert_image,
    video_bytes_to_mp4,
    video_codec_name,
)
from daras_ai_v2.redis_cache import (
    get_redis_cache,
)
from daras_ai_v2.scraping_proxy import requests_scraping_kwargs


class EmbeddingModel(typing.NamedTuple):
    model_id: typing.Iterable[str] | str
    label: str

    # Per-model capabilities. These live in code, so adding or correcting a model still
    # needs a deploy -- the ai_models.AIModelSpec table is where they want to end up.
    supports_multimodal: bool = False
    max_images: int = 0
    max_audio_seconds: int = 0
    max_video_seconds: int = 0
    max_documents: int = 0
    max_document_pages: int = 0


class EmbeddingInput(typing.NamedTuple):
    """One thing to embed: either a text snippet or an uploaded media file."""

    text: str | None = None
    url: str | None = None


class EmbeddingModels(Enum):
    openai_3_large = EmbeddingModel(
        model_id=("openai-text-embedding-3-large-prod-ca-1", "text-embedding-3-large"),
        label="Text Embedding 3 Large (OpenAI)",
    )
    openai_3_small = EmbeddingModel(
        model_id=("openai-text-embedding-3-small-prod-ca-1", "text-embedding-3-small"),
        label="Text Embedding 3 Small (OpenAI)",
    )
    openai_ada_2 = EmbeddingModel(
        model_id=("openai-text-embedding-ada-002-prod-ca-1", "text-embedding-ada-002"),
        label="Text Embedding Ada 2 (OpenAI)",
    )

    gemini_embedding_2 = EmbeddingModel(
        model_id="gemini-embedding-2",
        label="Gemini Embedding 2 (Google)",
        # text, images, audio, video and PDFs all land in one shared vector space,
        # so media can be retrieved by a plain text query
        supports_multimodal=True,
        max_images=6,
        max_audio_seconds=180,
        max_video_seconds=120,
        max_documents=1,
        max_document_pages=6,
    )

    mistral_embed = EmbeddingModel(
        model_id="mistral-embed",
        label="Mistral Embed (Mistral AI)",
    )

    e5_large_v2 = EmbeddingModel(
        model_id="intfloat/e5-large-v2",
        label="E5 large v2 (Liang Wang)",
    )
    e5_base_v2 = EmbeddingModel(
        model_id="intfloat/e5-base-v2",
        label="E5 base v2 (Liang Wang)",
    )
    multilingual_e5_base = EmbeddingModel(
        model_id="intfloat/multilingual-e5-base",
        label="Multilingual E5 Base (Liang Wang)",
    )
    multilingual_e5_large = EmbeddingModel(
        model_id="intfloat/multilingual-e5-large",
        label="Multilingual E5 Large (Liang Wang)",
    )
    gte_large = EmbeddingModel(
        model_id="thenlper/gte-large",
        label="General Text Embeddings Large (Dingkun Long)",
    )
    gte_base = EmbeddingModel(
        model_id="thenlper/gte-base",
        label="General Text Embeddings Base (Dingkun Long)",
    )

    @property
    def model_id(self) -> typing.Iterable[str] | str:
        return self.value.model_id

    @property
    def label(self) -> str:
        return self.value.label

    @property
    def supports_multimodal(self) -> bool:
        return self.value.supports_multimodal

    @property
    def max_images(self) -> int:
        return self.value.max_images

    @property
    def max_audio_seconds(self) -> int:
        return self.value.max_audio_seconds

    @property
    def max_video_seconds(self) -> int:
        return self.value.max_video_seconds

    @property
    def max_documents(self) -> int:
        return self.value.max_documents

    @property
    def max_document_pages(self) -> int:
        return self.value.max_document_pages

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls[key]
        except KeyError:
            return default


def create_embeddings_cached(
    texts: list[str], model: EmbeddingModels
) -> list[np.ndarray | None]:
    # replace newlines, which can negatively affect performance.
    texts = [whitespace_re.sub(" ", text) for text in texts]
    # get the redis cache
    redis_cache = get_redis_cache()
    # load the embeddings from the cache
    ret = [
        (
            np_loads(data)
            if (data := redis_cache.get(_embed_cache_key(text, model.name)))
            else None
        )
        for text in texts
    ]
    # list of embeddings that need to be created
    misses = [i for i, c in enumerate(ret) if c is None]
    if misses:
        # create the embeddings in bulk
        embeddings = create_embeddings(texts=[texts[i] for i in misses], model=model)
        for i, embedding in zip(misses, embeddings):
            # save the embedding to the cache
            text = texts[i]
            redis_cache.set(_embed_cache_key(text, model.name), np_dumps(embedding))
            # fill in missing values
            ret[i] = embedding
    return ret


def create_embeddings(texts: list[str], model: EmbeddingModels) -> np.ndarray:
    if "openai" in model.name:
        ret = _run_openai_embedding(texts=texts, model_id=model.model_id)
    elif "mistral" in model.name:
        ret = _run_openai_embedding(
            texts=texts,
            model_id=model.model_id,
            base_url="https://api.mistral.ai/v1",
            api_key=settings.MISTRAL_API_KEY,
        )
    elif "gemini" in model.name:
        ret = _run_vertex_embedding(
            contents=[{"parts": [{"text": text}]} for text in texts],
            model_id=model.model_id,
        )
    else:
        ret = _run_gpu_embedding(texts=texts, model_id=model.model_id)

    return _validate_embeddings(ret, expected_len=len(texts))


def create_multimodal_embeddings(
    inputs: list[EmbeddingInput], model: EmbeddingModels
) -> np.ndarray:
    """
    Embed a mixed list of texts and media files, one vector per input.

    Every input becomes its own `content`, which is what yields an embedding each --
    bundling several parts into one `content` would instead return a single aggregated
    vector for the lot.
    """
    if not model.supports_multimodal:
        raise UserError(f"{model.label} cannot embed media, only text.")

    # fetching and converting media can be slow, so get every input ready in parallel
    with ThreadPoolExecutor(
        max_workers=VERTEX_EMBEDDING_MAX_WORKERS, initializer=get_initializer()
    ) as pool:
        parts = list(pool.map(_embedding_input_to_part, inputs))
    ret = _run_vertex_embedding(
        contents=[{"parts": [part]} for part in parts], model_id=model.model_id
    )
    return _validate_embeddings(ret, expected_len=len(inputs))


def _embedding_input_to_part(inp: EmbeddingInput) -> dict:
    if not inp.url:
        return {"text": inp.text or ""}
    url, mime_type = _media_url_for_vertex(inp.url)
    # Vertex reads the file with our own service account, and gs_url_to_uri throws away
    # the host and turns whatever path it's given into a bucket name. So this is the one
    # place a gs:// uri gets made, and it only ever points into our own upload prefix --
    # anything else would let a caller make us read any object that account can see,
    # and hand back its embedding.
    if not _is_user_media_url(url):
        raise RuntimeError(
            f"Refusing to send {url!r} to Vertex: not in our media bucket"
        )
    return {"file_data": {"mime_type": mime_type, "file_uri": gs_url_to_uri(url)}}


# what gemini-embedding-2 can read, from
# https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-multimodal-embeddings
GEMINI_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/heic",
    "image/heif",
    "image/avif",
    "audio/mpeg",
    "audio/wav",
    "video/mp4",
    "video/quicktime",
    "application/pdf",
}
# the same image formats, as imagemagick names them
GEMINI_IMAGE_FORMATS = {"jpeg", "png", "webp", "bmp", "heic", "heif", "avif"}
GEMINI_VIDEO_CODECS = {"h264", "hevc", "av1", "vp9"}

# other names that servers and python's mimetypes use for those same formats
MIME_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/x-ms-bmp": "image/bmp",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/mp3": "audio/mpeg",
}

# a fetched file is held and converted in memory, so cap how big one can be
MAX_EMBEDDING_MEDIA_BYTES = 50 * 1024 * 1024


def _media_url_for_vertex(url: str) -> tuple[str, str]:
    """
    Return the url of a copy of this file in our own upload prefix that Gemini can
    read, and its mime type.

    A file already uploaded to Gooey in a format Gemini reads (going by its extension)
    is used as-is. Anything else is fetched -- anonymously if it isn't ours, so we only
    ever get what anyone on the internet could -- converted if Gemini can't read it,
    and uploaded as our own.
    """
    if not settings.GS_BUCKET_NAME:
        raise UserError(
            "Embedding media needs Google Cloud Storage (GS_BUCKET_NAME), since "
            "Vertex can't read files stored on this server."
        )
    if _is_user_media_url(url):
        mime_type = _guess_mime_type(url)
        if mime_type in GEMINI_MEDIA_TYPES:
            return url, mime_type
        data, mime_type = _download_user_media(url)
    else:
        data, mime_type = _download_public_media(url)

    data, mime_type = _convert_for_gemini(url, data, mime_type)
    segments = furl(url).path.segments
    stem = os.path.splitext(segments[-1] if segments else "")[0] or "media"
    filename = stem + (mimetypes.guess_extension(mime_type) or "")
    return upload_file_from_bytes(filename, data, mime_type), mime_type


def _is_user_media_url(url: str) -> bool:
    """Whether this is the url of a file in our own bucket's upload prefix."""
    f = furl(url)
    segments = f.path.segments
    media_segments = furl(settings.GS_MEDIA_PATH).path.segments
    prefix = [settings.GS_BUCKET_NAME, *media_segments]
    return bool(
        settings.GS_BUCKET_NAME
        and f.scheme == "https"
        and f.host == "storage.googleapis.com"
        and segments[: len(prefix)] == prefix
        # something must follow the prefix, and nothing may climb back out of it once
        # the segments are percent-decoded and rejoined into the uri
        and len(segments) > len(prefix)
        and not any(s in ("", ".", "..") or "/" in s for s in segments)
    )


def _download_user_media(url: str) -> tuple[bytes, str]:
    from google.api_core.exceptions import NotFound

    # already checked to be in our own upload prefix, so reading it with our own
    # credentials can't reach anything else
    blob = gcs_bucket().blob("/".join(furl(url).path.segments[1:]))
    try:
        blob.reload()
    except NotFound:
        raise UserError(f"Can't embed {url!r}: that file doesn't exist.")
    if blob.size > MAX_EMBEDDING_MEDIA_BYTES:
        raise _too_big_error(url)
    mime_type = _normalize_mime_type(blob.content_type) or _guess_mime_type(url)
    return blob.download_as_bytes(), mime_type


def _download_public_media(url: str) -> tuple[bytes, str]:
    # none of our credentials go with this request, so a private file -- in a GCS bucket
    # our service account can read, or anywhere else -- fails like it would for anyone
    r = requests.get(url, stream=True, timeout=(10, 60), **requests_scraping_kwargs())
    with r:
        raise_for_status(r, is_user_url=True)
        length = r.headers.get("Content-Length", "")
        if length.isdigit() and int(length) > MAX_EMBEDDING_MEDIA_BYTES:
            raise _too_big_error(url)
        data = bytearray()
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            data += chunk
            if len(data) > MAX_EMBEDDING_MEDIA_BYTES:
                raise _too_big_error(url)
        mime_type = _normalize_mime_type(r.headers.get("Content-Type"))
    return bytes(data), mime_type or _guess_mime_type(url)


def _too_big_error(url: str) -> UserError:
    return UserError(
        f"Can't embed {url!r}: it's bigger than the "
        f"{MAX_EMBEDDING_MEDIA_BYTES // (1024 * 1024)} MB limit."
    )


def _convert_for_gemini(url: str, data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Convert a file Gemini can't read into one of the same kind that it can."""
    match mime_type.split("/")[0]:
        case "image":
            # an image type gemini doesn't name is converted even if imagemagick
            # thinks its format is fine, so the mime type sent along is always right
            keep = GEMINI_IMAGE_FORMATS if mime_type in GEMINI_MEDIA_TYPES else ()
            data, converted = resize_and_convert_image(data, keep_formats=keep)
            return data, "image/png" if converted else mime_type
        case "audio":
            if mime_type in GEMINI_MEDIA_TYPES:
                return data, mime_type
            return audio_bytes_to_wav(data)[0], "audio/wav"
        case "video":
            if (
                mime_type in GEMINI_MEDIA_TYPES
                and video_codec_name(data) in GEMINI_VIDEO_CODECS
            ):
                return data, mime_type
            return video_bytes_to_mp4(data), "video/mp4"
    if mime_type == "application/pdf":
        return data, mime_type
    raise UserError(
        f"Can't embed {url!r}: it's {mime_type or 'an unknown kind of file'}, "
        "not an image, audio, video or PDF file."
    )


def _guess_mime_type(url: str) -> str:
    return _normalize_mime_type(mimetypes.guess_type(str(furl(url).path))[0])


def _normalize_mime_type(mime_type: str | None) -> str:
    mime_type = (mime_type or "").split(";")[0].strip().lower()
    if mime_type in gcs_v2.dumb_content_types:
        return ""
    return MIME_TYPE_ALIASES.get(mime_type, mime_type)


def _validate_embeddings(ret: list[list[float]], *, expected_len: int) -> np.ndarray:
    arr = np.array(ret)
    # see - https://community.openai.com/t/text-embedding-ada-002-embeddings-sometime-return-nan/279664/5
    if np.isnan(arr).any():
        raise RuntimeError("NaNs detected in embedding")
        # raise openai.error.APIError("NaNs detected in embedding")  # this lets us retry
    if arr.shape[0] != expected_len or arr.shape[1] < 128:
        raise RuntimeError(f"Unexpected shape for embedding: {arr.shape}")

    return arr


def _embed_cache_key(text: str, model_name: str) -> str:
    return f"gooey/{model_name}/v1/{sha256(text)}"


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def np_loads(data: bytes) -> np.ndarray:
    return np.load(io.BytesIO(data))


def np_dumps(a: np.ndarray) -> bytes:
    f = io.BytesIO()
    np.save(f, a)
    return f.getvalue()


def _run_gpu_embedding(texts: list[str], model_id: str) -> list[list[float]]:
    logger.info(f"{model_id=}, {len(texts)=}")
    return call_celery_task(
        "text_embeddings", pipeline={"model_id": model_id}, inputs={"texts": texts}
    )


@retry_if(openai_should_retry)
def _run_openai_embedding(
    *,
    texts: list[str],
    model_id: typing.Iterable[str] | str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[list[float]]:
    logger.info(f"{model_id=}, {len(texts)=}")
    if isinstance(model_id, str):
        model_id = [model_id]
    res = try_all(
        *[
            partial(
                get_openai_client(
                    model_str, base_url=base_url, api_key=api_key
                ).embeddings.create,
                model=model_str,
                input=texts,
            )
            for model_str in model_id
        ],
    )
    return [data.embedding for data in res.data]


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


def _run_vertex_embedding(*, contents: list[dict], model_id: str) -> list[list[float]]:
    logger.info(f"{model_id=}, {len(contents)=}")
    session, project = get_google_auth_session()
    # the model is addressed by its fully qualified resource path
    model_uri = (
        f"projects/{project}/locations/{GEMINI_EMBEDDING_LOCATION}"
        f"/publishers/google/models/{model_id}"
    )
    with ThreadPoolExecutor(max_workers=VERTEX_EMBEDDING_MAX_WORKERS) as pool:
        return list(
            pool.map(
                lambda content: _vertex_embed_content(
                    session=session, model_uri=model_uri, content=content
                ),
                contents,
            )
        )


@retry_if(http_should_retry)
def _vertex_embed_content(*, session, model_uri: str, content: dict) -> list[float]:
    r = session.post(
        f"https://aiplatform.{GEMINI_EMBEDDING_LOCATION}.rep.googleapis.com"
        f"/v1/{model_uri}:embedContent",
        json={
            "content": content,
            "embedContentConfig": {"outputDimensionality": GEMINI_EMBEDDING_DIMENSIONS},
        },
    )
    raise_for_status(r)
    return r.json()["embedding"]["values"]
