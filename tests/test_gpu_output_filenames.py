import contextlib
import datetime
import uuid
from unittest.mock import patch

import pytest

from bots.models import PublishedRun, SavedRun, Workflow
from daras_ai_v2 import gpu_server

CREATED_AT = datetime.datetime(2026, 9, 24, 12, 41, 10, tzinfo=datetime.timezone.utc)
PREFIX = "2026-09-24 12-41-10 UTC"


@pytest.fixture
def signed_filenames():
    names = []

    @contextlib.contextmanager
    def fake_signed_url(filename, content_type=None):
        names.append(filename)
        yield f"upload/{filename}", f"public/{filename}"

    with (
        patch.object(gpu_server, "generate_signed_url", fake_signed_url),
        patch.object(gpu_server, "call_celery_task", return_value={}),
    ):
        yield names


def test_sd_multi_numbers_each_output(signed_filenames, transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_TEXT2IMG, "Bird Plates")

    with patch("celeryapp.tasks.get_running_saved_run", return_value=sr):
        gpu_server.call_sd_multi(
            "diffusion.text2img",
            pipeline={},
            inputs={"prompt": ["a bird"], "num_images_per_prompt": 3},
        )

    assert signed_filenames == [
        f"{PREFIX} - Bird Plates - 1.png",
        f"{PREFIX} - Bird Plates - 2.png",
        f"{PREFIX} - Bird Plates - 3.png",
    ]


def test_sd_multi_single_output_is_not_numbered(signed_filenames, transactional_db):
    sr = _make_titled_sr(Workflow.COMPARE_TEXT2IMG, "Bird Plates")

    with patch("celeryapp.tasks.get_running_saved_run", return_value=sr):
        gpu_server.call_sd_multi(
            "diffusion.text2img",
            pipeline={},
            inputs={"prompt": ["a bird"], "num_images_per_prompt": 1},
        )

    assert signed_filenames == [f"{PREFIX} - Bird Plates.png"]


@pytest.mark.django_db
def test_sd_multi_keeps_the_old_name_outside_a_run(signed_filenames):
    with patch("celeryapp.tasks.get_running_saved_run", return_value=None):
        gpu_server.call_sd_multi(
            "diffusion.text2img",
            pipeline={},
            inputs={"prompt": ["a bird"], "num_images_per_prompt": 2},
        )

    assert signed_filenames == ["gooey.ai - ['a bird'].png"] * 2


def test_single_filename_is_reused_for_every_output(signed_filenames):
    urls, _ = gpu_server.call_celery_task_outfile_with_ret(
        "wav2lip",
        pipeline={},
        inputs={},
        content_type="video/mp4",
        filename="gooey.ai lipsync.mp4",
        num_outputs=2,
    )

    assert signed_filenames == ["gooey.ai lipsync.mp4"] * 2
    assert urls == ["public/gooey.ai lipsync.mp4"] * 2


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
