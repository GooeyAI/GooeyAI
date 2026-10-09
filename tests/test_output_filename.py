import datetime
import uuid
from unittest.mock import patch

import pytest

from bots.models import PublishedRun, SavedRun, Workflow
from daras_ai.image_input import safe_filename
from daras_ai_v2.output_filename import (
    get_output_filename,
    get_output_filename_stem,
    get_output_filenames,
)
from daras_ai_v2.upscaler_models import UpscalerModels, run_upscaler_model
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


def test_uses_the_current_time_outside_a_run():
    with (
        patch("celeryapp.tasks.get_running_saved_run", return_value=None),
        patch("django.utils.timezone.now", return_value=CREATED_AT),
    ):
        assert get_output_filename_stem() == PREFIX
        assert get_output_filename(".png") == f"{PREFIX}.png"
        assert get_output_filenames(".png", ["a", "b"], suffix="Mask") == [
            (f"{PREFIX} - Mask - 1.png", "a"),
            (f"{PREFIX} - Mask - 2.png", "b"),
        ]


def test_explicit_run_wins_over_the_running_one(transactional_db):
    sr = _make_titled_sr(Workflow.VIDEO_GEN, "Explicit")
    running = _make_titled_sr(Workflow.VIDEO_GEN, "Running")

    with patch("celeryapp.tasks.get_running_saved_run", return_value=running):
        assert get_output_filename(".ogg", sr=sr) == f"{PREFIX} - Explicit.ogg"


@pytest.mark.parametrize(
    "items, suffix, expected",
    [
        (["a"], "Mask", [(f"{PREFIX} - Segmenter - Mask.png", "a")]),
        (["a"], None, [(f"{PREFIX} - Segmenter.png", "a")]),
        (
            ["a", "b", "c"],
            None,
            [
                (f"{PREFIX} - Segmenter - 1.png", "a"),
                (f"{PREFIX} - Segmenter - 2.png", "b"),
                (f"{PREFIX} - Segmenter - 3.png", "c"),
            ],
        ),
        (
            ["a", "b"],
            "Cutout",
            [
                (f"{PREFIX} - Segmenter - Cutout - 1.png", "a"),
                (f"{PREFIX} - Segmenter - Cutout - 2.png", "b"),
            ],
        ),
    ],
)
def test_suffix_and_index(items, suffix, expected, transactional_db):
    sr = _make_titled_sr(Workflow.IMAGE_SEGMENTATION, "Segmenter")

    assert get_output_filenames(".png", items, sr=sr, suffix=suffix) == expected


def test_survives_safe_filename(transactional_db):
    sr = _make_titled_sr(Workflow.VIDEO_GEN, "Birds: v5.4 / In Vitrine " + "x" * 120)

    name, _ = get_output_filenames(".mp4", range(3), sr=sr)[1]
    name = safe_filename(name)

    assert name.startswith(PREFIX)
    assert name.endswith(" - 2.mp4")
    assert ":" not in name and "/" not in name
    assert len(name) == 100 + len(".mp4") - 1


def test_safe_filename_collapses_spaces_left_by_emoji():
    name = safe_filename(f"{PREFIX} - Edit - ✨ InstructPix2Pix (Tim Brooks).png")

    assert name == f"{PREFIX} - Edit - InstructPix2Pix Tim Brooks.png"


def test_model_label_goes_before_the_suffix_and_index(transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_TEXT2IMG, "Bird Plates")

    name, _ = get_output_filenames(
        ".png", range(2), sr=sr, model_label="FLUX.1 dev", suffix="Mask"
    )[1]

    assert name == f"{PREFIX} - Bird Plates - FLUX.1 dev - Mask - 2.png"


def test_upscaler_names_outputs_after_the_model(transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_UPSCALER, "Upscale Birds")
    model = UpscalerModels.gfpgan_1_4

    with (
        patch("celeryapp.tasks.get_running_saved_run", return_value=sr),
        patch(
            "daras_ai_v2.upscaler_models.call_celery_task_outfile",
            side_effect=lambda *args, filename, **kwargs: [filename],
        ),
    ):
        name = run_upscaler_model(
            selected_model=model, video="https://example.com/bird.mp4", scale=2
        )

    assert name == f"{PREFIX} - Upscale Birds - {model.label}.mp4"


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
