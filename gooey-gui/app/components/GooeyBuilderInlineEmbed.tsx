import { useEffect, useRef } from "react";
import { fetchServerAPI } from "~/fetchServerAPI";
import type { CustomComponentProps } from "~/components";
import { useGlobalContext } from "~/globalContext";
import { useAppShellPanelActions } from "~/appShellContext";

declare global {
  interface Window {
    GooeyEmbed?: any;
  }
}

export function GooeyBuilderInlineEmbed(
  props: CustomComponentProps & {
    config: Record<string, any>;
    event_key: string;
    messages?: Record<string, any>[] | null;
    builder_run_url: string;
    workflow_state: Record<string, any>;
    builder_only?: boolean;
    /** Set only for a logged-out visitor: the send endpoint is login-required. */
    login_url?: string | null;
  }
) {
  const { config, messages } = props;
  const propsRef = useRef(props);
  propsRef.current = props;

  const controllerRef = useRef<any>(null);

  const ctx = useGlobalContext();
  const { setPanelOpen } = useAppShellPanelActions();

  useEffect(() => {
    const loadEmbed = () => {
      const GooeyEmbed = window.GooeyEmbed;
      if (!GooeyEmbed) return;

      const embedTarget = document.getElementById("gooey-builder-embed");
      if (embedTarget?.children.length) {
        controllerRef.current?.setMessages?.(messages);
        return;
      }

      // builder-only pages are standalone, so there's no sidebar to close
      if (!propsRef.current.builder_only) {
        config.onClose = function () {
          setPanelOpen(propsRef.current.event_key, false);
          window.dispatchEvent(
            new CustomEvent(`${propsRef.current.event_key}:close`)
          );
        };
      }

      async function sendMessage(input_data: any) {
        // Anonymous: the endpoint is login-required, so the message waits in this tab's
        // storage through login and is sent once the widget mounts on the way back.
        const loginUrl = propsRef.current.login_url;
        if (loginUrl) {
          savePendingPrompt(loginUrl, input_data?.input_prompt);
          window.location.href = loginUrl;
          return;
        }
        let redirectUrl = await fetchServerAPI<string | null>(
          "/__/gooey-builder/send-message",
          {
            // builder-only pages have no associated workflow to clone
            workflow_url: propsRef.current.builder_only
              ? null
              : window.location.href,
            builder_run_url: propsRef.current.builder_run_url,
            workflow_state: propsRef.current.workflow_state,
            input_data,
          }
        );
        if (!redirectUrl) return;
        let url = new URL(redirectUrl);
        ctx.current.navigate(url.pathname + url.search);
      }

      controllerRef.current = {
        messages,
        onSendMessage: sendMessage,
        onEditQuery: (_messageId: string, input_data: any, webUrl?: string) => {
          // webUrl identifies the run that produced the edited turn, so the
          // server re-runs that turn rather than always the latest one
          if (!webUrl) return;
          sendMessage({ ...input_data, edit_run_url: webUrl });
        },
        // same server path as an edit, minus the prompt: the turn is replayed as-is
        rerun: async (webUrl: string) => {
          if (!webUrl) return;
          sendMessage({ edit_run_url: webUrl });
        },
        onNewConversation: async () => {
          ctx.current.update_session_state({ builderOnNewConversation: true });
        },
      };

      GooeyEmbed.mount(config, controllerRef.current);

      // After mount, so the controller exists to take it.
      if (propsRef.current.login_url) return;
      const pending = takePendingPrompt();
      if (pending) sendMessage({ input_prompt: pending });
    };

    const script = document.getElementById("gooey-embed-script");
    script?.addEventListener("load", loadEmbed);
    loadEmbed();

    // v2 hides the widget's header, so the panel's title button fires this instead. Routed
    // through the controller, the same path the widget's own control uses.
    const newConversationEvent = `${propsRef.current.event_key}:new`;
    const onNewConversation = () =>
      controllerRef.current?.onNewConversation?.();
    const rerunEvent = `${propsRef.current.event_key}:rerun`;
    const onRerun = () =>
      controllerRef.current?.rerun?.(propsRef.current.builder_run_url);
    window.addEventListener(newConversationEvent, onNewConversation);
    window.addEventListener(rerunEvent, onRerun);

    return () => {
      script?.removeEventListener("load", loadEmbed);
      window.removeEventListener(newConversationEvent, onNewConversation);
      window.removeEventListener(rerunEvent, onRerun);
    };
  }, []);

  useEffect(() => {
    controllerRef.current?.setMessages?.(messages);
  }, [messages]);

  return <div id="gooey-builder-embed" />;
}

const PENDING_PROMPT_KEY = "gooey:builder-pending-prompt";

/** Keyed to the page login returns to (its `next`), so the message is only sent there. */
function savePendingPrompt(loginUrl: string, prompt: unknown) {
  if (typeof prompt !== "string" || !prompt.trim()) return;
  const next = new URL(loginUrl, window.location.href).searchParams.get("next");
  const path = next
    ? new URL(next, window.location.href).pathname
    : window.location.pathname;
  try {
    sessionStorage.setItem(
      PENDING_PROMPT_KEY,
      JSON.stringify({ path, prompt })
    );
  } catch {
    // storage blocked: login still works, the message is just not replayed
  }
}

/** Cleared once taken, so a reload cannot send it twice; left for its own page otherwise. */
function takePendingPrompt(): string | null {
  try {
    const raw = sessionStorage.getItem(PENDING_PROMPT_KEY);
    if (!raw) return null;
    const { path, prompt } = JSON.parse(raw);
    if (path !== window.location.pathname) return null;
    sessionStorage.removeItem(PENDING_PROMPT_KEY);
    return prompt;
  } catch {
    return null;
  }
}
