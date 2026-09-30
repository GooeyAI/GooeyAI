from __future__ import annotations

import datetime
import typing
from contextlib import contextmanager

if typing.TYPE_CHECKING:
    from bots.models import SavedRun

MODEL_LABEL_ATTR = "output_filename_model_label"


@contextmanager
def output_model_label(label: str, *, total: int) -> typing.Iterator[None]:
    from celeryapp.tasks import threadlocal

    prev = getattr(threadlocal, MODEL_LABEL_ATTR, None)
    # like /video, only name outputs after the model when a run compares several
    if total > 1:
        setattr(threadlocal, MODEL_LABEL_ATTR, label)
    try:
        yield
    finally:
        setattr(threadlocal, MODEL_LABEL_ATTR, prev)


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
    from celeryapp.tasks import get_running_saved_run, threadlocal

    sr = sr or get_running_saved_run()
    if not sr:
        return None
    created_at = sr.created_at.astimezone(datetime.timezone.utc)
    # colons are stripped by safe_filename(), so use dashes in the time
    stem = f"{created_at:%Y-%m-%d %H-%M-%S} UTC - {get_output_title(sr)}"
    model_label = getattr(threadlocal, MODEL_LABEL_ATTR, None)
    if model_label:
        stem += f" - {model_label}"
    if suffix:
        stem += f" - {suffix}"
    return append_index(stem, index=index, total=total)


def get_output_title(sr: SavedRun) -> str:
    from bots.models import Workflow
    from functions.models import CalledFunction

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


def append_index(stem: str | None, *, index: int, total: int) -> str | None:
    if not stem or total <= 1:
        return stem
    return f"{stem} - {index + 1}"
