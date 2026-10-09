import type {
  PageShellConfig,
  SingleLayout,
  SplitLayout,
  SurfaceId,
  WorkspaceView,
} from "@gooey-types/recipe_workspace_props";

export type WorkspaceLayout = SingleLayout | SplitLayout;

export type PaneRole = "closed" | "solo" | "major" | "minor";
export type PaneRoles = Record<SurfaceId, PaneRole>;

export type WorkspaceControls = {
  addEditor: boolean;
  addPreview: boolean;
  closePreview: boolean;
};

/* The view a workspace opens on, derived from the url alone: the server sends
   `initial_layout` per url - About on a published run, the work view on a saved run - so
   the same url always opens the same way, for everyone. */
/* Two tokens, because a named view appearing and disappearing are the same change to one.
   Deliberately not `location.key`: a form post is a navigation with a fresh key and the same
   url, and the rail posts one to remember its width while a run posts one per chunk. */
/** Whether starting a run should swap this layout for the one that shows the output.
 *
 * Only from the editor on its own. That is the view a run would start out of sight from, so
 * it gives way to the split. Every other view was chosen to show something in particular -
 * About to read about the workflow, Preview to watch it - and a run is no reason to take it
 * away. Preview is already the output, and About keeps the preview beside it on a wide
 * screen, so nothing is hidden by staying put either.
 */
export function shouldRevealRunOutput(layout: WorkspaceLayout): boolean {
  return layout.kind === "single" && layout.surface === "editor";
}

/** The key to write into the form state to ask for a deferred pane's body, or null if there
 *  is nothing to ask for. State-guarded, so each response offering it deferred gets one ask. */

/* The workspace's view lives in the url's hash, so a refresh or a shared link opens on it.
   The hash rather than `?view=` because it is written straight to the address bar instead
   of navigating: a navigation would drop a live run's latest render. The server never sees
   it, so a url that does not name a view gets the one the server sends for that url. */

/** The layout a view key names, or null when it names nothing this page offers. */
export function layoutFromViewKey(
  config: PageShellConfig,
  viewKey: string | null
): WorkspaceLayout | null {
  if (!viewKey) return null;
  return (
    workspaceViews(config.views).find((view) => view.key === viewKey)?.layout ??
    null
  );
}

/** Every view the workspace can show: the server's, plus Preview where they leave it out.
 *  A visitor's About and How it works each fold to one pane below lg, leaving no way to the bot. */
export function workspaceViews(
  views: readonly WorkspaceView[]
): readonly WorkspaceView[] {
  if (views.some((view) => view.key === PREVIEW_VIEW.key)) return views;
  // second, where an editor's own Preview tab sits
  return [views[0], PREVIEW_VIEW, ...views.slice(1)];
}

const PREVIEW_VIEW: WorkspaceView = {
  key: "preview",
  label: "Preview",
  // same as `icons.play` on an editor's own Preview tab
  icon_html: '<i class="fa-regular fa-play"></i>',
  layout: { kind: "single", surface: "preview" },
  desktop_only: false,
};

/** The view key to write for a layout, or null when no declared view matches it. */
export function viewKeyForLayout(
  views: readonly WorkspaceView[],
  layout: WorkspaceLayout
): string | null {
  return views.find((view) => layoutsEqual(view.layout, layout))?.key ?? null;
}

/** The view to lay out: the one picked, else what this url is for. */
export function workspaceLayoutForView(
  config: PageShellConfig,
  viewKey: string | null
): WorkspaceLayout {
  return (
    layoutFromViewKey(config, viewKey) ??
    config.route_layout ??
    config.initial_layout
  );
}

/** `href` with its hash naming a view: the one way a link names the view to arrive on. */
export function withViewHash(href: string, viewKey: string | null): string {
  if (!viewKey) return href;
  const url = new URL(href, "http://relative.invalid");
  url.hash = viewKey;
  return `${url.pathname}${url.search}${url.hash}`;
}

/** The view key a `location.hash` names, if any. */
export function viewKeyFromHash(hash: string): string | null {
  return decodeURIComponent(hash.replace(/^#/, "")) || null;
}

/** A view picked on one page, named by the url without its hash. Every form post lands the
 *  router on a url with no hash, so the pick has to outlive the url it was written to. */
export type PickedView = { page: string; viewKey: string | null };

/** Show the output when a run starts, from the one view it would start out of sight from.
 *  Optimistic: the run redirects to its own url, whose view is the work one anyway. */
export function revealRunOutput(
  layout: WorkspaceLayout,
  runLayout: WorkspaceLayout,
  selectLayout: (next: WorkspaceLayout) => void
) {
  if (!shouldRevealRunOutput(layout)) return;
  // Deferred one macrotask: the submit has already been dispatched by the time this runs,
  // because both happen off the same click.
  // plain `setTimeout`, not `window.`: identical in a browser, and reachable from a test
  setTimeout(() => selectLayout(runLayout), 0);
}

export function isRootLayout(
  shown: WorkspaceLayout,
  initial: WorkspaceLayout,
  narrowSurface: SurfaceId,
  isNarrow: boolean
): boolean {
  return layoutsEqual(
    shown,
    foldForNarrowViewport(initial, narrowSurface, isNarrow)
  );
}

export function foldForNarrowViewport(
  layout: WorkspaceLayout,
  narrowSurface: SurfaceId,
  isNarrow: boolean
): WorkspaceLayout {
  if (!isNarrow || layout.kind === "single") {
    return layout;
  }
  if (layout.primary === "about") {
    return singleLayout("about");
  }
  if (layoutHasSurface(layout, narrowSurface)) {
    return singleLayout(narrowSurface);
  }
  return singleLayout(layout.primary);
}

/* A card that names a config pane has to land somewhere that pane is on screen. On a phone a
   split folds to the half the recipe keeps - the chat, for an owner - which is not that pane. */
export function layoutForEditorPane(
  layout: WorkspaceLayout,
  editorPane: string | null | undefined,
  narrowSurface: SurfaceId,
  isNarrow: boolean
): WorkspaceLayout {
  if (!editorPane) {
    return layout;
  }
  const shown = foldForNarrowViewport(layout, narrowSurface, isNarrow);
  return layoutHasSurface(shown, "editor") ? layout : singleLayout("editor");
}

export function paneRolesForLayout(layout: WorkspaceLayout): PaneRoles {
  const roles: PaneRoles = {
    about: "closed",
    editor: "closed",
    preview: "closed",
  };
  if (layout.kind === "single") {
    roles[layout.surface] = "solo";
    return roles;
  }
  roles[layout.primary] = "major";
  roles[layout.secondary] = "minor";
  return roles;
}

export function viewForLayout(
  views: readonly WorkspaceView[],
  layout: WorkspaceLayout
): WorkspaceView | null {
  return views.find((view) => layoutsEqual(view.layout, layout)) ?? null;
}

export function activeViewForLayouts(
  views: readonly WorkspaceView[],
  shown: WorkspaceLayout,
  stored: WorkspaceLayout,
  workspaceActive: boolean
): WorkspaceView | null {
  if (!workspaceActive) {
    return null;
  }
  return viewForLayout(views, shown) ?? viewForLayout(views, stored);
}

export function collapsePane(
  layout: WorkspaceLayout,
  surface: SurfaceId
): WorkspaceLayout {
  if (layout.kind === "single" || !layoutHasSurface(layout, surface)) {
    return layout;
  }
  if (layout.primary === surface) {
    return singleLayout(layout.secondary);
  }
  return singleLayout(layout.primary);
}

/** `views` decides whether closing the preview is offered: it may only leave a layout one
 *  of them names, or the strip would end up with nothing selected. A visitor's How it works
 *  is the editor beside the preview, and closing it left them on an Edit they have no tab
 *  for. An editor has that tab, which is why this only ever bit view-only. */
export function workspaceControlsForLayout(
  layout: WorkspaceLayout,
  views: readonly WorkspaceView[] = []
): WorkspaceControls {
  const noControls: WorkspaceControls = {
    addEditor: false,
    addPreview: false,
    closePreview: false,
  };
  if (layoutHasSurface(layout, "about")) {
    return noControls;
  }
  if (layout.kind === "split") {
    return {
      ...noControls,
      closePreview:
        layoutHasSurface(layout, "preview") &&
        !!viewForLayout(views, collapsePane(layout, "preview")),
    };
  }
  if (layout.surface === "editor") {
    return { ...noControls, addPreview: true };
  }
  if (layout.surface === "preview") {
    return { ...noControls, addEditor: true };
  }
  return noControls;
}

/** Where to navigate to reach the workspace, or null when we are already on it.
 *  Named for what it answers: there is no layout in the question. */
export function workspaceHrefToNavigate(
  workspaceActive: boolean,
  workspaceHref: string
): string | null {
  if (workspaceActive || !workspaceHref) {
    return null;
  }
  return appRelativeHref(workspaceHref);
}

export function singleLayout(surface: SurfaceId): SingleLayout {
  return { kind: "single", surface };
}

export function splitLayout(
  primary: SurfaceId,
  secondary: SurfaceId
): SplitLayout {
  if (primary === secondary) {
    throw new Error("A split layout requires two different surfaces");
  }
  return { kind: "split", primary, secondary };
}

export function layoutsEqual(
  left: WorkspaceLayout,
  right: WorkspaceLayout
): boolean {
  if (left.kind !== right.kind) {
    return false;
  }
  if (left.kind === "single" && right.kind === "single") {
    return left.surface === right.surface;
  }
  if (left.kind === "split" && right.kind === "split") {
    return left.primary === right.primary && left.secondary === right.secondary;
  }
  return false;
}

function layoutHasSurface(
  layout: WorkspaceLayout,
  surface: SurfaceId
): boolean {
  if (layout.kind === "single") {
    return layout.surface === surface;
  }
  return layout.primary === surface || layout.secondary === surface;
}

/** Python sends absolute app urls; Remix's `navigate` wants a path. Handed an absolute one
 *  it resolves it against the origin, which doubles it - `/http://host/agent/` - and 404s.
 *  Every navigation off a server-sent href has to come through here. */
export function appRelativeHref(href: string): string {
  if (!href.startsWith("http://") && !href.startsWith("https://")) {
    return href;
  }
  const url = new URL(href);
  return `${url.pathname}${url.search}${url.hash}`;
}
