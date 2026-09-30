from __future__ import annotations

import datetime

from bots.models import SavedRun, Workflow
from functions.models import CalledFunction


def get_output_filename(
    ext: str,
    *,
    sr: SavedRun | None = None,
    suffix: str | None = None,
    index: int = 0,
    total: int = 1,
) -> str | None:
    stem = get_output_filename_stem(sr, suffix=suffix, index=index, total=total)
    if not stem:
        return None
    return stem + ext


def get_output_filename_stem(
    sr: SavedRun | None = None,
    *,
    suffix: str | None = None,
    index: int = 0,
    total: int = 1,
) -> str | None:
    from celeryapp.tasks import get_running_saved_run

    sr = sr or get_running_saved_run()
    if not sr:
        return None
    created_at = sr.created_at.astimezone(datetime.timezone.utc)
    # colons are stripped by safe_filename(), so use dashes in the time
    parts = [f"{created_at:%Y-%m-%d %H-%M-%S} UTC", get_output_title(sr)]
    if suffix:
        parts.append(suffix)
    if total > 1:
        parts.append(str(index + 1))
    return " - ".join(parts)


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
