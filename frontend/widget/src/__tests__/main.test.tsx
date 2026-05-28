// Owner: Amer
// Widget bootstrap tests covering direct-open localhost mode and iframe boot.

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    exchangeToken: vi.fn(),
  };
});

import { exchangeToken } from "../api";
import { LOCAL_DEMO_WIDGET_ID, WidgetApp } from "../main";

const TOKEN_RESPONSE = {
  token: "token-123",
  expires_in: 900,
  session_id: "session-123",
};

const originalParentDescriptor = Object.getOwnPropertyDescriptor(window, "parent");

function setParent(value: unknown): void {
  Object.defineProperty(window, "parent", {
    configurable: true,
    value,
  });
}

function restoreParent(): void {
  if (originalParentDescriptor) {
    Object.defineProperty(window, "parent", originalParentDescriptor);
    return;
  }

  setParent(window);
}

function dispatchHostOrigin(origin: string, source: unknown): void {
  const event = new MessageEvent("message", {
    data: {
      type: "concierge.widget.host_origin",
      origin,
    },
  });

  Object.defineProperty(event, "source", {
    configurable: true,
    value: source,
  });

  window.dispatchEvent(event);
}

beforeEach(() => {
  vi.mocked(exchangeToken).mockResolvedValue(TOKEN_RESPONSE);
  window.history.replaceState({}, "", "/");
  restoreParent();
});

afterEach(() => {
  cleanup();
  vi.mocked(exchangeToken).mockReset();
  window.history.replaceState({}, "", "/");
  restoreParent();
});

describe("widget bootstrap", () => {
  it("uses the local demo widget id when opened directly on localhost", async () => {
    render(<WidgetApp />);

    await waitFor(() =>
      expect(exchangeToken).toHaveBeenCalledWith(
        window.location.origin,
        LOCAL_DEMO_WIDGET_ID
      )
    );
    expect(await screen.findByText("Visitor support desk")).toBeInTheDocument();
  });

  it("starts the session while embedded without waiting for a host-origin message", async () => {
    const hostWindow = { postMessage: vi.fn() };
    setParent(hostWindow);
    window.history.replaceState({}, "", "/?widget_id=widget-123");

    render(<WidgetApp />);

    await waitFor(() =>
      expect(exchangeToken).toHaveBeenCalledWith(
        window.location.origin,
        "widget-123"
      )
    );
    expect(await screen.findByText("Visitor support desk")).toBeInTheDocument();
    expect(hostWindow.postMessage).not.toHaveBeenCalled();
  });

  it("notifies the host after the widget is ready and the host origin arrives", async () => {
    const hostWindow = { postMessage: vi.fn() };
    setParent(hostWindow);
    window.history.replaceState({}, "", "/?widget_id=widget-123");

    render(<WidgetApp />);

    await screen.findByText("Visitor support desk");

    dispatchHostOrigin("https://customer-site.example", hostWindow);

    await waitFor(() =>
      expect(hostWindow.postMessage).toHaveBeenCalledWith(
        { type: "concierge.widget.ready" },
        "https://customer-site.example"
      )
    );
  });
});
