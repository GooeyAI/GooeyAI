import type { ArtifactFrameProps } from "@gooey-types/artifact_props";
import type { CustomComponentProps } from "~/components";
import { RenderedChildren } from "~/renderer";

// Desktop fills the pane; Mobile is a phone-width frame, centred.
const MOBILE_WIDTH = 390;

export function ArtifactFrame({
  title,
  srcdoc,
  src,
  sandbox,
  device = "desktop",
  children,
  onChange,
  state,
}: CustomComponentProps & ArtifactFrameProps) {
  const frame = (
    <iframe
      // when set, the browser shows this instead of src, so the frame never hits an expired link
      srcDoc={srcdoc ?? undefined}
      src={srcdoc ? undefined : src ?? undefined}
      title={title}
      className="w-100 h-100 border-0 d-block"
      style={{ background: "#fff" }}
      sandbox={sandbox}
      allow="fullscreen; autoplay"
    />
  );
  return (
    <div className="d-flex flex-column gap-2 h-100 px-2 px-lg-0">
      {/* the status line above the page, rendered from python */}
      <RenderedChildren children={children} onChange={onChange} state={state} />
      {device === "mobile" ? (
        <div
          className="d-flex justify-content-center flex-grow-1 rounded py-3"
          style={{ minHeight: 0, background: "var(--bs-tertiary-bg, #f3f4f6)" }}
        >
          <div
            className="border rounded-4 overflow-hidden shadow-sm bg-white"
            style={{ width: MOBILE_WIDTH, maxWidth: "100%", height: "100%" }}
          >
            {frame}
          </div>
        </div>
      ) : (
        <div
          className="flex-grow-1 border rounded overflow-hidden"
          style={{ minHeight: 0 }}
        >
          {frame}
        </div>
      )}
    </div>
  );
}
