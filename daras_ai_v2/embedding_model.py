import hashlib
import io
import typing
from enum import Enum
from functools import partial

import numpy as np
from aifail import (
    retry_if,
    try_all,
)
from jinja2.lexer import whitespace_re
from loguru import logger

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.gemini_embedding import run_gemini_embedding
from daras_ai_v2.gpu_server import call_celery_task
from daras_ai_v2.language_model import get_openai_client, openai_should_retry
from daras_ai_v2.redis_cache import (
    get_redis_cache,
)


class EmbeddingModel(typing.NamedTuple):
    model_id: typing.Iterable[str] | str
    label: str

    supports_multimodal: bool = False
    max_images: int = 0
    max_documents: int = 0


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
        max_documents=1,
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
    media_urls = [
        *(input_images or []),
        *(input_audio or []),
        *(input_videos or []),
        *(input_documents or []),
    ]
    if media_urls and not model.value.supports_multimodal:
        raise UserError(
            f"{model.label} can only embed text, not images, audio, video or documents."
        )
    if input_images and len(input_images) > model.value.max_images:
        raise UserError(
            f"{model.label} accepts at most {model.value.max_images} images per run, "
            f"got {len(input_images)}."
        )
    if input_documents and len(input_documents) > model.value.max_documents:
        raise UserError(
            f"{model.label} accepts at most {model.value.max_documents} documents per run, "
            f"got {len(input_documents)}."
        )
    num_inputs = len(texts) + len(media_urls)
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
        ret = run_gemini_embedding(
            texts=texts, media_urls=media_urls, model_id=model.model_id
        )
    else:
        ret = _run_gpu_embedding(texts=texts, model_id=model.model_id)

    arr = np.array(ret)
    # see - https://community.openai.com/t/text-embedding-ada-002-embeddings-sometime-return-nan/279664/5
    if np.isnan(arr).any():
        raise RuntimeError("NaNs detected in embedding")
        # raise openai.error.APIError("NaNs detected in embedding")  # this lets us retry
    if arr.shape[0] != num_inputs or arr.shape[1] < 128:
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
