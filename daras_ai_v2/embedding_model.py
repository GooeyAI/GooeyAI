import hashlib
import io
import mimetypes
import os
import typing
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from enum import Enum
from functools import partial

import numpy as np
from aifail import (
    http_should_retry,
    retry_if,
    try_all,
)
from furl import furl
from jinja2.lexer import whitespace_re
from loguru import logger

from daras_ai.image_input import (
    GOOGLE_NEEDS_GCS_MSG,
    get_mimetype_from_url,
    is_user_uploaded_url,
    safe_filename,
    temp_upload_file_from_bytes,
    user_uploaded_url_to_gs_uri,
)
from daras_ai_v2 import settings
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


# gemini-embedding-2 has no batch call, so indexing a knowledge base would mean a Vertex
# request per chunk, and its retrieval wants query/document instructions we don't add
# yet -- so it's kept out of doc search (the model selector and its API) for now
DOC_SEARCH_EXCLUDED_EMBEDDING_MODELS = [EmbeddingModels.gemini_embedding_2]


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


# every input to a multimodal model is its own Vertex request, but a run is billed at a
# flat price, so this caps how many requests one call can fan out into
MAX_MULTIMODAL_INPUTS_PER_RUN = 100


def create_embeddings(
    texts: list[str],
    model: EmbeddingModels,
    *,
    input_images: list[str] | None = None,
    input_audio: list[str] | None = None,
    input_videos: list[str] | None = None,
    input_documents: list[str] | None = None,
) -> np.ndarray:
    """
    Embed texts and media files with `model`, one vector per input, ordered texts,
    images, audio, videos, documents.
    """
    if not any(text.strip() for text in texts):
        # all blank, like the embeddings form's empty starting box: no text to embed
        texts = []
    for i, text in enumerate(texts):
        if not text.strip():
            # dropping it would shift every later embedding off the input it belongs to
            raise UserError(
                f"texts[{i}] is empty. Remove it or fill it in, so each embedding "
                "lines up with its input."
            )
    media_urls = [
        *(input_images or []),
        *(input_audio or []),
        *(input_videos or []),
        *(input_documents or []),
    ]
    if media_urls and not model.supports_multimodal:
        raise UserError(
            f"{model.label} can only embed text, not images, audio, video or documents."
        )
    if input_images and len(input_images) > model.max_images:
        raise UserError(
            f"{model.label} accepts at most {model.max_images} images per run, "
            f"got {len(input_images)}."
        )
    if input_documents and len(input_documents) > model.max_documents:
        raise UserError(
            f"{model.label} accepts at most {model.max_documents} documents per run, "
            f"got {len(input_documents)}."
        )
    num_inputs = len(texts) + len(media_urls)
    if model.supports_multimodal and num_inputs > MAX_MULTIMODAL_INPUTS_PER_RUN:
        raise UserError(
            f"{model.label} embeds at most {MAX_MULTIMODAL_INPUTS_PER_RUN} inputs per "
            f"run, got {num_inputs}. Split them across several runs."
        )
    if not num_inputs:
        raise UserError("Please provide at least one text or file to embed.")

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
            inputs=[EmbeddingInput(text=text) for text in texts]
            + [EmbeddingInput(url=url) for url in media_urls],
            model_id=model.model_id,
        )
    else:
        ret = _run_gpu_embedding(texts=texts, model_id=model.model_id)

    return _validate_embeddings(ret, expected_len=num_inputs)


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


def _run_vertex_embedding(
    *, inputs: list[EmbeddingInput], model_id: str
) -> list[list[float]]:
    """
    Embed each input with its own :embedContent call, so each gets its own vector --
    bundling several parts into one `content` would return one aggregated vector instead.
    """
    logger.info(f"{model_id=}, {len(inputs)=}")
    session, project = get_google_auth_session()
    # the model is addressed by its fully qualified resource path
    model_uri = (
        f"projects/{project}/locations/{GEMINI_EMBEDDING_LOCATION}"
        f"/publishers/google/models/{model_id}"
    )

    def embed(inp: EmbeddingInput) -> list[float]:
        # fetching, converting and embedding each input in one thread means none waits on
        # another's download, and any copy made of it only lasts for its own call
        with _embedding_input_part(inp) as part:
            return _vertex_embed_content(
                session=session, model_uri=model_uri, content={"parts": [part]}
            )

    with ThreadPoolExecutor(
        max_workers=VERTEX_EMBEDDING_MAX_WORKERS, initializer=get_initializer()
    ) as pool:
        return list(pool.map(embed, inputs))


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


@contextmanager
def _embedding_input_part(inp: EmbeddingInput) -> typing.Iterator[dict]:
    if not inp.url:
        yield {"text": inp.text or ""}
        return
    with _gemini_readable_media(inp.url) as (gs_uri, mime_type):
        yield {"file_data": {"mime_type": mime_type, "file_uri": gs_uri}}


# what gemini-embedding-2 reads, per
# https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-multimodal-embeddings
# plus other names servers use for the same formats, which vertex accepts too
GEMINI_MEDIA_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/pjpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/heic",
    "image/heif",
    "image/avif",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/vnd.wave",
    "video/mp4",
    "video/quicktime",
    "application/pdf",
}
# the same image formats, as imagemagick names them
GEMINI_IMAGE_FORMATS = {"jpeg", "png", "webp", "bmp", "heic", "heif", "avif"}
GEMINI_VIDEO_CODECS = {"h264", "hevc", "av1", "vp9"}

# a fetched file is held and converted in memory, so cap how big one can be
MAX_EMBEDDING_MEDIA_BYTES = 50 * 1024 * 1024


@contextmanager
def _gemini_readable_media(url: str) -> typing.Iterator[tuple[str, str]]:
    """
    A gs:// uri Gemini can read this url's file from, and its mime type, valid until the
    `with` block exits.

    Like google_readable_gs_uri, but a file Gemini can't read is converted first -- which
    can mean copying one of our own uploads too -- and the mime type Vertex needs comes
    from what the server reports, not the url.
    """
    if not settings.GS_BUCKET_NAME:
        raise UserError(GOOGLE_NEEDS_GCS_MSG)
    if is_user_uploaded_url(url):
        mime_type = get_mimetype_from_url(url)
        if mime_type in GEMINI_MEDIA_TYPES:
            yield user_uploaded_url_to_gs_uri(url), mime_type
            return

    from daras_ai_v2.vector_search import download_content_bytes

    data, mime_type = download_content_bytes(
        f_url=url,
        mime_type="",
        max_bytes=MAX_EMBEDDING_MEDIA_BYTES,
        raise_on_error=True,
    )
    data, mime_type = _convert_for_gemini(url, data, mime_type)
    segments = furl(url.strip("/")).path.segments
    stem = os.path.splitext(segments[-1] if segments else "")[0] or "file"
    filename = safe_filename(stem + (mimetypes.guess_extension(mime_type) or ""))
    with temp_upload_file_from_bytes(filename, data, mime_type) as copy_url:
        yield user_uploaded_url_to_gs_uri(copy_url), mime_type


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
