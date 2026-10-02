import datetime
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bots.models import PublishedRun, SavedRun, Workflow
from daras_ai.image_input import safe_filename
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.output_filename import (
    get_output_filename,
    get_output_filename_stem,
    output_model_label,
)
from daras_ai_v2.upscaler_models import UpscalerModels
from recipes.CompareUpscaler import CompareUpscalerPage
from recipes.Text2Audio import Text2AudioPage
from functions.models import CalledFunction, FunctionTrigger

CREATED_AT = datetime.datetime(2026, 9, 24, 12, 41, 10, tzinfo=datetime.timezone.utc)
PREFIX = "2026-09-24 12-41-10 UTC"


def test_names_a_direct_run_after_its_own_workflow(transactional_db):
    sr = _make_titled_sr(Workflow.VIDEO_GEN, "Bird Video Render")

    assert get_output_filename_stem(sr) == f"{PREFIX} - Bird Video Render"


def test_names_an_unsaved_run_after_the_recipe(transactional_db):
    sr = _make_sr(Workflow.VIDEO_GEN)

    assert get_output_filename_stem(sr) == f"{PREFIX} - {Workflow.VIDEO_GEN.label}"


def test_names_a_tool_call_after_the_calling_agent(transactional_db):
    agent_sr = _make_titled_sr(Workflow.VIDEO_BOTS, "Birds Agent")
    tool_sr = _make_titled_sr(Workflow.VIDEO_GEN, "Bird Video Render")
    CalledFunction.objects.create(
        saved_run=agent_sr,
        function_run=tool_sr,
        trigger=FunctionTrigger.prompt.db_value,
    )

    assert get_output_filename_stem(tool_sr) == f"{PREFIX} - Birds Agent"


def test_uses_the_running_saved_run_by_default(transactional_db):
    sr = _make_titled_sr(Workflow.VIDEO_GEN, "Bird Video Render")

    with patch("celeryapp.tasks.get_running_saved_run", return_value=sr):
        assert get_output_filename(".mp4") == f"{PREFIX} - Bird Video Render.mp4"


@pytest.mark.django_db
def test_returns_none_outside_a_run():
    with patch("celeryapp.tasks.get_running_saved_run", return_value=None):
        assert get_output_filename_stem() is None
        assert get_output_filename(".png") is None


def test_explicit_run_wins_over_the_running_one(transactional_db):
    sr = _make_titled_sr(Workflow.VIDEO_GEN, "Explicit")
    running = _make_titled_sr(Workflow.VIDEO_GEN, "Running")

    with patch("celeryapp.tasks.get_running_saved_run", return_value=running):
        assert get_output_filename(".ogg", sr=sr) == f"{PREFIX} - Explicit.ogg"


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"suffix": "Mask"}, f"{PREFIX} - Segmenter - Mask.png"),
        ({"index": 0, "total": 1}, f"{PREFIX} - Segmenter.png"),
        ({"index": 2, "total": 4}, f"{PREFIX} - Segmenter - 3.png"),
        (
            {"suffix": "Cutout", "index": 0, "total": 2},
            f"{PREFIX} - Segmenter - Cutout - 1.png",
        ),
    ],
)
def test_suffix_and_index(kwargs, expected, transactional_db):
    sr = _make_titled_sr(Workflow.IMAGE_SEGMENTATION, "Segmenter")

    assert get_output_filename(".png", sr=sr, **kwargs) == expected


def test_survives_safe_filename(transactional_db):
    sr = _make_titled_sr(Workflow.VIDEO_GEN, "Birds: v5.4 / In Vitrine " + "x" * 120)

    name = safe_filename(get_output_filename(".mp4", sr=sr, index=1, total=3))

    assert name.startswith(PREFIX)
    assert name.endswith(" - 2.mp4")
    assert ":" not in name and "/" not in name
    assert len(name) == 100 + len(".mp4") - 1


def test_model_label_is_added_when_several_models_run(transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_TEXT2IMG, "Bird Plates")

    with output_model_label("FLUX.1 dev", total=2):
        name = get_output_filename(".png", sr=sr, suffix="Mask", index=1, total=2)

    assert name == f"{PREFIX} - Bird Plates - FLUX.1 dev - Mask - 2.png"


def test_model_label_is_skipped_for_a_single_model(transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_TEXT2IMG, "Bird Plates")

    with output_model_label("FLUX.1 dev", total=1):
        assert get_output_filename(".png", sr=sr) == f"{PREFIX} - Bird Plates.png"


def test_model_label_is_reset_after_the_block_even_on_error(transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_TEXT2IMG, "Bird Plates")

    with pytest.raises(RuntimeError):
        with output_model_label("FLUX.1 dev", total=2):
            raise RuntimeError

    assert get_output_filename(".png", sr=sr) == f"{PREFIX} - Bird Plates.png"


def test_model_label_reaches_worker_threads(transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_TEXT2IMG, "Bird Plates")

    with output_model_label("FLUX.1 dev", total=2):
        names = map_parallel(
            lambda i: get_output_filename(".png", sr=sr, index=i, total=2), [0, 1]
        )

    assert names == [
        f"{PREFIX} - Bird Plates - FLUX.1 dev - 1.png",
        f"{PREFIX} - Bird Plates - FLUX.1 dev - 2.png",
    ]


def test_compare_upscaler_names_each_model(transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_UPSCALER, "Upscale Birds")
    models = list(UpscalerModels)[:2]
    request = CompareUpscalerPage.RequestModel(
        input_video="https://example.com/bird.mp4",
        scale=2,
        selected_models=[model.name for model in models],
    )
    response = SimpleNamespace()
    page = CompareUpscalerPage.__new__(CompareUpscalerPage)
    page.request = SimpleNamespace(user=SimpleNamespace(disable_safety_checker=True))

    with (
        patch("celeryapp.tasks.get_running_saved_run", return_value=sr),
        patch(
            "recipes.CompareUpscaler.run_upscaler_model",
            side_effect=lambda **kwargs: get_output_filename(".mp4"),
        ),
    ):
        list(page.run_v2(request, response))

    assert response.output_videos == {
        model.name: f"{PREFIX} - Upscale Birds - {model.label}.mp4" for model in models
    }


def test_text2audio_without_num_outputs_requests_no_files():
    state = {"text_prompt": "bird song", "selected_models": ["audio_ldm"]}

    with patch("recipes.Text2Audio.call_celery_task_outfile", return_value=[]) as call:
        list(Text2AudioPage.__new__(Text2AudioPage).run(state))

    assert call.call_args.kwargs["filename"] == []
    assert call.call_args.kwargs["num_outputs"] == 0


def _make_titled_sr(workflow: Workflow, title: str) -> SavedRun:
    pr = PublishedRun.objects.create_with_version(
        workflow=workflow,
        published_run_id=uuid.uuid4().hex[:12],
        saved_run=_make_sr(workflow),
        user=None,
        workspace=None,
        title=title,
    )
    return _make_sr(workflow, parent_version=pr.versions.first())


def _make_sr(workflow: Workflow, **kwargs) -> SavedRun:
    sr = SavedRun.objects.create(workflow=workflow, run_id=uuid.uuid4().hex, **kwargs)
    SavedRun.objects.filter(pk=sr.pk).update(created_at=CREATED_AT)
    sr.refresh_from_db()
    return sr
