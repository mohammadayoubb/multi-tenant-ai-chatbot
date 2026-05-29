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
const OPEN_SIZE = { width: 380, height: 560 };
const MOBILE_BREAKPOINT = 640;

function postSize(open: boolean): void {
  if (typeof window === "undefined" || !window.parent) return;
  const isMobile = window.innerWidth < MOBILE_BREAKPOINT;
  if (open && isMobile) {
    window.parent.postMessage(
      {
        type: "concierge.widget.resize",
        mode: "mobile",
        width: window.innerWidth,
        height: window.innerHeight,
      },
      "*"
    );
    return;
  }
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

  // US1 / T051: chat history is page-lifetime only (FR-070). Reset on
  // page hide and on visibilitychange→hidden so a tab switch + return is
  // safe but a refresh or navigation discards the conversation.
  useEffect(() => {
    function onVisibility(): void {
      if (document.visibilityState === "hidden") {
        reset();
      }
    }
    function onPageHide(): void {
      reset();
    }
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
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
