import datetime
import uuid
from unittest.mock import patch

import pytest

from bots.models import PublishedRun, SavedRun, Workflow
from daras_ai.image_input import safe_filename
from daras_ai_v2.output_filename import get_output_filename, get_output_filename_stem
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
