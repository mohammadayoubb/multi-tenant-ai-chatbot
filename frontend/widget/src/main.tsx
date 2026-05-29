// Owner: Amer
// Widget entry point. Runs the token-exchange handshake against the host
// origin, then mounts the ChatWidget orchestrator. Phase 2 keeps the panel
// always-open; the bubble launcher (US4 / T105) replaces this with a
// state.open-driven Bubble/Panel switch.

import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { exchangeToken, fetchAgentConfig } from "./api";
import { ChatWidget } from "./ChatWidget";
import type { AgentConfig, HostOriginMessage } from "./types";
import "./styles.css";

type Status = "waiting_for_host_origin" | "exchanging" | "ready" | "unavailable";

const backendUrl: string =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ??
  window.location.origin;

function isHostOriginMessage(value: unknown): value is HostOriginMessage {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { type?: unknown }).type === "concierge.widget.host_origin" &&
    typeof (value as { origin?: unknown }).origin === "string"
  );
}

function WidgetApp(): JSX.Element {
  const [status, setStatus] = useState<Status>("waiting_for_host_origin");
  const [hostOrigin, setHostOrigin] = useState<string | null>(null);
  const [agentConfig, setAgentConfig] = useState<AgentConfig | null>(null);
  const widgetId = new URLSearchParams(window.location.search).get("widget_id");

  useEffect(() => {
    function onMessage(event: MessageEvent): void {
      if (event.source !== window.parent) return;
      if (!isHostOriginMessage(event.data)) return;
      setHostOrigin(event.data.origin);
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    if (!hostOrigin || !widgetId) return;
    setStatus("exchanging");
    exchangeToken(backendUrl, widgetId)
      .then(async () => {
        // Best-effort agent-config load; falls back to placeholder shape
        // on any failure path so the panel always has chips + greeting.
        const cfg = await fetchAgentConfig(backendUrl);
        setAgentConfig(cfg);
        setStatus("ready");
        if (window.parent && hostOrigin) {
          window.parent.postMessage(
            { type: "concierge.widget.ready" },
            hostOrigin
          );
        }
      })
      .catch(() => setStatus("unavailable"));
  }, [hostOrigin, widgetId]);

  if (status === "unavailable") {
    return (
      <div className="widget-shell">
        <p>Widget unavailable</p>
      </div>
    );
  }

  if (status === "ready") {
    return (
      <div className="widget-shell">
        <ChatWidget
          backendUrl={backendUrl}
          chips={agentConfig?.chips ?? []}
          greeting={agentConfig?.greeting}
          placeholderConfig={agentConfig?._placeholder === true}
        />
      </div>
    );
  }

  return (
    <div className="widget-shell">
      <p>Loading…</p>
    </div>
  );
}

const rootEl = document.getElementById("root");
if (rootEl) {
  createRoot(rootEl).render(<WidgetApp />);
}
