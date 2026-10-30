from __future__ import annotations

import mimetypes
import os
import typing
from datetime import timedelta

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.template.defaultfilters import filesizeformat
from fastapi.requests import Request
from furl import furl

import gooey_gui as gui
from daras_ai_v2 import gcs_v2
from gooey_gui.types.workspace_files_props import (
    WorkspaceFileBrowserProps,
    WorkspaceFileEntry,
)

if typing.TYPE_CHECKING:
    from firebase_admin import storage

    from workspaces.models import Workspace

WORKSPACE_FILE_DOWNLOAD_URL = "/__/workspace-files/download/"

# served as plain text so the browser displays them instead of downloading
TEXT_EXTENSIONS = {
    ".cfg", ".csv", ".ini", ".ipynb", ".js", ".json", ".jsonl", ".log", ".md",
    ".py", ".sh", ".sql", ".toml", ".ts", ".tsv", ".txt", ".xml", ".yaml", ".yml",
}  # fmt: skip
HTML_EXTENSIONS = {".htm", ".html"}
INLINE_MIME_PREFIXES = ("image/", "audio/", "video/", "application/pdf")


def manage_workspace_files(
    request: Request, *, workspace: Workspace, page_token: str | None
):
    blobs, next_page_token = list_workspace_files(workspace, page_token=page_token)

    if next_page_token:
        next_page_url = str(
            furl(request.url)
            .set(origin=None)
            .set(args=dict(page_token=next_page_token))
        )
    else:
        next_page_url = None

    prefix = gcs_v2.workspace_files_prefix(workspace.id)
    gui.model_component(
        WorkspaceFileBrowserProps(
            description=(
                "Files written by your Python and Bash functions to their working directory "
                f"(/workspace) are stored here and shared across all runs in "
                f"{workspace.display_name(request.user)}."
            ),
            entries=[
                WorkspaceFileEntry(
                    path=blob.name.removeprefix(prefix),
                    href=str(
                        furl(WORKSPACE_FILE_DOWNLOAD_URL).set(
                            args=dict(path=blob.name.removeprefix(prefix))
                        )
                    ),
                    size_label=filesizeformat(blob.size or 0),
                    updated_at_label=str(naturaltime(blob.updated)),
                )
                for blob in blobs
            ],
            next_page_url=next_page_url,
        )
    )


def list_workspace_files(
    workspace: Workspace, *, page_token: str | None, page_size: int = 100
) -> tuple[list[storage.Blob], str | None]:
    from firebase_admin import storage

    prefix = gcs_v2.workspace_files_prefix(workspace.id)
    iterator = storage.bucket(gcs_v2.GCS_BUCKET_NAME).list_blobs(
        prefix=prefix, max_results=page_size, page_token=page_token
    )
    page = next(iterator.pages, None)
    if page is None:
        return [], None
    # skip zero-byte "folder" placeholders created by the sandbox's bucket mount
    blobs = [blob for blob in page if not blob.name.endswith("/")]
    return blobs, iterator.next_page_token


def get_workspace_file_blob(workspace: Workspace, path: str) -> storage.Blob | None:
    from firebase_admin import storage

    path = path.strip("/")
    if not path or ".." in path.split("/"):
        return None
    blob_name = gcs_v2.workspace_files_prefix(workspace.id) + path
    return storage.bucket(gcs_v2.GCS_BUCKET_NAME).get_blob(blob_name)


def get_workspace_file_signed_url(blob: storage.Blob) -> str:
    content_type = get_inline_content_type(blob.name)
    if not content_type:
        return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60))
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=60),
        response_type=content_type,
        response_disposition="inline",
    )


def get_inline_content_type(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXTENSIONS:
        return "text/plain; charset=utf-8"
    if ext in HTML_EXTENSIONS:
        return "text/html; charset=utf-8"
    mime_type = mimetypes.guess_type(path)[0]
    if mime_type and mime_type.startswith(INLINE_MIME_PREFIXES):
        return mime_type
    return None
