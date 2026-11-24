import os

import pydantic
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.template.defaultfilters import filesizeformat
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

import gooey_gui as gui
from bots.models import Workflow
from daras_ai_v2 import gcs_v2, icons
from daras_ai_v2.gooey_builder import (
    GOOEY_BUILDER_EVENT_KEY,
    GOOEY_BUILDER_STORAGE_KEY,
    can_launch_gooey_builder,
    get_gooey_builder_photo_url,
    render_gooey_builder_embed,
)
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.web_widget_embed import get_chat_widget_messages
from files.models import Artifact, ArtifactDraft, ArtifactVersion
from gooey_gui.types.artifact_props import (
    ArtifactCard,
    ArtifactFrameProps,
    ArtifactGridProps,
)
from gooey_gui.types.recipe_top_bar_props import (
    CopyShare,
    LinkTarget,
    ManageShare,
    MenuIntent,
    PublishIntent,
    RecipeSubmitIntent,
    RecipeTopBarProps,
    ShareIntent,
    SubmitTarget,
    TopBarAuthor,
    TopBarMenuItem,
)
from gooey_gui.types.recipe_workspace_props import (
    PageShellConfig,
    RecipeSurfaceProps,
    RecipeWorkspaceProps,
    SingleLayout,
    SurfaceId,
    WorkspaceView,
)
from gooey_gui.types.workspace_files_props import (
    WorkspaceFileBrowserProps,
    WorkspaceFileEntry,
)
from handles.models import Handle
from routers.base_auth import get_login_url
from routers.custom_api_router import CustomAPIRouter
from routers.root import get_og_url_path, sidebar_page_wrapper
from widgets.sidebar import sidebar_layout
from workspaces.artifacts import (
    ARTIFACT_INDEX,
    ARTIFACT_SANDBOX,
    ARTIFACTS_PATH,
    discard_draft,
    draft_dir,
    get_artifact,
    get_artifact_blob,
    get_artifact_title,
    get_artifact_url,
    get_signed_url,
    list_dir_files,
    live_changed_since,
    live_dir,
    make_live,
    publish_draft,
    read_artifact_html,
    render_artifact_share_dialog,
    start_draft,
    sync_workspace_artifacts,
    version_dir,
)
from workspaces.models import Workspace
from workspaces.widgets import set_current_workspace

app = CustomAPIRouter()

SUBMIT_INTENT_KEY = "--artifact-submit-intent"
MENU_VERSIONS = "versions"
MENU_DISCARD = "discard-draft"

# PoC: Desktop / Mobile / Files ride on the workspace's existing surfaces, so the agent
# page's layout works unchanged. Hardening would give them surfaces of their own.
DESKTOP_SURFACE = SurfaceId.preview
MOBILE_SURFACE = SurfaceId.about
FILES_SURFACE = SurfaceId.editor


@gui.route(app, ARTIFACTS_PATH)
def artifacts_route(request: Request):
    if not request.user or request.user.is_anonymous:
        raise gui.RedirectException(get_login_url(request))
    with sidebar_page_wrapper(request) as workspace:
        render_artifacts_grid(request, workspace)
    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url, title="Artifacts • Gooey.AI", robots="noindex,nofollow"
        )
    )


def render_artifacts_grid(request: Request, workspace: Workspace):
    sync_workspace_artifacts(workspace)
    artifacts = (
        Artifact.objects.filter(workspace=workspace)
        .select_related("created_by", "live_version", "workspace__handle")
        .order_by("-updated_at")
    )
    user = request.user
    drafts = set(
        ArtifactDraft.objects.filter(
            artifact__workspace=workspace, user=user
        ).values_list("artifact_id", flat=True)
    )
    cards = []
    for artifact in artifacts:
        if not artifact.can_user_view(user):
            continue
        live = artifact.live_version
        notes = []
        if artifact.id in drafts:
            notes.append("You have a draft")
        if artifact.can_user_manage(user):
            proposed = get_proposed_versions(artifact).count()
            if proposed:
                notes.append(f"{proposed} proposed version{'s' * (proposed > 1)}")
        cards.append(
            ArtifactCard(
                title=get_artifact_title(artifact),
                href=get_artifact_url(artifact),
                author=get_artifact_author(artifact),
                status=f"Live · v{live.number}" if live else "Not published",
                status_tone="live" if live else "draft",
                updated_at_label=str(naturaltime(artifact.updated_at)),
                note=" · ".join(notes) or None,
            )
        )
    gui.model_component(
        ArtifactGridProps(
            workspace_name=workspace.display_name(user),
            cards=cards,
            empty_message=(
                "No artifacts yet. Ask Gooey to make a website: it's saved as a folder "
                "with an index.html and shows up here."
            ),
        )
    )


def render_artifact_route(request: Request, handle_name: str, path: str):
    """`/<handle>/<folder>/`, or None to fall through to the static pages."""
    try:
        handle = Handle.objects.get_by_name(handle_name)
    except Handle.DoesNotExist:
        return None
    if not handle.has_workspace:
        return None
    parts = [part for part in path.split("/") if part]
    artifact = parts and get_artifact(handle.workspace, parts[0])
    if not artifact:
        return None

    user = request.user
    if not artifact.can_user_view(user):
        if not user or user.is_anonymous:
            raise gui.RedirectException(get_login_url(request))
        with sidebar_page_wrapper(request):
            render_artifact_no_access(request, artifact)
        return dict(meta=build_artifact_meta_tags(request, artifact, None))

    # other files of the folder: from the live version
    if parts[1:] and parts[1:] != [ARTIFACT_INDEX]:
        blob = get_artifact_blob(
            artifact.workspace, get_shown_dir(artifact) + "/".join(parts[1:])
        )
        if not blob:
            return None
        return RedirectResponse(get_signed_url(blob))

    builder_href = None
    if artifact.can_user_edit(user) and can_launch_gooey_builder(
        request, artifact.workspace
    ):
        # the draft holds the panel; elsewhere the button opens the draft
        is_draft = "draft" in request.query_params
        builder_href = "" if is_draft else get_artifact_url(artifact, draft=1)
    with sidebar_page_wrapper(
        request, fill_viewport=True, hosts_builder=True, builder_href=builder_href
    ):
        render_artifact_page(request, artifact)
    return dict(
        meta=build_artifact_meta_tags(request, artifact, get_artifact_title(artifact))
    )


def render_artifact_page(request: Request, artifact: Artifact):
    user = request.user
    can_edit = artifact.can_user_edit(user)
    draft = None
    if can_edit:
        draft = ArtifactDraft.objects.filter(artifact=artifact, user=user).first()

    params = request.query_params
    version = None
    if "draft" in params and can_edit:
        mode = "draft"
        draft = draft or start_draft(artifact, user)
        # Ask Gooey runs in the selected workspace, so its edits land in the right files
        set_current_workspace(request.session, artifact.workspace_id)
        directory = draft_dir(artifact, user.id)
    elif params.get("v") and can_edit:
        mode = "version"
        version = artifact.versions.filter(number=_to_int(params["v"])).first()
        if not version:
            raise HTTPException(status_code=404)
        directory = version_dir(artifact, version.number)
    else:
        mode = "live"
        directory = get_shown_dir(artifact)

    hosts_builder = mode == "draft" and can_launch_gooey_builder(
        request, artifact.workspace
    )
    config = build_artifact_shell_config(artifact)

    # the bar comes first in the DOM, but is filled last, once the actions have run
    top_bar_placeholder = gui.div(
        className="v2-topbar-container flex-shrink-0 w-100 px-2 px-lg-4 py-2"
    )
    with gui.div(
        className="v2-app-shell d-flex flex-column flex-grow-1 w-100",
        style=dict(minHeight=0),
    ):
        if hosts_builder:
            # open beside the draft on arrival
            gui.session_state.setdefault(GOOEY_BUILDER_EVENT_KEY, True)
            builder_pane, body_pane = sidebar_layout(
                key=GOOEY_BUILDER_EVENT_KEY,
                session=request.session,
                client_only=True,
                storage_key=GOOEY_BUILDER_STORAGE_KEY,
            )
        else:
            builder_pane, body_pane = None, gui.dummy()

    with (
        body_pane,
        gui.div(
            className="artifact-page v2-workspace-body d-flex flex-column h-100 w-100 pt-2 pt-lg-0 pb-lg-2 overflow-auto px-0",
            style=dict(minHeight=0),
        ),
    ):
        # the workspace's pane controls open an editor beside the page; artifacts have none
        gui.html(
            "<style>.artifact-page .recipe-workspace-controls { display: none !important; }</style>"
        )
        render_artifact_workspace(
            request,
            artifact,
            config=config,
            mode=mode,
            draft=draft,
            version=version,
            directory=directory,
        )

    if builder_pane is not None:
        with builder_pane:
            render_artifact_builder(draft)

    with top_bar_placeholder:
        render_artifact_top_bar(
            request,
            artifact,
            config=config,
            mode=mode,
            draft=draft,
            hosts_builder=hosts_builder,
        )

    handle_artifact_actions(request, artifact, draft=draft)


def render_artifact_workspace(
    request: Request,
    artifact: Artifact,
    *,
    config: PageShellConfig,
    mode: str,
    draft: ArtifactDraft | None,
    version: ArtifactVersion | None,
    directory: str,
):
    title = get_artifact_title(artifact)
    srcdoc, src = read_artifact_html(artifact.workspace, directory)
    with gui.model_component(RecipeWorkspaceProps(config=config)):
        for surface, device in (
            (DESKTOP_SURFACE, "desktop"),
            (MOBILE_SURFACE, "mobile"),
        ):
            # the surface renders its one slot's children, so the frame sits in a div
            with (
                gui.model_component(RecipeSurfaceProps(surface=surface)),
                gui.div(),
                gui.model_component(
                    ArtifactFrameProps(
                        title=title,
                        srcdoc=srcdoc,
                        src=src,
                        sandbox=ARTIFACT_SANDBOX,
                        device=device,
                    )
                ),
            ):
                render_artifact_banner(
                    request,
                    artifact,
                    mode=mode,
                    draft=draft,
                    version=version,
                    key=device,
                )
        with (
            gui.model_component(RecipeSurfaceProps(surface=FILES_SURFACE)),
            gui.div(className="px-2 px-lg-0"),
        ):
            render_artifact_files(artifact, mode=mode, directory=directory)


def render_artifact_banner(
    request: Request,
    artifact: Artifact,
    *,
    mode: str,
    draft: ArtifactDraft | None,
    version: ArtifactVersion | None,
    key: str,
):
    """One line on what this is and who else sees it, with the action that fits."""
    user = request.user
    live = artifact.live_version
    can_manage = artifact.can_user_manage(user)
    with gui.div(
        className="d-flex flex-wrap align-items-center gap-2 small border rounded px-3 py-2 bg-body-tertiary"
    ):
        match mode:
            case "draft":
                text = f"{icons.edit} **Your draft**"
                if draft.base_number:
                    text += f", started from version {draft.base_number}"
                text += ". "
                text += (
                    f"Viewers see version {live.number}."
                    if live
                    else "Nothing is published yet."
                )
                changed = live_changed_since(draft)
                if changed and draft.base_number:
                    text += f" Version {changed.number} went live after you started."
                if not can_manage:
                    text += " Update sends your version to the owner to make live."
                gui.write(text, unsafe_allow_html=True, className="mb-0")
            case "version":
                status = get_version_status(artifact, version)
                gui.write(
                    f"{icons.time} **Version {version.number}** · {status} · by "
                    f"{get_user_name(version.created_by)} · {naturaltime(version.created_at)}",
                    unsafe_allow_html=True,
                    className="mb-0",
                )
                if can_manage and version.id != artifact.live_version_id:
                    if gui.button(
                        "Make live",
                        type="primary",
                        className="btn-sm mb-0 ms-auto",
                        key=f"make-live-banner-{key}",
                    ):
                        make_live(artifact, version)
                        raise gui.RedirectException(get_artifact_url(artifact))
            case _ if not live:
                gui.write(
                    f"{icons.eye_slash} **Not published yet.** Only people who can edit "
                    "it see this. Edit it with Ask Gooey, then Update to publish.",
                    unsafe_allow_html=True,
                    className="mb-0",
                )
            case _:
                text = f"{icons.globe} **Live** · version {live.number}"
                proposed = can_manage and get_proposed_versions(artifact).first()
                if proposed:
                    url = get_artifact_url(artifact, v=proposed.number)
                    text += (
                        f" · [Version {proposed.number} proposed by "
                        f"{get_user_name(proposed.created_by)}]({url})"
                    )
                if draft:
                    text += (
                        f" · [You have a draft]({get_artifact_url(artifact, draft=1)})"
                    )
                gui.write(text, unsafe_allow_html=True, className="mb-0")


def render_artifact_files(artifact: Artifact, *, mode: str, directory: str):
    prefix_len = len(directory)
    blobs = list_dir_files(artifact.workspace, directory)
    root = gcs_v2.workspace_files_prefix(artifact.workspace_id)
    label = {"draft": "your draft", "version": "this version"}.get(
        mode, "the live page"
    )
    gui.model_component(
        WorkspaceFileBrowserProps(
            description=(
                f"The files behind {label}. Download one to look at it; changes go "
                "through Ask Gooey."
            ),
            entries=[
                WorkspaceFileEntry(
                    path=blob.name.removeprefix(root)[prefix_len:],
                    href=get_signed_url(
                        blob, download_name=os.path.basename(blob.name)
                    ),
                    size_label=filesizeformat(blob.size or 0),
                    updated_at_label=str(naturaltime(blob.updated)),
                )
                for blob in blobs
            ],
        )
    )


def render_artifact_builder(draft: ArtifactDraft):
    # the widget's "new conversation" sets this; the next message starts a fresh chat
    if gui.session_state.pop("builderOnNewConversation", None):
        draft.builder_saved_run = None
        draft.save(update_fields=["builder_saved_run", "updated_at"])
    builder_sr = draft.builder_saved_run
    if builder_sr:
        builder_run_url = builder_sr.get_app_url()
        messages = get_chat_widget_messages(
            builder_sr.to_dict(), web_url=builder_run_url
        )
        if builder_sr.run_status:
            # re-render while Ask Gooey works, so the frame picks up its edits
            page_cls = Workflow(builder_sr.workflow).page_cls
            gui.realtime_pull(
                [page_cls.realtime_channel_name(builder_sr.run_id, builder_sr.uid)]
            )
    else:
        builder_run_url = None
        messages = []
    render_gooey_builder_embed(
        event_key=GOOEY_BUILDER_EVENT_KEY,
        builder_run_url=builder_run_url,
        messages=messages,
        workflow_state={},
        prompts=[
            "Make it work better on phones",
            "Add a short intro at the top",
            "Change the colours to match our brand",
        ],
    )


def render_artifact_top_bar(
    request: Request,
    artifact: Artifact,
    *,
    config: PageShellConfig,
    mode: str,
    draft: ArtifactDraft | None,
    hosts_builder: bool,
):
    user = request.user
    can_edit = artifact.can_user_edit(user)
    can_manage = artifact.can_user_manage(user)

    publish_label = None
    if draft:
        publish_label = "Update" if can_manage else "Propose update"
    if can_manage:
        share = ManageShare(icon_html=icons.share)
    else:
        share = CopyShare(url=get_artifact_url(artifact), icon_html=icons.share)

    gui.model_component(
        RecipeTopBarProps(
            config=config,
            title=get_artifact_title(artifact),
            title_href=get_artifact_url(artifact),
            author=TopBarAuthor(label=f"by {get_artifact_author(artifact)}"),
            title_menu_items=get_artifact_menu_items(
                artifact, mode=mode, draft=draft, can_edit=can_edit
            ),
            submit_intent_key=SUBMIT_INTENT_KEY,
            publish_label=publish_label,
            publish_intent=PublishIntent() if publish_label else None,
            has_unpublished_changes=bool(draft),
            share=share,
            view_only=not can_edit,
            builder_panel_key=GOOEY_BUILDER_EVENT_KEY if hosts_builder else None,
            builder_storage_key=GOOEY_BUILDER_STORAGE_KEY if hosts_builder else None,
            builder_new_event=(
                f"{GOOEY_BUILDER_EVENT_KEY}:new"
                if hosts_builder and draft.builder_saved_run_id
                else None
            ),
            builder_photo_url=get_gooey_builder_photo_url() if hosts_builder else None,
        )
    )


def get_artifact_menu_items(
    artifact: Artifact, *, mode: str, draft: ArtifactDraft | None, can_edit: bool
) -> list[TopBarMenuItem]:
    items = []
    if can_edit and mode != "draft":
        items.append(
            TopBarMenuItem(
                key="edit",
                label="Edit draft" if draft else "Edit with Ask Gooey",
                icon_html=icons.edit,
                target=LinkTarget(href=get_artifact_url(artifact, draft=1)),
            )
        )
    if mode != "live":
        items.append(
            TopBarMenuItem(
                key="live",
                label="View live" if artifact.live_version_id else "View working copy",
                icon_html=icons.globe,
                target=LinkTarget(href=get_artifact_url(artifact)),
            )
        )
    if can_edit:
        items.append(
            TopBarMenuItem(
                key=MENU_VERSIONS,
                label="Version history",
                icon_html=icons.time,
                target=SubmitTarget(intent=MenuIntent(item_key=MENU_VERSIONS)),
            )
        )
    if draft:
        items.append(
            TopBarMenuItem(
                key=MENU_DISCARD,
                label="Discard draft",
                icon_html=icons.delete,
                target=SubmitTarget(intent=MenuIntent(item_key=MENU_DISCARD)),
                is_danger=True,
            )
        )
    return items


def handle_artifact_actions(
    request: Request, artifact: Artifact, *, draft: ArtifactDraft | None
):
    intent = pop_submit_intent()

    publish_ref = gui.use_confirm_dialog(key="artifact-publish-confirm")
    if isinstance(intent, PublishIntent) and draft:
        if live_changed_since(draft) and draft.base_number:
            publish_ref.set_open(True)
        else:
            publish_and_redirect(request, draft)
    if publish_ref.is_open and draft:
        live = artifact.live_version
        with gui.confirm_dialog(
            ref=publish_ref,
            modal_title="#### The live page changed",
            confirm_label="Publish anyway",
        ):
            gui.write(
                f"Version {live.number} went live after you started your draft from "
                f"version {draft.base_number}. Publishing your draft replaces those "
                "changes. To keep them, discard your draft and start again from the live "
                "page."
            )
    if publish_ref.pressed_confirm and draft:
        publish_and_redirect(request, draft)

    share_ref = gui.use_alert_dialog(key="artifact-share")
    if isinstance(intent, ShareIntent):
        share_ref.set_open(True)
    if share_ref.is_open:
        render_artifact_share_dialog(request, artifact, dialog=share_ref)

    picked = intent.item_key if isinstance(intent, MenuIntent) else None

    history_ref = gui.use_alert_dialog(key="artifact-versions")
    if picked == MENU_VERSIONS:
        history_ref.set_open(True)
    if history_ref.is_open:
        with gui.alert_dialog(
            ref=history_ref,
            modal_title=f"#### {icons.time} Versions",
            large=True,
            unsafe_allow_html=True,
        ):
            render_artifact_versions(request, artifact)

    discard_ref = gui.use_confirm_dialog(key="artifact-discard-confirm")
    if picked == MENU_DISCARD:
        discard_ref.set_open(True)
    if discard_ref.is_open:
        with gui.confirm_dialog(
            ref=discard_ref,
            modal_title="#### Discard your draft?",
            confirm_label="Discard",
            confirm_className="border-danger bg-danger text-white",
        ):
            gui.write("Your unpublished changes will be lost.")
    if discard_ref.pressed_confirm and draft:
        discard_draft(draft)
        raise gui.RedirectException(get_artifact_url(artifact))


def publish_and_redirect(request: Request, draft: ArtifactDraft):
    version = publish_draft(draft, request.user)
    artifact = draft.artifact
    if version.status == ArtifactVersion.Status.PUBLISHED:
        raise gui.RedirectException(get_artifact_url(artifact))
    raise gui.RedirectException(get_artifact_url(artifact, v=version.number))


def render_artifact_versions(request: Request, artifact: Artifact):
    versions = artifact.versions.select_related("created_by")
    if not versions:
        gui.write("No versions yet. Update publishes the first one.")
        return
    can_manage = artifact.can_user_manage(request.user)
    for version in versions:
        with gui.div(
            className="d-flex flex-wrap align-items-center gap-2 border-bottom py-2"
        ):
            gui.write(
                f"**[Version {version.number}]({get_artifact_url(artifact, v=version.number)})**"
                f" · {get_version_status(artifact, version)} · by "
                f"{get_user_name(version.created_by)} · {naturaltime(version.created_at)}",
                className="mb-0 flex-grow-1",
            )
            if can_manage and version.id != artifact.live_version_id:
                if gui.button(
                    "Make live",
                    className="btn-sm mb-0",
                    key=f"make-live-{version.id}",
                ):
                    make_live(artifact, version)
                    raise gui.RedirectException(get_artifact_url(artifact))


def render_artifact_no_access(request: Request, artifact: Artifact):
    if artifact.is_member(request.user):
        gui.write(
            "#### This page is private\n\nOnly the person who made it can see it."
            if artifact.live_version_id
            else "#### Not published yet\n\nOnly people who can edit it can see it."
        )
    else:
        gui.write(
            "#### You need access\n\n"
            f"This page belongs to a workspace you're not a member of. Ask someone in "
            f"{artifact.workspace.display_name()} to invite you."
        )


def build_artifact_shell_config(artifact: Artifact) -> PageShellConfig:
    desktop = SingleLayout(surface=DESKTOP_SURFACE)
    return PageShellConfig(
        storage_key=f"gooey:artifact-layout:{artifact.id}",
        initial_layout=desktop,
        run_layout=desktop,
        views=[
            WorkspaceView(
                key="desktop",
                label="Desktop",
                icon_html='<i class="fa-regular fa-desktop"></i>',
                layout=desktop,
            ),
            WorkspaceView(
                key="mobile",
                label="Mobile",
                icon_html='<i class="fa-regular fa-mobile"></i>',
                layout=SingleLayout(surface=MOBILE_SURFACE),
            ),
            WorkspaceView(
                key="files",
                label="Files",
                icon_html='<i class="fa-regular fa-folder-open"></i>',
                layout=SingleLayout(surface=FILES_SURFACE),
            ),
        ],
        narrow_surface=DESKTOP_SURFACE,
        workspace_href=get_artifact_url(artifact),
        workspace_active=True,
    )


def build_artifact_meta_tags(
    request: Request, artifact: Artifact, title: str | None
) -> list:
    # pages people can't see don't name the artifact
    url = get_og_url_path(request)
    workspace_name = artifact.workspace.display_name()
    return raw_build_meta_tags(
        url=url,
        canonical_url=url,
        title=f"{title or 'You need access'} • {workspace_name} • Gooey.AI",
        description=f"Made in {workspace_name} on Gooey.AI.",
        robots="noindex,nofollow",
    )


def pop_submit_intent() -> RecipeSubmitIntent | None:
    raw_intent = gui.session_state.pop(SUBMIT_INTENT_KEY, None)
    if not raw_intent:
        return None
    adapter = pydantic.TypeAdapter(RecipeSubmitIntent)
    try:
        if isinstance(raw_intent, str):
            return adapter.validate_json(raw_intent)
        return adapter.validate_python(raw_intent)
    except (pydantic.ValidationError, ValueError, TypeError):
        return None


def get_shown_dir(artifact: Artifact) -> str:
    """What the artifact's link shows: the live version, or the working copy before one."""
    live = artifact.live_version
    if live:
        return version_dir(artifact, live.number)
    return live_dir(artifact)


def get_proposed_versions(artifact: Artifact):
    return artifact.versions.filter(
        status=ArtifactVersion.Status.PROPOSED,
        number__gt=artifact.live_version.number if artifact.live_version_id else 0,
    ).select_related("created_by")


def get_version_status(artifact: Artifact, version: ArtifactVersion) -> str:
    if version.id == artifact.live_version_id:
        return "Live"
    if version.status == ArtifactVersion.Status.PROPOSED:
        return "Proposed"
    return "Earlier version"


def get_artifact_author(artifact: Artifact) -> str:
    if artifact.created_by_id:
        return get_user_name(artifact.created_by)
    return artifact.workspace.display_name()


def get_user_name(user) -> str:
    if not user:
        return "someone"
    return user.display_name or user.first_name(fallback="User")


def _to_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
