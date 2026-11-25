import clsx from "clsx";

import type { ArtifactWorkspaceProps } from "@gooey-types/artifact_props";
import type { SurfaceId } from "@gooey-types/recipe_workspace_props";
import { useWorkspaceLayout } from "~/appShellContext";
import type { CustomComponentProps } from "~/components";
import { RenderedChildren } from "~/renderer";

/** A website page's body: Desktop, Mobile and Files, one at a time. The top bar's views pick
 *  which, through the same workspace layout an agent page uses, so there are no panes to
 *  split or close. Every surface stays mounted, so switching back doesn't reload the page. */
export function ArtifactWorkspace({
  children,
  onChange,
  state,
  config,
}: CustomComponentProps & ArtifactWorkspaceProps) {
  const { layout, hydrated } = useWorkspaceLayout(config);
  const active: SurfaceId =
    layout.kind === "single" ? layout.surface : layout.primary;

  return (
    <div
      className={clsx(
        "d-flex flex-column flex-grow-1 w-100 mx-auto px-2 px-lg-4 py-lg-2",
        !hydrated && "gooey-until-hydrated"
      )}
      style={{ minHeight: 0, maxWidth: "var(--v2-shell-max)" }}
    >
      {children.map((surface) => (
        <div
          key={String(surface.props.surface)}
          className={clsx(
            "flex-column flex-grow-1",
            surface.props.surface === active ? "d-flex" : "d-none"
          )}
          style={{ minHeight: 0 }}
        >
          <RenderedChildren
            children={surface.children}
            onChange={onChange}
            state={state}
          />
        </div>
      ))}
    </div>
  );
}
