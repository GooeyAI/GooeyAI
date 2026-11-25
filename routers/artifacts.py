import os

import pydantic
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.template.defaultfilters import filesizeformat
from fastapi import HTTPException
from furl import furl
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
    handle_gooey_builder_redirect,
    render_gooey_builder_embed,
)
from daras_ai_v2.meta_content import raw_build_meta_tags
from daras_ai_v2.web_widget_embed import get_chat_widget_messages
from files.models import Artifact, ArtifactChat, ArtifactDraft
from gooey_gui.types.artifact_props import (
    ArtifactCard,
    ArtifactFileEntry,
    ArtifactFilesProps,
    ArtifactFilterOption,
    ArtifactFrameProps,
    ArtifactGridProps,
    ArtifactLink,
    ArtifactWorkspaceProps,
)
from gooey_gui.types.recipe_top_bar_props import (
    CopyShare,
    LinkTarget,
    ManageShare,
    MenuIntent,
    NoShare,
    PublishIntent,
    RecipeSubmitIntent,
    RecipeTopBarProps,
    ShareIntent,
    SubmitTarget,
    TopBarAuthor,
    TopBarMenuItem,
    TopBarParent,
)
from gooey_gui.types.recipe_workspace_props import (
    PageShellConfig,
    RecipeSurfaceProps,
    SingleLayout,
    SurfaceId,
    WorkspaceView,
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
    can_user_ask_gooey,
    delete_artifact,
    draft_dir,
    duplicate_artifact,
    get_artifact,
    get_artifact_blob,
    get_artifact_title,
    get_artifact_url,
    get_download_url,
    get_shown_draft,
    get_signed_url,
    list_dir_files,
    live_dir,
    publish_draft,
    read_artifact_html,
    rename_artifact,
    render_artifact_share_dialog,
    sync_workspace_artifacts,
)
from workspaces.models import Workspace

app = CustomAPIRouter()

SUBMIT_INTENT_KEY = "--artifact-submit-intent"
MENU_RENAME = "rename"
MENU_VERSIONS = "versions"
MENU_DUPLICATE = "duplicate"
MENU_DELETE = "delete"
# card menus on the Artefacts page link here with ?action=<one of these>
LINKED_ACTIONS = {"share", MENU_RENAME, MENU_DELETE}

DESKTOP_SURFACE = SurfaceId.desktop
MOBILE_SURFACE = SurfaceId.mobile
FILES_SURFACE = SurfaceId.files

SORTS = {"edited": "Last edited", "newest": "Newest", "name": "Name"}
# grid thumbnails embed the page; bigger pages get a placeholder
MAX_THUMBNAIL_HTML_BYTES = 300_000
TEXT_FILE_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".json", ".txt", ".md", ".svg", ".csv", ".xml",
}  # fmt: skip
MAX_SHOWN_FILE_BYTES = 200_000


@gui.route(app, ARTIFACTS_PATH)
def artifacts_route(request: Request):
    if not request.user or request.user.is_anonymous:
        raise gui.RedirectException(get_login_url(request))
    with sidebar_page_wrapper(request) as workspace:
        render_artifacts_grid(request, workspace)
    url = get_og_url_path(request)
    return dict(
        meta=raw_build_meta_tags(
            url=url, title="Artefacts • Gooey.AI", robots="noindex,nofollow"
        )
    )


def render_artifacts_grid(request: Request, workspace: Workspace):
    sync_workspace_artifacts(workspace)
    user = request.user
    params = request.query_params
    search = params.get("q", "").strip()
    made_by = params.get("by") or "everyone"
    sort = params.get("sort") or "edited"
    if sort not in SORTS:
        sort = "edited"

    artifacts = Artifact.objects.filter(workspace=workspace).select_related(
        "created_by", "live_version", "workspace__handle"
    )
    if search:
        artifacts = artifacts.filter(folder__icontains=search.replace(" ", "-"))
    if made_by == "me":
        artifacts = artifacts.filter(created_by=user)
    elif made_by.isdigit():
        artifacts = artifacts.filter(created_by_id=int(made_by))
    artifacts = artifacts.order_by(
        {"edited": "-updated_at", "newest": "-created_at", "name": "folder"}[sort]
    )
    cards = [
        build_artifact_card(request, artifact)
        for artifact in artifacts
        if artifact.can_user_view(user)
    ]

    def filter_href(**changes) -> str:
        query = dict(q=search, by=made_by, sort=sort) | changes
        query = {
            k: v for k, v in query.items() if v and v not in ("everyone", "edited")
        }
        return furl(ARTIFACTS_PATH).set(query).url

    makers = {
        artifact.created_by
        for artifact in Artifact.objects.filter(workspace=workspace).select_related(
            "created_by"
        )
        if artifact.created_by_id and artifact.created_by_id != user.id
    }
    made_by_options = [
        ArtifactFilterOption(
            label="Everyone", href=filter_href(by=""), active=made_by == "everyone"
        ),
        ArtifactFilterOption(
            label="Me", href=filter_href(by="me"), active=made_by == "me"
        ),
    ] + [
        ArtifactFilterOption(
            label=get_user_name(maker),
            href=filter_href(by=str(maker.id)),
            active=made_by == str(maker.id),
        )
        for maker in sorted(makers, key=get_user_name)
    ]

    gui.model_component(
        ArtifactGridProps(
            title="Artefacts",
            subtitle=f"Websites that Gooey made for {workspace.display_name(user)}",
            create_menu=[
                ArtifactLink(
                    label="Website",
                    href=furl("/new/").set(dict(prompt="Create a website with ")).url,
                    icon_class="fa-regular fa-globe",
                ),
            ],
            search_action=ARTIFACTS_PATH,
            search_value=search,
            search_hidden={
                k: v
                for k, v in dict(by=made_by, sort=sort).items()
                if v not in ("everyone", "edited")
            },
            made_by=made_by_options,
            sort=[
                ArtifactFilterOption(
                    label=label, href=filter_href(sort=key), active=key == sort
                )
                for key, label in SORTS.items()
            ],
            cards=cards,
            empty_message=(
                f"No websites match “{search}”."
                if search
                else "No websites yet. Create one with Ask Gooey and it shows up here."
            ),
        )
    )


def build_artifact_card(request: Request, artifact: Artifact) -> ArtifactCard:
    user = request.user
    srcdoc, _ = read_artifact_html(
        artifact.workspace, live_dir(artifact), max_bytes=MAX_THUMBNAIL_HTML_BYTES
    )
    url = get_artifact_url(artifact)
    menu = [
        ArtifactLink(
            label="Open",
            href=url,
            icon_class="fa-regular fa-arrow-up-right-from-square",
        )
    ]
    download_url = get_download_url(artifact, live_dir(artifact))
    if download_url:
        menu.append(
            ArtifactLink(
                label="Download", href=download_url, icon_class="fa-regular fa-download"
            )
        )
    if artifact.can_user_manage(user):
        menu += [
            ArtifactLink(
                label="Share…",
                href=get_artifact_url(artifact, action="share"),
                icon_class="fa-regular fa-share-nodes",
            ),
            ArtifactLink(
                label="Rename",
                href=get_artifact_url(artifact, action=MENU_RENAME),
                icon_class="fa-regular fa-pen",
            ),
            ArtifactLink(
                label="Delete",
                href=get_artifact_url(artifact, action=MENU_DELETE),
                icon_class="fa-regular fa-trash",
                is_danger=True,
            ),
        ]
    live = artifact.live_version
    edited = live.created_at if live else artifact.updated_at
    author = get_artifact_author(artifact)
    is_someone_else = bool(artifact.created_by_id) and artifact.created_by_id != user.id
    return ArtifactCard(
        title=get_artifact_title(artifact),
        href=url,
        thumbnail_srcdoc=srcdoc,
        meta=f"Website · Edited {naturaltime(edited)}",
        author_initial=author[:1].upper() if is_someone_else else None,
        author_name=author,
        menu=menu,
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

    # other files of the folder
    if parts[1:] and parts[1:] != [ARTIFACT_INDEX]:
        blob = get_artifact_blob(
            artifact.workspace, live_dir(artifact) + "/".join(parts[1:])
        )
        if not blob:
            return None
        return RedirectResponse(get_signed_url(blob))

    draft = get_shown_draft(artifact, request.query_params.get("draft"))
    # drafts are for the workspace: visitors of a public page only see the live version
    is_live = draft and draft.id == artifact.live_version.draft_id
    if not draft or (not is_live and not can_user_ask_gooey(artifact, user)):
        raise HTTPException(status_code=404)

    hosts_builder = can_user_ask_gooey(artifact, user) and can_launch_gooey_builder(
        request, artifact.workspace
    )
    with sidebar_page_wrapper(
        request,
        fill_viewport=True,
        hosts_builder=True,
        builder_href="" if hosts_builder else None,
    ):
        render_artifact_page(
            request, artifact, draft=draft, hosts_builder=hosts_builder
        )
    return dict(
        meta=build_artifact_meta_tags(request, artifact, get_artifact_title(artifact))
    )


def render_artifact_page(
    request: Request, artifact: Artifact, *, draft: ArtifactDraft, hosts_builder: bool
):
    """The live page, or one draft (`?draft=`), as an agent shows its published run or one
    of its runs."""
    is_live = draft.id == artifact.live_version.draft_id
    directory = live_dir(artifact) if is_live else draft_dir(draft)
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
            # editors land with Ask Gooey open beside the page, as in the designs
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
        render_artifact_workspace(artifact, config=config, directory=directory)

    chat = None
    if builder_pane is not None:
        chat, _ = ArtifactChat.objects.get_or_create(
            artifact=artifact, user=request.user
        )
        with builder_pane:
            render_artifact_builder(chat)

    with top_bar_placeholder:
        render_artifact_top_bar(
            request,
            artifact,
            draft=draft,
            directory=directory,
            config=config,
            chat=chat,
            reload_href=get_artifact_url(artifact, **request.query_params),
        )

    handle_artifact_actions(request, artifact, draft=draft)


def render_artifact_workspace(
    artifact: Artifact, *, config: PageShellConfig, directory: str
):
    title = get_artifact_title(artifact)
    srcdoc, src = read_artifact_html(artifact.workspace, directory)
    with gui.model_component(ArtifactWorkspaceProps(config=config)):
        for surface, device in (
            (DESKTOP_SURFACE, "desktop"),
            (MOBILE_SURFACE, "mobile"),
        ):
            with gui.model_component(RecipeSurfaceProps(surface=surface)):
                gui.model_component(
                    ArtifactFrameProps(
                        title=title,
                        srcdoc=srcdoc,
                        src=src,
                        sandbox=ARTIFACT_SANDBOX,
                        device=device,
                    )
                )
        with gui.model_component(RecipeSurfaceProps(surface=FILES_SURFACE)):
            render_artifact_files(artifact, directory=directory)


def render_artifact_files(artifact: Artifact, *, directory: str):
    root = gcs_v2.workspace_files_prefix(artifact.workspace_id) + directory
    blobs = sorted(list_dir_files(artifact.workspace, directory), key=lambda b: b.name)
    entries = []
    seen_folders = set()
    for blob in blobs:
        path = blob.name.removeprefix(root)
        parts = path.split("/")
        for depth, folder in enumerate(parts[:-1]):
            folder_path = "/".join(parts[: depth + 1])
            if folder_path in seen_folders:
                continue
            seen_folders.add(folder_path)
            entries.append(
                ArtifactFileEntry(
                    path=folder_path, name=folder, depth=depth, is_folder=True
                )
            )
        ext = os.path.splitext(path)[1].lower()
        content = None
        if ext in TEXT_FILE_EXTENSIONS and (blob.size or 0) <= MAX_SHOWN_FILE_BYTES:
            content = blob.download_as_text()
        entries.append(
            ArtifactFileEntry(
                path=path,
                name=parts[-1],
                depth=len(parts) - 1,
                size_label=filesizeformat(blob.size or 0),
                type_label=ext.lstrip(".").upper() or "File",
                content=content,
                download_url=get_signed_url(blob, download_name=parts[-1]),
            )
        )
    total = sum(blob.size or 0 for blob in blobs)
    count = len(blobs)
    gui.model_component(
        ArtifactFilesProps(
            summary=f"{count} file{'s' * (count != 1)} · {filesizeformat(total)}",
            entries=entries,
            selected=ARTIFACT_INDEX,
        )
    )


def render_artifact_builder(chat: ArtifactChat):
    # the widget's "new conversation" sets this; the next message starts a fresh chat
    if gui.session_state.pop("builderOnNewConversation", None):
        chat.builder_saved_run = None
        chat.save(update_fields=["builder_saved_run", "updated_at"])
    builder_sr = chat.builder_saved_run
    # an edit made a draft: move to it, as an agent's page moves to the run Ask Gooey made
    handle_gooey_builder_redirect(builder_sr)
    if builder_sr:
        builder_run_url = builder_sr.get_app_url()
        messages = get_chat_widget_messages(
            builder_sr.to_dict(), web_url=builder_run_url
        )
        if builder_sr.run_status:
            # re-render while Ask Gooey works, so the page picks up its edits
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
    draft: ArtifactDraft,
    directory: str,
    config: PageShellConfig,
    chat: ArtifactChat | None,
    reload_href: str,
):
    """The agent's bar: Publish holds Update (or Save as New) and Share, with the dot for
    unpublished changes, and a draft links back to the live page."""
    user = request.user
    title = get_artifact_title(artifact)
    is_live = draft.id == artifact.live_version.draft_id
    if artifact.can_user_manage(user):
        share = ManageShare(icon_html=icons.share)
    elif artifact.is_member(user):
        share = CopyShare(url=get_artifact_url(artifact), icon_html=icons.share)
    else:
        share = NoShare()
    publish_label = get_publish_label(artifact, user)
    hosts_builder = chat is not None
    gui.model_component(
        RecipeTopBarProps(
            config=config,
            title=title,
            title_href=get_artifact_url(artifact),
            author=TopBarAuthor(label=get_artifact_author_label(artifact, draft)),
            parent=(
                None
                if is_live
                else TopBarParent(label=title, href=get_artifact_url(artifact))
            ),
            title_menu_items=get_artifact_menu_items(
                request, artifact, directory=directory
            ),
            submit_intent_key=SUBMIT_INTENT_KEY,
            publish_label=publish_label,
            publish_intent=PublishIntent() if publish_label else None,
            has_unpublished_changes=not is_live,
            share=share,
            reload_href=reload_href,
            view_only=not artifact.is_member(user),
            builder_panel_key=GOOEY_BUILDER_EVENT_KEY if hosts_builder else None,
            builder_storage_key=GOOEY_BUILDER_STORAGE_KEY if hosts_builder else None,
            builder_new_event=(
                f"{GOOEY_BUILDER_EVENT_KEY}:new"
                if hosts_builder and chat.builder_saved_run_id
                else None
            ),
            builder_photo_url=get_gooey_builder_photo_url() if hosts_builder else None,
        )
    )


def get_publish_label(artifact: Artifact, user) -> str | None:
    """As on an agent: Update for people who can change the live page, Save as New for the
    workspace's other members, nothing for visitors."""
    if artifact.can_user_edit(user):
        return "Update"
    if artifact.is_member(user):
        return "Save as New"
    return None


def get_artifact_author_label(artifact: Artifact, draft: ArtifactDraft) -> str:
    if draft.id == artifact.live_version.draft_id:
        return f"Website · by {get_artifact_author(artifact)}"
    # an earlier version, opened from Versions
    version = draft.versions.order_by("-number").first()
    if version:
        return f"Version {version.number} · by {get_user_name(version.created_by)}"
    label = f"Draft by {get_user_name(draft.created_by)}"
    based_on = draft.based_on and draft.based_on.versions.order_by("-number").first()
    if based_on:
        label += f" · from version {based_on.number}"
    return label


def get_artifact_menu_items(
    request: Request, artifact: Artifact, *, directory: str
) -> list[TopBarMenuItem]:
    """Rename, Versions, Duplicate, Download, Delete - each for the people allowed to."""
    user = request.user
    can_manage = artifact.can_user_manage(user)
    items = []
    if can_manage:
        items.append(menu_item(MENU_RENAME, "Rename", "fa-pen"))
    items.append(menu_item(MENU_VERSIONS, "Versions", "fa-clock-rotate-left"))
    if artifact.is_member(user):
        items.append(menu_item(MENU_DUPLICATE, "Duplicate", "fa-code-fork"))
    download_url = get_download_url(artifact, directory)
    if download_url:
        items.append(
            TopBarMenuItem(
                key="download",
                label="Download",
                icon_html='<i class="fa-regular fa-download"></i>',
                target=LinkTarget(href=download_url),
            )
        )
    if can_manage:
        items.append(menu_item(MENU_DELETE, "Delete", "fa-trash", is_danger=True))
    return items


def menu_item(key: str, label: str, icon: str, *, is_danger: bool = False):
    return TopBarMenuItem(
        key=key,
        label=label,
        icon_html=f'<i class="fa-regular {icon}"></i>',
        target=SubmitTarget(intent=MenuIntent(item_key=key)),
        is_danger=is_danger,
    )


def handle_artifact_actions(
    request: Request, artifact: Artifact, *, draft: ArtifactDraft
):
    user = request.user
    intent = pop_submit_intent()
    picked = intent.item_key if isinstance(intent, MenuIntent) else None
    # card menus on the Artefacts page link here with ?action=, once per visit
    linked = request.query_params.get("action")
    if linked in LINKED_ACTIONS and not gui.session_state.get("artifact-linked-action"):
        gui.session_state["artifact-linked-action"] = linked
        picked = linked
    can_manage = artifact.can_user_manage(user)

    publish_ref = gui.use_alert_dialog(key="artifact-publish")
    if isinstance(intent, PublishIntent) and get_publish_label(artifact, user):
        publish_ref.set_open(True)
    if publish_ref.is_open:
        render_artifact_publish_dialog(
            request, artifact, draft=draft, dialog=publish_ref
        )

    share_ref = gui.use_alert_dialog(key="artifact-share")
    if (isinstance(intent, ShareIntent) or picked == "share") and can_manage:
        share_ref.set_open(True)
    if share_ref.is_open:
        render_artifact_share_dialog(request, artifact, dialog=share_ref)

    rename_ref = gui.use_alert_dialog(key="artifact-rename")
    if picked == MENU_RENAME and can_manage:
        rename_ref.set_open(True)
    if rename_ref.is_open:
        with gui.alert_dialog(ref=rename_ref, modal_title="#### Rename"):
            name = gui.text_input(
                "Name", value=get_artifact_title(artifact), key="artifact-new-name"
            )
            gui.caption("The link changes to match the new name.")
            if gui.button("Save", type="primary", key="artifact-rename-save"):
                error = rename_artifact(artifact, name)
                if error:
                    gui.error(error)
                else:
                    raise gui.RedirectException(get_artifact_url(artifact))

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

    if picked == MENU_DUPLICATE and artifact.is_member(user):
        copy = duplicate_artifact(artifact, user=user, draft=draft)
        raise gui.RedirectException(get_artifact_url(copy))

    delete_ref = gui.use_confirm_dialog(key="artifact-delete-confirm")
    if picked == MENU_DELETE and can_manage:
        delete_ref.set_open(True)
    if delete_ref.is_open:
        with gui.confirm_dialog(
            ref=delete_ref,
            modal_title=f"#### Delete “{get_artifact_title(artifact)}”?",
            confirm_label="Delete",
            confirm_className="border-danger bg-danger text-white",
        ):
            gui.write(
                "The website, its files and all its versions are deleted, and its link "
                "stops working."
            )
    if delete_ref.pressed_confirm and can_manage:
        delete_artifact(artifact)
        raise gui.RedirectException(ARTIFACTS_PATH)


def render_artifact_publish_dialog(
    request: Request, artifact: Artifact, *, draft: ArtifactDraft, dialog
):
    """The agent's publish dialog, cut to what a website has: change notes for Update, a
    name for Save as New."""
    user = request.user
    is_live = draft.id == artifact.live_version.draft_id
    label = get_publish_label(artifact, user)
    with gui.alert_dialog(ref=dialog, modal_title=f"#### {label}"):
        if label == "Update":
            gui.write(
                "Everyone who can open this website sees this version.",
                className="text-muted",
            )
            notes = gui.text_input(
                "Change notes",
                key="artifact-change-notes",
                placeholder="What changed, for Versions (optional)",
            )
        else:
            name = gui.text_input(
                "Name",
                key="artifact-copy-name",
                value=f"{get_artifact_title(artifact)} copy",
            )
            gui.caption("A copy of what's on screen, made by you.")
        if not gui.button(label, type="primary", key="artifact-publish-save"):
            return
        if label == "Update":
            if is_live:
                gui.error("No changes to publish", icon="⚠️")
                return
            publish_draft(artifact, draft, user=user, note=notes.strip())
            raise gui.RedirectException(get_artifact_url(artifact))
        copy = duplicate_artifact(artifact, user=user, draft=draft, name=name)
        raise gui.RedirectException(get_artifact_url(copy))


def render_artifact_versions(request: Request, artifact: Artifact):
    """Each Update, like an agent's Version History: open one, press Update to go back."""
    versions = artifact.versions.select_related("created_by", "draft")
    for version in versions:
        is_live = version.id == artifact.live_version_id
        href = get_artifact_url(
            artifact, **({} if is_live else dict(draft=version.draft.draft_id))
        )
        with gui.div(className="border-bottom py-2"):
            text = (
                f"**[Version {version.number}]({href})**"
                f"{' · live' if is_live else ''} · by "
                f"{get_user_name(version.created_by)} · {naturaltime(version.created_at)}"
            )
            if version.note:
                text += f" · {version.note}"
            gui.write(text, className="mb-0")


def render_artifact_no_access(request: Request, artifact: Artifact):
    if artifact.is_member(request.user):
        gui.write(
            "#### This page is private\n\nOnly the person who made it can see it."
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
                icon_html='<i class="fa-regular fa-folder"></i>',
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


def get_artifact_author(artifact: Artifact) -> str:
    if artifact.created_by_id:
        return get_user_name(artifact.created_by)
    return artifact.workspace.display_name()


def get_user_name(user) -> str:
    if not user:
        return "someone"
    return user.display_name or user.first_name(fallback="User")
