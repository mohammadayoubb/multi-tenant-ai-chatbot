// Owner: Amer
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { exchangeToken } from "./api";
import { ChatPane } from "./components/ChatPane";
import { WidgetShellState } from "./components/WidgetShellState";
import type { HostOriginMessage } from "./types";
import "./styles.css";

type Status = "waiting_for_host_origin" | "exchanging" | "ready" | "unavailable";

const backendUrl: string = window.location.origin;
export const LOCAL_DEMO_WIDGET_ID = "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d";

function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

function isValidOrigin(value: string): boolean {
  try {
    return new URL(value).origin === value;
  } catch {
    return false;
  }
}

function isHostOriginMessage(value: unknown): value is HostOriginMessage {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { type?: unknown }).type === "concierge.widget.host_origin" &&
    typeof (value as { origin?: unknown }).origin === "string" &&
    isValidOrigin((value as { origin: string }).origin)
  );
}

export function resolveWidgetId(
  location: Location,
  isTopLevelAccess: boolean
): string | null {
  const widgetId = new URLSearchParams(location.search).get("widget_id")?.trim();
  if (widgetId) {
    return widgetId;
  }

  if (isTopLevelAccess && isLoopbackHost(location.hostname)) {
    // Local direct-open fallback so http://localhost:8000/ boots the fixture widget.
    return LOCAL_DEMO_WIDGET_ID;
  }

  return null;
}

export function WidgetApp(): JSX.Element {
  const isTopLevelAccess = window.parent === window;
  const widgetId = resolveWidgetId(window.location, isTopLevelAccess);
  const [status, setStatus] = useState<Status>(() =>
    widgetId === null ? "unavailable" : "exchanging"
  );
  const [hostOrigin, setHostOrigin] = useState<string | null>(() =>
    isTopLevelAccess ? window.location.origin : null
  );

  useEffect(() => {
    if (isTopLevelAccess) {
      return;
    }

    function onMessage(event: MessageEvent): void {
      if (event.source !== window.parent) return;
      if (!isHostOriginMessage(event.data)) return;
      setHostOrigin(event.data.origin);
    }

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [isTopLevelAccess]);

  useEffect(() => {
    if (!widgetId) {
      return;
    }

    let cancelled = false;
    exchangeToken(backendUrl, widgetId)
      .then(() => {
        if (cancelled) {
          return;
        }
        setStatus("ready");
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setStatus("unavailable");
      });

    return () => {
      cancelled = true;
    };
  }, [widgetId]);

  useEffect(() => {
    if (status !== "ready" || isTopLevelAccess || !hostOrigin) {
      return;
    }

    window.parent.postMessage({ type: "concierge.widget.ready" }, hostOrigin);
  }, [hostOrigin, isTopLevelAccess, status]);

  if (status === "unavailable") {
    const missingWidgetId = widgetId === null;
    return (
      <WidgetShellState
        eyebrow={missingWidgetId ? "Widget setup" : "Session setup"}
        title={missingWidgetId ? "Widget not configured" : "Widget unavailable"}
        body={
          missingWidgetId
            ? "Open this widget through the loader script, or add a widget_id query parameter."
            : "We could not start the assistant right now. Refresh the page or try again in a moment."
        }
        tone="warning"
      />
    );
  }

  if (status === "ready") {
    return (
      <div className="widget-shell">
        <ChatPane backendUrl={backendUrl} />
      </div>
    );
  }

  return (
    <WidgetShellState
      eyebrow="Starting secure chat"
      title="Loading..."
      body="Preparing your tenant-scoped assistant session."
    />
  );
}

const rootElement = document.getElementById("root");
if (rootElement) {
  createRoot(rootElement).render(<WidgetApp />);
}
