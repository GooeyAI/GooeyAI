"""Artifacts: websites made by functions, kept as folders of the workspace files.

A top-level folder that holds an `index.html` is an artifact. The page shows a published
snapshot, editors work in their own drafts, and Update saves a new snapshot - live for
people who can manage the artifact, proposed for everyone else.
"""

from __future__ import annotations

import re
import typing
from datetime import timedelta
from urllib.parse import quote

from django.db import transaction
from django.db.models import Max
from furl import furl

import gooey_gui as gui
from daras_ai_v2 import gcs_v2, icons, settings
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from files.models import Artifact, ArtifactDraft, ArtifactVersion

if typing.TYPE_CHECKING:
    from fastapi import Request
    from firebase_admin import storage

    from app_users.models import AppUser
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
DRAFTS_DIR = ".drafts"
VERSIONS_DIR = ".versions"
# HTML up to this size is embedded in the page (srcdoc), so it never expires
MAX_INLINE_HTML_BYTES = 1_000_000
ARTIFACT_SANDBOX = (
    "allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
)
ARTIFACTS_PATH = "/artifacts/"


def sync_workspace_artifacts(
    workspace: Workspace, *, user: AppUser | None = None
) -> None:
    """Add a row for every top-level folder with an index.html that doesn't have one yet."""
    prefix = gcs_v2.workspace_files_prefix(workspace.id)
    blobs = _bucket().list_blobs(
        prefix=prefix, match_glob=f"{prefix}*/{ARTIFACT_INDEX}"
    )
    folders = {blob.name.removeprefix(prefix).split("/")[0] for blob in blobs}
    folders = {folder for folder in folders if is_artifact_folder_name(folder)}
    existing = set(
        Artifact.objects.filter(workspace=workspace).values_list("folder", flat=True)
    )
    Artifact.objects.bulk_create(
        [
            Artifact(workspace=workspace, folder=folder, created_by=user)
            for folder in sorted(folders - existing)
        ],
        ignore_conflicts=True,
    )


def get_artifact(workspace: Workspace, folder: str) -> Artifact | None:
    if not is_artifact_folder_name(folder):
        return None
    artifact = Artifact.objects.filter(workspace=workspace, folder=folder).first()
    if artifact:
        return artifact
    if not get_artifact_blob(workspace, f"{folder}/{ARTIFACT_INDEX}"):
        return None
    artifact, _ = Artifact.objects.get_or_create(workspace=workspace, folder=folder)
    return artifact


def start_draft(artifact: Artifact, user: AppUser) -> ArtifactDraft:
    """The user's draft, copied from the live version (or the working copy) on first use."""
    draft = ArtifactDraft.objects.filter(artifact=artifact, user=user).first()
    if draft:
        return draft
    live = artifact.live_version
    source = version_dir(artifact, live.number) if live else live_dir(artifact)
    copy_dir(artifact.workspace, source, draft_dir(artifact, user.id))
    return ArtifactDraft.objects.create(
        artifact=artifact, user=user, base_number=live and live.number
    )


def publish_draft(draft: ArtifactDraft, user: AppUser) -> ArtifactVersion:
    """Save the draft as the next version: live for managers, proposed for other editors."""
    with transaction.atomic():
        artifact = Artifact.objects.select_for_update().get(id=draft.artifact_id)
        number = (artifact.versions.aggregate(n=Max("number"))["n"] or 0) + 1
        copy_dir(
            artifact.workspace,
            draft_dir(artifact, user.id),
            version_dir(artifact, number),
        )
        if artifact.can_user_manage(user):
            status = ArtifactVersion.Status.PUBLISHED
        else:
            status = ArtifactVersion.Status.PROPOSED
        version = ArtifactVersion.objects.create(
            artifact=artifact,
            number=number,
            status=status,
            created_by=user,
            base_number=draft.base_number,
        )
        if status == ArtifactVersion.Status.PUBLISHED:
            make_live(artifact, version)
    discard_draft(draft)
    return version


def make_live(artifact: Artifact, version: ArtifactVersion) -> None:
    """Show this version on the artifact's link; `<folder>/` is refreshed to match it."""
    version.status = ArtifactVersion.Status.PUBLISHED
    version.save(update_fields=["status"])
    artifact.live_version = version
    artifact.save(update_fields=["live_version", "updated_at"])
    copy_dir(
        artifact.workspace, version_dir(artifact, version.number), live_dir(artifact)
    )


def discard_draft(draft: ArtifactDraft) -> None:
    delete_dir(draft.artifact.workspace, draft_dir(draft.artifact, draft.user_id))
    draft.delete()


def live_changed_since(draft: ArtifactDraft) -> ArtifactVersion | None:
    """The live version, if it isn't the one the draft started from."""
    live = draft.artifact.live_version
    if live and live.number != draft.base_number:
        return live
    return None


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
            f"{icons.company_solid} **Editable**: Members of {workspace_name} can edit "
            "with Ask Gooey and propose versions."
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
        f"{icons.globe} **Public**: Anyone with the link can view the live version, "
        "without signing in.",
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
    """The folder name, made friendly: "product-shots_gallery" -> "Product shots gallery"."""
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


def get_artifact_draft_for_url(user: AppUser, url: str) -> ArtifactDraft | None:
    """The user's draft when `url` is an artifact page in draft mode, for Ask Gooey."""
    from handles.models import Handle

    f = furl(url)
    if "draft" not in f.args:
        return None
    parts = [part for part in f.path.segments if part]
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
    return start_draft(artifact, user)


def get_artifact_builder_context(draft: ArtifactDraft) -> str:
    """Prepended to the first Ask Gooey message on a draft. The production prompt doesn't
    read system variables for this yet, so the PoC says it in the message."""
    artifact = draft.artifact
    return (
        f"[Editing the page “{get_artifact_title(artifact)}”. Its files are in "
        f"`{draft_dir(artifact, draft.user_id)}` of the working directory: read "
        f"`{ARTIFACT_INDEX}` there, edit only files in that folder, and keep the page one "
        "self-contained HTML file. Describe changes by what the page shows, not the code.]"
        "\n\n"
    )


def is_artifact_folder_name(folder: str) -> bool:
    return (
        bool(folder)
        and not folder.startswith(".")
        and folder not in (RESERVED_FOLDER_NAMES)
    )


def live_dir(artifact: Artifact) -> str:
    return f"{artifact.folder}/"


def draft_dir(artifact: Artifact, user_id: int) -> str:
    return f"{DRAFTS_DIR}/{user_id}/{artifact.folder}/"


def version_dir(artifact: Artifact, number: int) -> str:
    return f"{VERSIONS_DIR}/{artifact.folder}/{number}/"


def read_artifact_html(
    workspace: Workspace, directory: str
) -> tuple[str | None, str | None]:
    """(srcdoc, src) for the index.html in `directory`: embedded up to 1 MB, else a signed
    link. Both None when there's no index.html."""
    blob = get_artifact_blob(workspace, directory + ARTIFACT_INDEX)
    if not blob:
        return None, None
    if (blob.size or 0) <= MAX_INLINE_HTML_BYTES:
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
