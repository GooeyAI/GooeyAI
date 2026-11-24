"""Artifacts: websites made by functions, kept as folders of the workspace files.

A top-level folder that holds an `index.html` is an artifact. It works like an agent: every Ask
Gooey edit makes a draft with its own link, and only Update changes the live page, as a new
version. A run that writes the folder itself (making a new website, say) goes live at once.

Storage, all inside the workspace files:
    <folder>/                          the live version's files
    .drafts/<folder>/<draft_id>/       every draft, never changed once made
    .ask-gooey/<user id>/<artifact id>/  where Ask Gooey edits for one member
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
from daras_ai_v2.crypto import get_random_doc_id
from files.models import Artifact, ArtifactChat, ArtifactDraft, ArtifactVersion

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
DRAFTS_DIR = ".drafts"
WORKING_COPIES_DIR = ".ask-gooey"
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
) -> list[ArtifactDraft]:
    """
    After a Python or Bash run:
    - An Ask Gooey edit of someone's working copy becomes a new draft, and the page moves to
      it, as an agent's page moves to the run Ask Gooey made.
    - A run that wrote an artifact folder itself goes live as a new version; a new folder
      becomes a new artifact, and when Ask Gooey made it, its chat opens on the new page.
    """
    from bots.models import SavedRun

    prefix = gcs_v2.workspace_files_prefix(workspace.id)
    folders = set()
    working_copies = set()
    for blob in _bucket().list_blobs(prefix=prefix):
        relative = blob.name.removeprefix(prefix)
        if "/" not in relative or blob.updated < since:
            continue
        parts = relative.split("/")
        if parts[0] == WORKING_COPIES_DIR and len(parts) > 3:
            working_copies.add((parts[1], parts[2]))
        else:
            folders.add(parts[0])

    builder_sr = None
    if caller_sr and caller_sr.surface == SavedRun.Surface.builder_prompt:
        builder_sr = caller_sr

    made = []
    for user_id, artifact_id in sorted(working_copies):
        # only the member's own working copy
        if user_id != str(user.id) or not artifact_id.isdigit():
            continue
        chat = (
            ArtifactChat.objects.filter(
                artifact_id=int(artifact_id), artifact__workspace=workspace, user=user
            )
            .select_related("artifact", "working_draft")
            .first()
        )
        if not chat:
            continue
        artifact = chat.artifact
        directory = working_dir(artifact, user.id)
        if chat.working_draft and is_same_dir(
            workspace, directory, draft_dir(chat.working_draft)
        ):
            continue
        draft = save_draft(
            artifact,
            directory,
            user=user,
            based_on=chat.working_draft,
            builder_sr=builder_sr,
        )
        chat.working_draft = draft
        chat.save(update_fields=["working_draft", "updated_at"])
        made.append(draft)
        if builder_sr:
            builder_sr.redirect_url = get_artifact_url(artifact, draft=draft.draft_id)
            builder_sr.save(update_fields=["redirect_url"])

    for folder in sorted(folders):
        if not is_artifact_folder_name(folder):
            continue
        if not get_artifact_blob(workspace, f"{folder}/{ARTIFACT_INDEX}"):
            continue
        artifact, created = Artifact.objects.get_or_create(
            workspace=workspace, folder=folder, defaults=dict(created_by=user)
        )
        live = artifact.live_version
        if live and is_same_dir(workspace, live_dir(artifact), draft_dir(live.draft)):
            continue
        draft = save_draft(
            artifact,
            live_dir(artifact),
            user=user,
            based_on=live and live.draft,
            builder_sr=builder_sr,
        )
        publish_draft(artifact, draft, user=user)
        made.append(draft)
        if created and builder_sr:
            ArtifactChat.objects.update_or_create(
                artifact=artifact,
                user=user,
                defaults=dict(builder_saved_run=builder_sr),
            )
            # the standalone Ask Gooey page follows this to the new artifact
            builder_sr.redirect_url = get_artifact_url(artifact)
            builder_sr.save(update_fields=["redirect_url"])
    return made


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
            publish_live_folder(
                artifact, user=None, note="Found in the workspace files"
            )


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
        publish_live_folder(artifact, user=None, note="Found in the workspace files")
    return artifact


def prepare_working_copy(chat: ArtifactChat, draft: ArtifactDraft) -> None:
    """Before an Ask Gooey message: fill the member's working copy with the draft on their
    screen, so the edit builds on what they're looking at."""
    if chat.working_draft_id == draft.id:
        return
    artifact = chat.artifact
    copy_dir(artifact.workspace, draft_dir(draft), working_dir(artifact, chat.user_id))
    chat.working_draft = draft
    chat.save(update_fields=["working_draft", "updated_at"])


def publish_live_folder(
    artifact: Artifact, *, user: AppUser | None, note: str = ""
) -> ArtifactVersion:
    """Save `<folder>/` as it is now as a draft, and make it the live version."""
    draft = save_draft(artifact, live_dir(artifact), user=user)
    return publish_draft(artifact, draft, user=user, note=note)


def save_draft(
    artifact: Artifact,
    source: str,
    *,
    user: AppUser | None,
    based_on: ArtifactDraft | None = None,
    builder_sr: SavedRun | None = None,
) -> ArtifactDraft:
    """Snapshot the files in `source` as a new draft."""
    draft = ArtifactDraft(
        artifact=artifact,
        draft_id=get_random_doc_id(),
        created_by=user,
        based_on=based_on,
        builder_saved_run=builder_sr,
    )
    copy_dir(artifact.workspace, source, draft_dir(draft))
    draft.save()
    return draft


def publish_draft(
    artifact: Artifact, draft: ArtifactDraft, *, user: AppUser | None, note: str = ""
) -> ArtifactVersion:
    """Update: make the draft the live page, as the next version."""
    with transaction.atomic():
        artifact = Artifact.objects.select_for_update().get(id=artifact.id)
        number = (artifact.versions.aggregate(n=Max("number"))["n"] or 0) + 1
        if not is_same_dir(artifact.workspace, draft_dir(draft), live_dir(artifact)):
            copy_dir(artifact.workspace, draft_dir(draft), live_dir(artifact))
        version = ArtifactVersion.objects.create(
            artifact=artifact, number=number, draft=draft, created_by=user, note=note
        )
        artifact.live_version = version
        artifact.save(update_fields=["live_version", "updated_at"])
    return version


def duplicate_artifact(
    artifact: Artifact, *, user: AppUser, draft: ArtifactDraft, name: str = ""
) -> Artifact:
    """Save as new: a new artifact made by `user` from the draft on screen."""
    base = slugify(name) or f"{artifact.folder}-copy"
    if not is_artifact_folder_name(base):
        base = f"{base}-copy"
    folder = get_free_folder_name(artifact.workspace, base)
    copy_dir(artifact.workspace, draft_dir(draft), f"{folder}/")
    copy = Artifact.objects.create(
        workspace=artifact.workspace,
        folder=folder,
        created_by=user,
        workspace_access=artifact.workspace_access,
    )
    publish_live_folder(
        copy, user=user, note=f"Copied from {get_artifact_title(artifact)}"
    )
    return copy


def rename_artifact(artifact: Artifact, name: str) -> str | None:
    """Move the folder (and its drafts) to a name made from `name`; the link changes too.
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
    move_dir(workspace, f"{DRAFTS_DIR}/{old}/", f"{DRAFTS_DIR}/{folder}/")
    artifact.folder = folder
    artifact.save(update_fields=["folder", "updated_at"])
    return None


def delete_artifact(artifact: Artifact) -> None:
    workspace = artifact.workspace
    delete_dir(workspace, live_dir(artifact))
    delete_dir(workspace, f"{DRAFTS_DIR}/{artifact.folder}/")
    for user_id in artifact.chats.values_list("user_id", flat=True):
        delete_dir(workspace, working_dir(artifact, user_id))
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


def get_artifact_chat_for_url(
    user: AppUser, url: str
) -> tuple[ArtifactChat, ArtifactDraft] | tuple[None, None]:
    """The user's Ask Gooey chat and the draft on screen, when `url` is an artifact page
    they can ask for changes on: members who can view it, as anyone can run an agent."""
    from handles.models import Handle

    parts = [part for part in furl(url).path.segments if part]
    if len(parts) != 2:
        return None, None
    try:
        handle = Handle.objects.get_by_name(parts[0])
    except Handle.DoesNotExist:
        return None, None
    if not handle.has_workspace:
        return None, None
    artifact = Artifact.objects.filter(
        workspace=handle.workspace, folder=parts[1]
    ).first()
    if not artifact or not can_user_ask_gooey(artifact, user):
        return None, None
    draft = get_shown_draft(artifact, furl(url).args.get("draft"))
    if not draft:
        return None, None
    chat, _ = ArtifactChat.objects.get_or_create(artifact=artifact, user=user)
    return chat, draft


def can_user_ask_gooey(artifact: Artifact, user: AppUser | None) -> bool:
    return artifact.is_member(user) and artifact.can_user_view(user)


def get_shown_draft(artifact: Artifact, draft_id: str | None) -> ArtifactDraft | None:
    """The draft a `?draft=` link names, or the live version's."""
    if draft_id:
        return artifact.drafts.filter(draft_id=draft_id).first()
    return artifact.live_version and artifact.live_version.draft


def get_artifact_builder_context(chat: ArtifactChat) -> str:
    """Prepended to the first Ask Gooey message on an artifact. Agents pass the page as a
    hidden variable (`workflow_url`); the PoC says it in the message instead."""
    artifact = chat.artifact
    return (
        f"[Editing the page “{get_artifact_title(artifact)}”. Its files are in "
        f"`{working_dir(artifact, chat.user_id)}` of the working directory: read "
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


def draft_dir(draft: ArtifactDraft) -> str:
    return f"{DRAFTS_DIR}/{draft.artifact.folder}/{draft.draft_id}/"


def working_dir(artifact: Artifact, user_id: int) -> str:
    # by id, so a rename leaves it, and the path Ask Gooey was told, in place
    return f"{WORKING_COPIES_DIR}/{user_id}/{artifact.id}/"


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


def get_download_url(artifact: Artifact, directory: str) -> str | None:
    blob = get_artifact_blob(artifact.workspace, directory + ARTIFACT_INDEX)
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


def is_same_dir(workspace: Workspace, a: str, b: str) -> bool:
    """Whether two folders hold the same files, by name and checksum."""
    return get_dir_fingerprint(workspace, a) == get_dir_fingerprint(workspace, b)


def get_dir_fingerprint(workspace: Workspace, directory: str) -> set[tuple[str, str]]:
    prefix = gcs_v2.workspace_files_prefix(workspace.id) + directory
    return {
        (blob.name.removeprefix(prefix), blob.md5_hash)
        for blob in list_dir_files(workspace, directory)
    }


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
