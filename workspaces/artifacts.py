"""Artifacts: websites made by functions, kept as folders of the workspace files.

A top-level folder that holds an `index.html` is an artifact. Every change to the folder - an
Ask Gooey edit, a restore - is saved as the next version and is live at once; Versions
restores an earlier one.
"""

from __future__ import annotations

import re
import typing
from datetime import datetime, timedelta
from urllib.parse import quote

from django.db import transaction
from django.db.models import Max
from django.utils.text import slugify
from furl import furl

import gooey_gui as gui
from daras_ai_v2 import gcs_v2, icons, settings
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from files.models import Artifact, ArtifactChat, ArtifactVersion

if typing.TYPE_CHECKING:
    from fastapi import Request
    from firebase_admin import storage

    from app_users.models import AppUser
    from bots.models import SavedRun
    from workspaces.models import Workspace


# Workflow tab routes that sit under `/{page_slug}/`; `/<handle>/<name>/` can't reach a
# folder with one of these names, so the Bash tool is told not to use them.
RESERVED_FOLDER_NAMES = (
    "api",
    "examples",
    "history",
    "integrations",
    "preview",
    "saved",
    "usage",
)
ARTIFACT_INDEX = "index.html"
VERSIONS_DIR = ".versions"
# HTML up to this size is embedded in the page (srcdoc), so it never expires
MAX_INLINE_HTML_BYTES = 1_000_000
ARTIFACT_SANDBOX = (
    "allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
)
ARTIFACTS_PATH = "/artefacts/"


def record_artifact_changes(
    workspace: Workspace,
    *,
    user: AppUser,
    since: datetime,
    caller_sr: SavedRun | None = None,
) -> list[Artifact]:
    """After a Python or Bash run: save a version of every artifact folder it changed, and
    register new ones. When Ask Gooey made a new one, its chat opens on the new page."""
    from bots.models import SavedRun

    prefix = gcs_v2.workspace_files_prefix(workspace.id)
    folders = set()
    for blob in _bucket().list_blobs(prefix=prefix):
        relative = blob.name.removeprefix(prefix)
        if "/" not in relative or blob.updated < since:
            continue
        folders.add(relative.split("/")[0])

    builder_sr = None
    if caller_sr and caller_sr.surface == SavedRun.Surface.builder_prompt:
        builder_sr = caller_sr

    changed = []
    for folder in sorted(folders):
        if not is_artifact_folder_name(folder):
            continue
        if not get_artifact_blob(workspace, f"{folder}/{ARTIFACT_INDEX}"):
            continue
        artifact, created = Artifact.objects.get_or_create(
            workspace=workspace, folder=folder, defaults=dict(created_by=user)
        )
        save_version(artifact, user=user, builder_sr=builder_sr)
        changed.append(artifact)
        if created and builder_sr:
            ArtifactChat.objects.update_or_create(
                artifact=artifact,
                user=user,
                defaults=dict(builder_saved_run=builder_sr),
            )
            # the standalone Ask Gooey page follows this to the new artifact
            builder_sr.redirect_url = get_artifact_url(artifact)
            builder_sr.save(update_fields=["redirect_url"])
    return changed


def sync_workspace_artifacts(workspace: Workspace) -> None:
    """Register folders with an index.html that have no row yet, each with a first version."""
    prefix = gcs_v2.workspace_files_prefix(workspace.id)
    blobs = _bucket().list_blobs(
        prefix=prefix, match_glob=f"{prefix}*/{ARTIFACT_INDEX}"
    )
    folders = {blob.name.removeprefix(prefix).split("/")[0] for blob in blobs}
    existing = set(
        Artifact.objects.filter(workspace=workspace).values_list("folder", flat=True)
    )
    for folder in sorted(folders - existing):
        if not is_artifact_folder_name(folder):
            continue
        artifact, created = Artifact.objects.get_or_create(
            workspace=workspace, folder=folder
        )
        if created:
            save_version(artifact, user=None, note="Found in the workspace files")


def get_artifact(workspace: Workspace, folder: str) -> Artifact | None:
    if not is_artifact_folder_name(folder):
        return None
    artifact = Artifact.objects.filter(workspace=workspace, folder=folder).first()
    if artifact:
        return artifact
    if not get_artifact_blob(workspace, f"{folder}/{ARTIFACT_INDEX}"):
        return None
    artifact, created = Artifact.objects.get_or_create(
        workspace=workspace, folder=folder
    )
    if created:
        save_version(artifact, user=None, note="Found in the workspace files")
    return artifact


def save_version(
    artifact: Artifact,
    *,
    user: AppUser | None,
    note: str = "",
    builder_sr: SavedRun | None = None,
) -> ArtifactVersion:
    """Snapshot `<folder>/` as the next version, which is now the live one."""
    with transaction.atomic():
        artifact = Artifact.objects.select_for_update().get(id=artifact.id)
        number = (artifact.versions.aggregate(n=Max("number"))["n"] or 0) + 1
        copy_dir(artifact.workspace, live_dir(artifact), version_dir(artifact, number))
        version = ArtifactVersion.objects.create(
            artifact=artifact,
            number=number,
            created_by=user,
            note=note,
            builder_saved_run=builder_sr,
        )
        artifact.live_version = version
        artifact.save(update_fields=["live_version", "updated_at"])
    return version


def restore_version(
    artifact: Artifact, version: ArtifactVersion, *, user: AppUser
) -> ArtifactVersion:
    """Put an earlier version back on the page, as a new version."""
    copy_dir(
        artifact.workspace, version_dir(artifact, version.number), live_dir(artifact)
    )
    return save_version(artifact, user=user, note=f"Restored version {version.number}")


def duplicate_artifact(artifact: Artifact, *, user: AppUser) -> Artifact:
    folder = get_free_folder_name(artifact.workspace, f"{artifact.folder}-copy")
    copy_dir(artifact.workspace, live_dir(artifact), f"{folder}/")
    copy = Artifact.objects.create(
        workspace=artifact.workspace,
        folder=folder,
        created_by=user,
        workspace_access=artifact.workspace_access,
    )
    save_version(copy, user=user, note=f"Copied from {get_artifact_title(artifact)}")
    return copy


def rename_artifact(artifact: Artifact, name: str) -> str | None:
    """Move the folder (and its versions) to a name made from `name`; the link changes too.
    Returns an error to show, or None."""
    folder = slugify(name)
    if not folder:
        return "Use letters or numbers in the name."
    if folder == artifact.folder:
        return None
    if not is_artifact_folder_name(folder):
        return f"“{folder}” is reserved, pick another name."
    if Artifact.objects.filter(workspace=artifact.workspace, folder=folder).exists():
        return f"There's already an artefact called “{folder}”."
    workspace = artifact.workspace
    old = artifact.folder
    move_dir(workspace, f"{old}/", f"{folder}/")
    move_dir(workspace, f"{VERSIONS_DIR}/{old}/", f"{VERSIONS_DIR}/{folder}/")
    artifact.folder = folder
    artifact.save(update_fields=["folder", "updated_at"])
    return None


def delete_artifact(artifact: Artifact) -> None:
    delete_dir(artifact.workspace, live_dir(artifact))
    delete_dir(artifact.workspace, f"{VERSIONS_DIR}/{artifact.folder}/")
    artifact.delete()


def render_artifact_share_dialog(request: Request, artifact: Artifact, *, dialog):
    with gui.alert_dialog(
        ref=dialog, modal_title=f"#### Share “{get_artifact_title(artifact)}”"
    ):
        # styled puts its class on each child element, so wrap the options in one div
        with (
            gui.styled(
                "& .gui-input-radio, & .gui-input-checkbox { display: flex; align-items: center; }"
            ),
            gui.div(),
        ):
            render_artifact_share_options(request, artifact)
        with gui.div(className="d-flex justify-content-between mt-4"):
            copy_to_clipboard_button(
                label=f"{icons.link} Copy Link",
                value=furl(settings.APP_BASE_URL).join(get_artifact_url(artifact)).url,
                type="secondary",
                className="py-2 px-3 m-0",
            )
            if gui.button("Done", type="primary", className="py-2 px-5 m-0"):
                dialog.set_open(False)
                gui.rerun()


def render_artifact_share_options(request: Request, artifact: Artifact):
    """Private / View only / Editable for members, plus Public; saves on change."""
    from bots.models.workflow import WorkflowAccessLevel

    workspace_name = artifact.workspace.display_name(request.user)
    workspace_access = artifact.workspace_access
    if not artifact.workspace.is_personal:
        options = {}
        # private needs a known creator, or nobody but Gooey staff could see it
        if artifact.created_by_id:
            if artifact.created_by_id == request.user.id:
                only = "you"
            else:
                only = artifact.created_by.full_name()
            options[str(WorkflowAccessLevel.VIEW_ONLY.value)] = (
                f"{icons.eye_slash} **Private**: Only {only} can view and edit.<br/>"
                '<span class="text-muted small">Hides it on Gooey.AI only: workspace '
                "functions can still read and change its files.</span>"
            )
        options[str(WorkflowAccessLevel.FIND_AND_VIEW.value)] = (
            f"{icons.eye} **View only**: Members of {workspace_name} can view."
        )
        options[str(WorkflowAccessLevel.EDIT.value)] = (
            f"{icons.company_solid} **Editable**: Members of {workspace_name} can change "
            "it with Ask Gooey."
        )
        with gui.div(className="mb-4"):
            gui.caption("WORKSPACE")
            workspace_access = int(
                gui.radio(
                    "",
                    options=options,
                    format_func=options.__getitem__,
                    key="artifact-workspace-access",
                    value=str(artifact.workspace_access),
                )
            )

    is_private = workspace_access == WorkflowAccessLevel.VIEW_ONLY
    if is_private:
        gui.session_state["artifact-is-public"] = False
    is_public = gui.checkbox(
        f"{icons.globe} **Public**: Anyone with the link can view, without signing in.",
        key="artifact-is-public",
        value=artifact.public_access == WorkflowAccessLevel.FIND_AND_VIEW,
        disabled=is_private,
    )
    public_access = (
        WorkflowAccessLevel.FIND_AND_VIEW
        if is_public
        else WorkflowAccessLevel.VIEW_ONLY
    )

    if (workspace_access, public_access) == (
        artifact.workspace_access,
        artifact.public_access,
    ):
        return
    artifact.workspace_access = workspace_access
    artifact.public_access = public_access
    artifact.save(update_fields=["workspace_access", "public_access", "updated_at"])


def get_artifact_title(artifact: Artifact) -> str:
    """The folder name, made friendly: "kisan-mitra_landing" -> "Kisan mitra landing"."""
    name = re.sub(r"[-_]+", " ", artifact.folder).strip()
    return name[:1].upper() + name[1:] or artifact.folder


def get_artifact_url(artifact: Artifact, **query) -> str:
    """`/<handle>/<folder>/`, or the Files tab for workspaces without a handle."""
    workspace = artifact.workspace
    if workspace.handle_id:
        path = f"/{workspace.handle.name}/{artifact.folder}/"
    else:
        path = f"/account/files/{artifact.folder}/{ARTIFACT_INDEX}"
    return furl(path).set(query).url


def get_artifact_chat_for_url(user: AppUser, url: str) -> ArtifactChat | None:
    """The user's Ask Gooey chat when `url` is an artifact page they can edit."""
    from handles.models import Handle

    parts = [part for part in furl(url).path.segments if part]
    if len(parts) != 2:
        return None
    try:
        handle = Handle.objects.get_by_name(parts[0])
    except Handle.DoesNotExist:
        return None
    if not handle.has_workspace:
        return None
    artifact = Artifact.objects.filter(
        workspace=handle.workspace, folder=parts[1]
    ).first()
    if not artifact or not artifact.can_user_edit(user):
        return None
    chat, _ = ArtifactChat.objects.get_or_create(artifact=artifact, user=user)
    return chat


def get_artifact_builder_context(chat: ArtifactChat) -> str:
    """Prepended to the first Ask Gooey message on an artifact. The production prompt doesn't
    read system variables for this yet, so the PoC says it in the message."""
    artifact = chat.artifact
    return (
        f"[Editing the page “{get_artifact_title(artifact)}”. Its files are in "
        f"`{live_dir(artifact)}` of the working directory: read `{ARTIFACT_INDEX}` there, "
        "edit only files in that folder, and keep the page one self-contained HTML file. "
        "Describe changes by what the page shows, not the code.]\n\n"
    )


def is_artifact_folder_name(folder: str) -> bool:
    return (
        bool(folder)
        and not folder.startswith(".")
        and folder not in (RESERVED_FOLDER_NAMES)
    )


def get_free_folder_name(workspace: Workspace, base: str) -> str:
    taken = set(
        Artifact.objects.filter(
            workspace=workspace, folder__startswith=base
        ).values_list("folder", flat=True)
    )
    folder, n = base, 2
    while folder in taken:
        folder, n = f"{base}-{n}", n + 1
    return folder


def live_dir(artifact: Artifact) -> str:
    return f"{artifact.folder}/"


def version_dir(artifact: Artifact, number: int) -> str:
    return f"{VERSIONS_DIR}/{artifact.folder}/{number}/"


def read_artifact_html(
    workspace: Workspace, directory: str, *, max_bytes: int = MAX_INLINE_HTML_BYTES
) -> tuple[str | None, str | None]:
    """(srcdoc, src) for the index.html in `directory`: embedded up to `max_bytes`, else a
    signed link. Both None when there's no index.html."""
    blob = get_artifact_blob(workspace, directory + ARTIFACT_INDEX)
    if not blob:
        return None, None
    if (blob.size or 0) <= max_bytes:
        return get_embeddable_html(blob.download_as_text()), None
    return None, get_signed_url(blob)


def get_embeddable_html(html: str) -> str:
    """
    Adds `<base href="about:srcdoc">` so `#...` links and `history.replaceState` work inside
    the frame; without it they resolve against the gooey.ai address and throw. Relative links
    to other files don't load. A page's own `<base>` is kept.
    """
    if re.search(r"<base\b", html, re.IGNORECASE):
        return html
    base = '<base href="about:srcdoc">'
    # after <head>, or after the doctype so the page stays out of quirks mode
    match = re.search(r"<head\b[^>]*>", html, re.IGNORECASE) or re.match(
        r"\s*<!doctype[^>]*>", html, re.IGNORECASE
    )
    if not match:
        return base + html
    return html[: match.end()] + base + html[match.end() :]


def get_download_url(artifact: Artifact) -> str | None:
    blob = get_artifact_blob(artifact.workspace, live_dir(artifact) + ARTIFACT_INDEX)
    if not blob:
        return None
    return get_signed_url(blob, download_name=f"{artifact.folder}.html")


def list_dir_files(workspace: Workspace, directory: str) -> list[storage.Blob]:
    prefix = gcs_v2.workspace_files_prefix(workspace.id) + directory
    # skip zero-byte "folder" placeholders created by the sandbox's bucket mount
    return [
        blob
        for blob in _bucket().list_blobs(prefix=prefix)
        if not blob.name.endswith("/")
    ]


def copy_dir(workspace: Workspace, source: str, destination: str) -> None:
    """Replace `destination` with a copy of `source`, both relative to the workspace files."""
    prefix = gcs_v2.workspace_files_prefix(workspace.id)
    delete_dir(workspace, destination)
    bucket = _bucket()
    for blob in list_dir_files(workspace, source):
        relative = blob.name.removeprefix(prefix + source)
        bucket.copy_blob(blob, bucket, prefix + destination + relative)


def move_dir(workspace: Workspace, source: str, destination: str) -> None:
    copy_dir(workspace, source, destination)
    delete_dir(workspace, source)


def delete_dir(workspace: Workspace, directory: str) -> None:
    prefix = gcs_v2.workspace_files_prefix(workspace.id) + directory
    for blob in _bucket().list_blobs(prefix=prefix):
        blob.delete()


def get_artifact_blob(workspace: Workspace, path: str) -> storage.Blob | None:
    if ".." in path.split("/"):
        return None
    blob_name = gcs_v2.workspace_files_prefix(workspace.id) + path
    return _bucket().get_blob(blob_name)


def get_signed_url(blob: storage.Blob, *, download_name: str | None = None) -> str:
    if download_name:
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=60),
            response_disposition=f"attachment; filename*=UTF-8''{quote(download_name)}",
        )
    return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60))


def _bucket():
    from firebase_admin import storage

    return storage.bucket(gcs_v2.GCS_BUCKET_NAME)
