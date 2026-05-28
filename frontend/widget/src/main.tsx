// Owner: Amer
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { exchangeToken } from "./api";
import { ChatPane } from "./components/ChatPane";
import type { HostOriginMessage } from "./types";
import "./styles.css";

type Status = "waiting_for_host_origin" | "exchanging" | "ready" | "unavailable";

const backendUrl: string = window.location.origin;

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
      .then(() => {
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
        <ChatPane backendUrl={backendUrl} />
      </div>
    );
  }

  return (
    <div className="widget-shell">
      <p>Loading…</p>
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<WidgetApp />);
