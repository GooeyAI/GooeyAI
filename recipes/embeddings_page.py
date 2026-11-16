import typing

from pydantic import BaseModel

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import embeddings_model_selector
from daras_ai_v2.embedding_model import EmbeddingModels, create_embeddings
from daras_ai_v2.pydantic_validation import HttpUrlStr

MEDIA_INPUT_KEYS = ["input_images", "input_audio", "input_videos", "input_documents"]


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
        if model and model.value.supports_multimodal:
            render_media_inputs(model)
        else:
            for key in MEDIA_INPUT_KEYS:
                gui.session_state.pop(key, None)

    def render_output(self):
        for i, embedding in enumerate(gui.session_state.get("embeddings", [])):
            gui.write(f"##### `embeddings[{i}]`")
            gui.json(embedding, depth=0)

    def render_run_preview_output(self, state: dict):
        texts = gui.session_state.setdefault("texts", [""])
        for i, text in enumerate(texts):
            texts[i] = gui.text_area(f"`texts[{i}]`", value=text, disabled=True)
        for key in MEDIA_INPUT_KEYS:
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


def render_media_inputs(model: EmbeddingModels):
    gui.write("---")
    gui.caption(
        f"{model.label} embeds media into the same vector space as text, "
        "so each file can be compared directly against a text query."
    )
    gui.file_uploader(
        label=f"##### 🏞️ Images\nUp to {model.value.max_images} per run.",
        key="input_images",
        accept=["image/*"],
        accept_multiple_files=True,
    )
    gui.file_uploader(
        label="##### 🎵 Audio\nUp to 180s each.",
        key="input_audio",
        accept=["audio/*"],
        accept_multiple_files=True,
    )
    gui.file_uploader(
        label="##### 🎥 Video\nUp to 120s each.",
        key="input_videos",
        accept=["video/*"],
        accept_multiple_files=True,
    )
    gui.file_uploader(
        label=f"##### 📄 Documents\nUp to {model.value.max_documents} PDF of 6 pages.",
        key="input_documents",
        accept=[".pdf"],
        # the request wants a list, which a single-file uploader doesn't store
        accept_multiple_files=True,
    )
