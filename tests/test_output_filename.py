import re
import uuid
from unittest.mock import patch

import pytest

from bots.models import PublishedRun, SavedRun, Workflow
from daras_ai_v2.output_filename import get_output_filename_stem
from functions.models import CalledFunction, FunctionTrigger

TIMESTAMP_PREFIX = r"^\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2} UTC - "


def test_names_a_direct_run_after_its_own_workflow(transactional_db):
    video_pr = _make_published_run(Workflow.VIDEO_GEN, title="Bird Video Render")
    sr = _make_sr(Workflow.VIDEO_GEN, parent_version=video_pr.versions.first())

    assert re.match(
        TIMESTAMP_PREFIX + "Bird Video Render$", get_output_filename_stem(sr)
    )


def test_names_an_unsaved_run_after_the_recipe(transactional_db):
    sr = _make_sr(Workflow.VIDEO_GEN)

    stem = get_output_filename_stem(sr)

    assert re.match(TIMESTAMP_PREFIX + re.escape(Workflow.VIDEO_GEN.label) + "$", stem)


def test_names_a_tool_call_after_the_calling_agent(transactional_db):
    agent_pr = _make_published_run(Workflow.VIDEO_BOTS, title="Birds Agent")
    video_pr = _make_published_run(Workflow.VIDEO_GEN, title="Bird Video Render")
    agent_sr = _make_sr(Workflow.VIDEO_BOTS, parent_version=agent_pr.versions.first())
    tool_sr = _make_sr(Workflow.VIDEO_GEN, parent_version=video_pr.versions.first())
    CalledFunction.objects.create(
        saved_run=agent_sr,
        function_run=tool_sr,
        trigger=FunctionTrigger.prompt.db_value,
    )

    assert re.match(
        TIMESTAMP_PREFIX + "Birds Agent$", get_output_filename_stem(tool_sr)
    )


def test_uses_the_running_saved_run_by_default(transactional_db):
    video_pr = _make_published_run(Workflow.VIDEO_GEN, title="Bird Video Render")
    sr = _make_sr(Workflow.VIDEO_GEN, parent_version=video_pr.versions.first())

    with patch("celeryapp.tasks.get_running_saved_run", return_value=sr):
        stem = get_output_filename_stem()

    assert re.match(TIMESTAMP_PREFIX + "Bird Video Render$", stem)


@pytest.mark.django_db
def test_returns_none_outside_a_run():
    with patch("celeryapp.tasks.get_running_saved_run", return_value=None):
        assert get_output_filename_stem() is None


def _make_published_run(workflow: Workflow, *, title: str) -> PublishedRun:
    return PublishedRun.objects.create_with_version(
        workflow=workflow,
        published_run_id=uuid.uuid4().hex[:12],
        saved_run=_make_sr(workflow),
        user=None,
        workspace=None,
        title=title,
    )


def _make_sr(workflow: Workflow, **kwargs) -> SavedRun:
    return SavedRun.objects.create(workflow=workflow, run_id=uuid.uuid4().hex, **kwargs)
