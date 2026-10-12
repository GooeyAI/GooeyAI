import typing

from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import embeddings_model_selector
from daras_ai_v2.embedding_model import EmbeddingModels, create_embeddings
from daras_ai_v2.pydantic_validation import HttpUrlStr


class EmbeddingsPage(BasePage):
    title = "Embeddings"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/aeb83ee8-889e-11ee-93dc-02420a000143/Youtube%20transcripts%20GPT%20extractions.png.png"
    workflow = Workflow.EMBEDDINGS
    slug_versions = ["embeddings", "embed", "text-embedings"]
    price = 1

    class RequestModel(BasePage.RequestModel):
        # optional so that a multimodal run can send media and no text at all. Callers
        # that only ever send texts are unaffected.
        texts: list[str] | None = None

        # only read by models with supports_multimodal set
        input_images: list[HttpUrlStr] | None = None
        input_audio: list[HttpUrlStr] | None = None
        input_videos: list[HttpUrlStr] | None = None
        input_documents: list[HttpUrlStr] | None = None

        selected_model: (
            typing.Literal[tuple(e.name for e in EmbeddingModels)] | None
        ) = None

    class ResponseModel(BaseModel):
        # one vector per input, ordered texts -> images -> audio -> videos -> documents
        embeddings: list[list[float]]

    def render_form_v2(self):
        col1, col2 = gui.columns(2)
        with col1:
            embeddings_model_selector(key="selected_model")

        texts = gui.session_state.setdefault("texts", [""])
        for i, text in enumerate(texts):
            col1, col2 = gui.columns([8, 3], responsive=False)
            with col1:
                texts[i] = gui.text_area(f"##### `texts[{i}]`", value=text)
            with col2:
                if gui.button("🗑️", className="mt-5"):
                    texts.pop(i)
                    gui.rerun()
        if gui.button("➕ Add"):
            texts.append("")
            gui.rerun()

        model = EmbeddingModels.get(gui.session_state.get("selected_model"))
        if model and model.supports_multimodal:
            self.render_media_inputs(model)
        else:
            for key in [
                "input_images",
                "input_audio",
                "input_videos",
                "input_documents",
            ]:
                gui.session_state.pop(key, None)

    def render_media_inputs(self, model: EmbeddingModels):
        gui.write("---")
        gui.caption(
            f"{model.label} embeds media into the same vector space as text, "
            "so anything uploaded here can be compared directly against a text query. "
            "Each input gets its own embedding."
        )

        if model.max_images:
            gui.file_uploader(
                label=f"##### 🏞️ Images\nUp to {model.max_images} per run.",
                key="input_images",
                accept=["image/*"],
                accept_multiple_files=True,
            )
        if model.max_audio_seconds:
            gui.file_uploader(
                label=f"##### 🎵 Audio\nUp to {model.max_audio_seconds}s each.",
                key="input_audio",
                accept=["audio/*"],
                accept_multiple_files=True,
            )
        if model.max_video_seconds:
            gui.file_uploader(
                label=f"##### 🎥 Video\nUp to {model.max_video_seconds}s each.",
                key="input_videos",
                accept=["video/*"],
                accept_multiple_files=True,
            )
        if model.max_documents:
            gui.file_uploader(
                label=(
                    f"##### 📄 Documents\nUp to {model.max_documents} PDF "
                    f"of {model.max_document_pages} pages."
                ),
                key="input_documents",
                accept=[".pdf"],
                # a single-file uploader stores a bare url, but the request wants a list.
                # max_documents is still enforced by create_embeddings
                accept_multiple_files=True,
            )

    def render_output(self):
        labels = embedding_input_labels(gui.session_state)
        for i, embedding in enumerate(gui.session_state.get("embeddings", [])):
            try:
                gui.write(f"##### `embeddings[{i}]` · {labels[i]}")
            except IndexError:
                gui.write(f"##### `embeddings[{i}]`")
            gui.json(embedding, depth=0)

    def render_run_preview_output(self, state: dict):
        texts = gui.session_state.setdefault("texts", [""])
        for i, text in enumerate(texts):
            texts[i] = gui.text_area(f"`texts[{i}]`", value=text, disabled=True)
        for key in ["input_images", "input_audio", "input_videos", "input_documents"]:
            for url in state.get(key) or []:
                gui.write(url)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: EmbeddingsPage.RequestModel = self.RequestModel.model_validate(state)
        state["embeddings"] = create_embeddings(
            request.texts or [],
            EmbeddingModels[request.selected_model],
            input_images=request.input_images,
            input_audio=request.input_audio,
            input_videos=request.input_videos,
            input_documents=request.input_documents,
        ).tolist()
        yield


def embedding_input_labels(state: dict) -> list[str]:
    """A label per embedding, in create_embeddings' order."""
    labels = [
        f"`texts[{i}]`"
        for i, text in enumerate(state.get("texts") or [])
        if text and text.strip()
    ]
    media_urls = [
        *(state.get("input_images") or []),
        *(state.get("input_audio") or []),
        *(state.get("input_videos") or []),
        *(state.get("input_documents") or []),
    ]
    return labels + [url.rsplit("/", 1)[-1] for url in media_urls]
