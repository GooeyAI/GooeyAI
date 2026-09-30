from __future__ import annotations

from django.utils import timezone

from bots.models import SavedRun, Workflow
from functions.models import CalledFunction


def get_output_filename_stem(sr: SavedRun | None = None) -> str | None:
    from celeryapp.tasks import get_running_saved_run

    sr = sr or get_running_saved_run()
    if not sr:
        return None
    # colons are stripped by safe_filename(), so use dashes in the time
    return f"{timezone.now():%Y-%m-%d %H-%M-%S} UTC - {get_output_title(sr)}"


def get_output_title(sr: SavedRun) -> str:
    called_fn = (
        CalledFunction.objects.select_related(
            "saved_run__parent_version__published_run"
        )
        .filter(function_run=sr)
        .first()
    )
    if called_fn:
        # when called as a tool, name the output after the calling agent
        sr = called_fn.saved_run
    return Workflow(sr.workflow).page_cls.get_run_title(sr, sr.parent_published_run())
