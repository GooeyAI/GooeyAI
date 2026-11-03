import pytest

import gooey_gui as gui
from daras_ai_v2 import embedding_model
from daras_ai_v2.embedding_model import (
    EmbeddingModels,
    create_embeddings,
)
from daras_ai_v2.exceptions import UserError
from recipes import embeddings_page
from recipes.embeddings_page import EmbeddingsPage

GEMINI = EmbeddingModels.gemini_embedding_2
OPENAI = EmbeddingModels.openai_3_large
MEDIA = "https://storage.googleapis.com/gooey-test-bucket/daras_ai/media"


@pytest.fixture
def sent(monkeypatch):
    """Stub the providers, recording what each was asked to embed."""
    calls = []

    def vertex(*, texts, media_urls, model_id):
        calls.append([*texts, *media_urls])
        return [[0.0] * 3072 for _ in [*texts, *media_urls]]

    def openai(*, texts, model_id, **kwargs):
        calls.append(list(texts))
        return [[0.0] * 3072 for _ in texts]

    monkeypatch.setattr(embedding_model, "run_gemini_embedding", vertex)
    monkeypatch.setattr(embedding_model, "_run_openai_embedding", openai)
    return calls


def test_one_vector_per_input_in_order(sent):
    vectors = create_embeddings(
        ["a", "b"],
        GEMINI,
        input_images=[f"{MEDIA}/u/cat.png"],
        input_audio=[f"{MEDIA}/u/clip.wav"],
        input_videos=[f"{MEDIA}/u/clip.mp4"],
        input_documents=[f"{MEDIA}/u/doc.pdf"],
    )
    assert len(vectors) == 6
    assert sent == [
        [
            "a",
            "b",
            f"{MEDIA}/u/cat.png",
            f"{MEDIA}/u/clip.wav",
            f"{MEDIA}/u/clip.mp4",
            f"{MEDIA}/u/doc.pdf",
        ]
    ]


def test_text_only_callers_are_unchanged(sent):
    # create_embeddings_cached and doc search call it like this
    create_embeddings(["a", "b"], OPENAI)
    assert sent == [["a", "b"]]


def test_all_blank_texts_mean_no_text(sent):
    # the form starts with one empty box, which shouldn't block a media-only run
    create_embeddings([""], GEMINI, input_images=[f"{MEDIA}/u/cat.png"])
    assert sent == [[f"{MEDIA}/u/cat.png"]]


@pytest.mark.parametrize("texts", [[], [""], ["  ", ""]])
def test_nothing_to_embed_is_an_error(sent, texts):
    with pytest.raises(UserError, match="at least one"):
        create_embeddings(texts, GEMINI)


def test_media_for_a_text_only_model_is_an_error_not_ignored(sent):
    with pytest.raises(UserError, match="only embed text"):
        create_embeddings(["a"], OPENAI, input_images=[f"{MEDIA}/u/cat.png"])
    assert sent == []


@pytest.mark.parametrize(
    "field, limit", [("input_images", GEMINI.value.max_images), ("input_documents", 1)]
)
def test_per_model_count_limits(sent, field, limit):
    with pytest.raises(UserError, match="at most"):
        create_embeddings([], GEMINI, **{field: [f"{MEDIA}/u/f"] * (limit + 1)})


def test_run_passes_the_request_straight_to_create_embeddings(monkeypatch):
    calls = []

    def create(texts, model, **kwargs):
        calls.append((texts, model, kwargs))
        return embedding_model.np.zeros((1, 3072))

    monkeypatch.setattr(embeddings_page, "create_embeddings", create)
    state = {
        "selected_model": GEMINI.name,
        "texts": ["a"],
        "input_images": [f"{MEDIA}/u/cat.png"],
    }
    list(EmbeddingsPage.run(EmbeddingsPage, state))
    assert calls == [
        (
            ["a"],
            GEMINI,
            dict(
                input_images=[f"{MEDIA}/u/cat.png"],
                input_audio=None,
                input_videos=None,
                input_documents=None,
            ),
        )
    ]


def test_every_media_uploader_stores_a_list(monkeypatch):
    # a single-file uploader stores a bare url, which RequestModel's list fields reject,
    # so a one-pdf upload would fail before embedding anything
    uploaders = {}
    monkeypatch.setattr(
        gui, "file_uploader", lambda **kwargs: uploaders.update({kwargs["key"]: kwargs})
    )
    monkeypatch.setattr(gui, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui, "caption", lambda *args, **kwargs: None)

    embeddings_page.render_media_inputs(GEMINI)

    assert set(uploaders) == {
        "input_images",
        "input_audio",
        "input_videos",
        "input_documents",
    }
    assert all(kwargs["accept_multiple_files"] for kwargs in uploaders.values())
