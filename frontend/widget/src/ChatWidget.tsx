// Owner: Amer
// Thin orchestrator for the widget chat surface. US4 (T105) flips this
// from always-open to a bubble launcher: state.open === false renders
// <Bubble/>, state.open === true renders <Panel/>. Iframe size is
// negotiated with the host loader via postMessage (T106).

import React, { useEffect, useRef } from "react";
import { Bubble } from "./components/Bubble";
import { ChatInput } from "./components/ChatInput";
import { EmptyState } from "./components/EmptyState";
import { Message } from "./components/Message";
import { Panel } from "./components/Panel";
import { QuickActions } from "./components/QuickActions";
import { StatusBanner } from "./components/StatusBanner";
import { useChatReducer } from "./state/useChatReducer";
import { resolveAccentColor } from "./theme";

interface ChatWidgetProps {
  backendUrl?: string;
  chips?: string[];
  greeting?: string;
  themeColor?: string;
  placeholderConfig?: boolean;
  // Test seam — production renders bubble-first; tests that exercise the
  // panel surface pass `initiallyOpen` to skip the bubble click.
  initiallyOpen?: boolean;
}

const defaultBackendUrl = (): string => window.location.origin;

const COLLAPSED_SIZE = { width: 80, height: 80 };
const OPEN_SIZE = { width: 360, height: 540 };

// Note: mobile detection lives in the loader (widget.js), NOT here.
// `window.innerWidth` read inside the iframe returns the iframe's own width
// (e.g. 80px when collapsed), not the host page's viewport — so any mobile
// check made here would always be true and trigger fullscreen mode on
// desktop hosts. The loader has access to the real host viewport and
// decides mobile vs desktop after receiving "open".
function postSize(open: boolean): void {
  if (typeof window === "undefined" || !window.parent) return;
  const size = open ? OPEN_SIZE : COLLAPSED_SIZE;
  window.parent.postMessage(
    {
      type: "concierge.widget.resize",
      mode: open ? "open" : "collapsed",
      width: size.width,
      height: size.height,
    },
    "*"
  );
}

export function ChatWidget({
  backendUrl,
  chips = [],
  greeting,
  themeColor,
  placeholderConfig = false,
  initiallyOpen = false,
}: ChatWidgetProps): JSX.Element {
  const resolvedBackendUrl = backendUrl ?? defaultBackendUrl();
  const { state, open, close, send, retry, reset } =
    useChatReducer(resolvedBackendUrl, initiallyOpen);
  const listRef = useRef<HTMLDivElement | null>(null);
  const accentColor = resolveAccentColor(themeColor);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.messages.length, state.status]);

  useEffect(() => {
    postSize(state.open);
  }, [state.open]);

  // Short-term memory: messages persist for the tab's lifetime. `pagehide`
  // (full navigation / tab close) still clears UI state — the conversation
  // discards there because the new session_id on reload can't reach the old
  // Redis key. Earlier behavior also reset on visibilitychange→hidden which
  // wiped history on tab-switch; that's now relaxed so the conversation
  // survives tab switches and minimize/restore. Backend Redis memory already
  // keeps the last 12 redacted turns under session:{tenant_id}:{session_id}
  // with a TTL — the agent sees that on every request.
  useEffect(() => {
    function onPageHide(): void {
      reset();
    }
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
    };
  }, [reset]);

  if (!state.open) {
    return <Bubble onClick={open} themeColor={accentColor} />;
  }

  return (
    <Panel themeColor={themeColor} onClose={close}>
      <div
        ref={listRef}
        className="message-list"
        data-testid="message-list"
        aria-live="polite"
        aria-relevant="additions"
      >
        {state.messages.length === 0 && state.status !== "sending" && (
          <EmptyState
            title={greeting ?? undefined}
            placeholder={placeholderConfig}
          />
        )}
        {state.messages.map((m) => (
          <Message key={m.id} message={m} />
        ))}
        {state.status === "sending" && (
          <div className="message-loading" data-testid="loading-indicator">
            <span />
          </div>
        )}
      </div>

      <StatusBanner
        status={state.status}
        onRetry={() => {
          void retry();
        }}
      />

      <QuickActions
        chips={chips}
        disabled={state.status === "sending" || state.status === "expired"}
        onPick={(text) => {
          void send(text);
        }}
      />

      <ChatInput
        disabled={state.status === "sending" || state.status === "expired"}
        onSubmit={(text) => {
          void send(text);
        }}
      />
    </Panel>
  );
}
