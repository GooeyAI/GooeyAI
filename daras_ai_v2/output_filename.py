from __future__ import annotations

import datetime
import typing

from django.utils import timezone

if typing.TYPE_CHECKING:
    from bots.models import SavedRun

T = typing.TypeVar("T")


def get_output_filenames(
    ext: str,
    items: typing.Sequence[T],
    *,
    sr: SavedRun | None = None,
    model_label: str | None = None,
    suffix: str | None = None,
) -> list[tuple[str, T]]:
    stem = get_output_filename_stem(sr, model_label=model_label, suffix=suffix)
    return [
        (append_index(stem, index=i, total=len(items)) + ext, item)
        for i, item in enumerate(items)
    ]


def get_output_filename(
    ext: str,
    *,
    sr: SavedRun | None = None,
    model_label: str | None = None,
    suffix: str | None = None,
) -> str:
    return get_output_filename_stem(sr, model_label=model_label, suffix=suffix) + ext


def get_output_filename_stem(
    sr: SavedRun | None = None,
    *,
    model_label: str | None = None,
    suffix: str | None = None,
) -> str:
    from celeryapp.tasks import get_running_saved_run

    sr = sr or get_running_saved_run()
    if sr:
        created_at = sr.created_at
    else:
        created_at = timezone.now()
    created_at = created_at.astimezone(datetime.timezone.utc)
    # colons are stripped by safe_filename(), so use dashes in the time
    stem = f"{created_at:%Y-%m-%d %H-%M-%S} UTC"
    if sr:
        stem += f" - {get_output_title(sr)}"
    if model_label:
        stem += f" - {model_label}"
    if suffix:
        stem += f" - {suffix}"
    return stem


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
