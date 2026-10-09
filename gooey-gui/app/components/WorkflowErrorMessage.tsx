import { useNavigate } from "@remix-run/react";
import { useState } from "react";
import type { CustomComponentProps } from "~/components";
import { fetchServerAPI } from "~/fetchServerAPI";
import { RenderedChildren } from "~/renderer";
import { builderOpenNavigationState } from "./NavigationSidebar/builderIntent";
import "./WorkflowErrorMessage.css";

export function WorkflowErrorMessage({
  prompt,
  workflow_state,
  photo_url,
  children,
  onChange,
  state,
}: CustomComponentProps & {
  prompt: string;
  workflow_state: Record<string, any>;
  photo_url: string;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  async function askGooey() {
    setBusy(true);
    try {
      const redirectUrl = await fetchServerAPI<string | null>(
        "/__/gooey-builder/send-message",
        {
          workflow_url: window.location.href,
          // no builder_run_url: always start a fresh builder conversation
          workflow_state,
          input_data: { input_prompt: prompt },
        }
      );
      if (!redirectUrl) return;
      const url = new URL(redirectUrl);
      // opens the builder panel on the new page, so the user can follow the fix
      navigate(url.pathname + url.search, {
        state: builderOpenNavigationState(),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workflow-error-message">
      <span>🔥</span>
      <div>
        <RenderedChildren
          children={children}
          onChange={onChange}
          state={state}
        />
      </div>
      <button
        type="button"
        className="workflow-error-fix-btn btn btn-theme btn-secondary d-inline-flex align-items-center gap-1 m-0"
        disabled={busy}
        onClick={askGooey}
      >
        {busy ? (
          <span
            className="spinner-border flex-shrink-0"
            style={{ width: 16, height: 16, borderWidth: 2 }}
            aria-hidden="true"
          />
        ) : (
          <img
            src={photo_url}
            alt=""
            width={16}
            height={16}
            className="rounded-circle"
          />
        )}
        Ask Gooey to fix
      </button>
    </div>
  );
}
