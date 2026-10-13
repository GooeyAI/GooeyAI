import { describe, expect, it, vi } from "vitest";

import type { PageShellConfig } from "@gooey-types/recipe_workspace_props";
import {
  activeViewForLayouts,
  appRelativeHref,
  collapsePane,
  foldForNarrowViewport,
  isRootLayout,
  layoutForEditorPane,
  layoutFromViewKey,
  layoutsEqual,
  paneRolesForLayout,
  revealRunOutput,
  shouldRevealRunOutput,
  singleLayout,
  splitLayout,
  viewKeyFromHash,
  viewKeyForLayout,
  withViewHash,
  workspaceControlsForLayout,
  workspaceHrefToNavigate,
  workspaceLayoutForView,
  workspaceViews,
} from "./paneState";

const about = splitLayout("about", "preview");
const edit = singleLayout("editor");
const preview = singleLayout("preview");
const split = splitLayout("editor", "preview");

const baseConfig: PageShellConfig = {
  storage_key: "recipe-layout",
  initial_layout: about,
  run_layout: split,
  route_layout: null,
  views: [
    {
      key: "about",
      label: "About",
      icon_html: null,
      layout: about,
      desktop_only: false,
    },
    {
      key: "edit",
      label: "Edit",
      icon_html: null,
      layout: edit,
      desktop_only: false,
    },
    {
      key: "preview",
      label: "Preview",
      icon_html: null,
      layout: preview,
      desktop_only: false,
    },
    {
      key: "split",
      label: "Split",
      icon_html: null,
      layout: split,
      desktop_only: true,
    },
  ],
  narrow_surface: "preview",
  workspace_href: "/agent/",
  workspace_active: true,
  active_run_id: null,
};

describe("workspace layout", () => {
  it("models a single surface separately from a split arrangement", () => {
    expect(edit).toEqual({ kind: "single", surface: "editor" });
    expect(split).toEqual({
      kind: "split",
      primary: "editor",
      secondary: "preview",
    });
    expect(() => splitLayout("editor", "editor")).toThrow(
      "requires two different surfaces"
    );
  });

  it("compares discriminated layouts", () => {
    expect(layoutsEqual(split, { ...split })).toBe(true);
    expect(layoutsEqual(split, about)).toBe(false);
    expect(layoutsEqual(edit, preview)).toBe(false);
  });
});

describe("shouldRevealRunOutput", () => {
  it("is true only for the editor on its own", () => {
    // The one view a run would start out of sight from.
    expect(shouldRevealRunOutput(edit)).toBe(true);
    expect(shouldRevealRunOutput(preview)).toBe(false);
    expect(shouldRevealRunOutput(about)).toBe(false);
    expect(shouldRevealRunOutput(split)).toBe(false);
    expect(shouldRevealRunOutput(singleLayout("about"))).toBe(false);
  });
});

describe("responsive layout", () => {
  it("folds work splits to the configured surface", () => {
    expect(foldForNarrowViewport(split, "preview", true)).toEqual(preview);
    expect(foldForNarrowViewport(split, "editor", true)).toEqual(edit);
  });

  it("keeps About as the primary narrow surface", () => {
    expect(foldForNarrowViewport(about, "preview", true)).toEqual(
      singleLayout("about")
    );
  });

  it("leaves wide and single layouts unchanged", () => {
    expect(foldForNarrowViewport(split, "preview", false)).toEqual(split);
    expect(foldForNarrowViewport(edit, "preview", true)).toEqual(edit);
  });

  it("keeps a config pane reachable when the split folds away from it", () => {
    // An About card naming a pane, tapped on a phone by someone whose narrow surface is the
    // chat: the split would fold to the chat, so the editor alone stands in for it.
    expect(layoutForEditorPane(split, "knowledge", "preview", true)).toEqual(
      edit
    );
    expect(layoutForEditorPane(split, "knowledge", "editor", true)).toEqual(
      split
    );
    expect(layoutForEditorPane(split, "knowledge", "preview", false)).toEqual(
      split
    );
  });

  it("leaves a target that names no pane alone", () => {
    expect(layoutForEditorPane(preview, null, "preview", true)).toEqual(
      preview
    );
    expect(layoutForEditorPane(about, undefined, "preview", true)).toEqual(
      about
    );
  });

  it("calls the root what the fold shows, not what is stored", () => {
    // The work split folds to Preview, so Preview chosen on its own is the same screen and
    // has to count as the root too - otherwise Back sits there offering to swap one for the
    // other, which the fold then draws identically.
    expect(isRootLayout(preview, split, "preview", true)).toBe(true);
    expect(isRootLayout(edit, split, "preview", true)).toBe(false);
    // Wide, the two are different arrangements again.
    expect(isRootLayout(preview, split, "preview", false)).toBe(false);
    expect(isRootLayout(split, split, "preview", false)).toBe(true);
  });
});

describe("pane roles and controls", () => {
  it("assigns roles from explicit surfaces", () => {
    expect(paneRolesForLayout(about)).toEqual({
      about: "major",
      editor: "closed",
      preview: "minor",
    });
    expect(paneRolesForLayout(edit)).toEqual({
      about: "closed",
      editor: "solo",
      preview: "closed",
    });
  });

  it("offers only valid editor/preview pairing controls", () => {
    expect(workspaceControlsForLayout(edit, baseConfig.views)).toEqual({
      addEditor: false,
      addPreview: true,
      closePreview: false,
    });
    expect(workspaceControlsForLayout(preview, baseConfig.views)).toEqual({
      addEditor: true,
      addPreview: false,
      closePreview: false,
    });
    expect(workspaceControlsForLayout(split, baseConfig.views)).toEqual({
      addEditor: false,
      addPreview: false,
      closePreview: true,
    });
    expect(workspaceControlsForLayout(about, baseConfig.views)).toEqual({
      addEditor: false,
      addPreview: false,
      closePreview: false,
    });
  });

  it("withholds Close Preview when nothing would be left selected", () => {
    // A visitor's set: About and How it works, both of them the preview paired with
    // something. Closing it lands on a bare editor they have no tab for, so the strip
    // would show nothing selected - the control is not offered.
    const visitorViews = baseConfig.views.filter((view) => view.key !== "edit");
    expect(workspaceControlsForLayout(split, visitorViews).closePreview).toBe(
      false
    );
    expect(
      workspaceControlsForLayout(split, baseConfig.views).closePreview
    ).toBe(true);
  });
});

describe("view selection", () => {
  it("falls back to the stored view after a responsive fold", () => {
    const active = activeViewForLayouts(baseConfig.views, preview, split, true);
    expect(active?.key).toBe("preview");

    const viewerViews = baseConfig.views.filter((view) =>
      ["about", "split"].includes(view.key)
    );
    expect(activeViewForLayouts(viewerViews, preview, split, true)?.key).toBe(
      "split"
    );
  });

  it("selects no workspace view on another route", () => {
    expect(
      activeViewForLayouts(baseConfig.views, split, split, false)
    ).toBeNull();
  });
});

describe("workspace navigation", () => {
  it("strips an absolute app origin", () => {
    expect(
      workspaceHrefToNavigate(
        false,
        "https://gooey.ai/agent/?run_id=run-1&uid=user-1"
      )
    ).toBe("/agent/?run_id=run-1&uid=user-1");
  });

  it("does not navigate when the workspace is active", () => {
    expect(workspaceHrefToNavigate(true, "/agent/")).toBeNull();
  });

  it("relativizes any server-sent href, keeping the query", () => {
    // Handed an absolute url, `navigate` resolves it against the origin and 404s on
    // `/http://localhost:3000/agent/...` - so every navigation off a server-sent href has
    // to come through here, the rail's Ask Gooey included.
    expect(
      appRelativeHref("http://localhost:3000/agent/?run_id=32i1&uid=1rEt")
    ).toBe("/agent/?run_id=32i1&uid=1rEt");
    expect(appRelativeHref("https://gooey.ai/agent/#tools")).toBe(
      "/agent/#tools"
    );
    // already a path: left exactly as it is
    expect(appRelativeHref("/agent/?run_id=32i1")).toBe("/agent/?run_id=32i1");
  });
});

describe("the view lives in the url", () => {
  it("selects only a view the server actually declared", () => {
    expect(layoutFromViewKey(baseConfig, "edit")).toEqual(edit);
    expect(layoutFromViewKey(baseConfig, "not-a-view")).toBeNull();
    expect(layoutFromViewKey(baseConfig, null)).toBeNull();
  });

  it("falls back to what the url is for when it names no view", () => {
    expect(workspaceLayoutForView(baseConfig, null)).toEqual(
      baseConfig.initial_layout
    );
    expect(workspaceLayoutForView(baseConfig, "nonsense")).toEqual(
      baseConfig.initial_layout
    );
  });

  it("lets a route's own view outrank the page default, and the url outrank both", () => {
    const onPreview = { ...baseConfig, route_layout: preview };
    expect(workspaceLayoutForView(onPreview, null)).toEqual(preview);
    expect(workspaceLayoutForView(onPreview, "edit")).toEqual(edit);
  });

  it("gives a visitor's Preview a key, though the server does not declare it", () => {
    const visitorViews = baseConfig.views.filter(
      (view) => view.key === "about"
    );
    const visitor = { ...baseConfig, views: visitorViews };
    const key = viewKeyForLayout(workspaceViews(visitorViews), preview);
    expect(key).toBe("preview");
    expect(layoutFromViewKey(visitor, key)).toEqual(preview);
  });

  it("round-trips a layout through its key", () => {
    const key = viewKeyForLayout(baseConfig.views, edit);
    expect(key).toBe("edit");
    expect(layoutFromViewKey(baseConfig, key)).toEqual(edit);
  });

  it("has no key for a layout no view declares, so the url is left alone", () => {
    expect(
      viewKeyForLayout(baseConfig.views, splitLayout("about", "editor"))
    ).toBeNull();
  });

  it("names the view on a link without disturbing the rest of the url", () => {
    expect(withViewHash("/agent/my-bot/?run_id=r1", "edit")).toBe(
      "/agent/my-bot/?run_id=r1#edit"
    );
    expect(withViewHash("/agent/my-bot/", null)).toBe("/agent/my-bot/");
    // replaces rather than appends a second one
    expect(withViewHash("/agent/#about", "edit")).toBe("/agent/#edit");
  });

  it("reads the view back out of a hash", () => {
    expect(viewKeyFromHash("#edit")).toBe("edit");
    expect(
      viewKeyFromHash(new URL(withViewHash("/a/", "edit"), "http://x").hash)
    ).toBe("edit");
    expect(viewKeyFromHash("")).toBeNull();
    expect(viewKeyFromHash("#")).toBeNull();
  });
});

describe("revealRunOutput", () => {
  it("swaps a lone editor for the run layout, once the submit is away", () => {
    vi.useFakeTimers();
    const picked: unknown[] = [];
    revealRunOutput(edit, split, (next) => picked.push(next));
    expect(picked).toEqual([]);
    vi.runAllTimers();
    expect(picked).toEqual([split]);
    vi.useRealTimers();
  });

  it("leaves every other view alone - they were each chosen to show something", () => {
    vi.useFakeTimers();
    const picked: unknown[] = [];
    for (const layout of [about, preview, split]) {
      revealRunOutput(layout, split, (next) => picked.push(next));
    }
    vi.runAllTimers();
    expect(picked).toEqual([]);
    vi.useRealTimers();
  });
});
