// Owner: Amer
// Vitest cases for frontend/widget/public/widget.js.
//
// Contract: specs/003-widget-loader-hardening/contracts/widget-loader.md
// Each clause C1..C8 is exercised by one or more cases below.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  evaluateLoader,
  loadHostTestSource,
  loadLoaderSource,
  resetDom,
} from "./loader-harness";

function widgetIframes(widgetId?: string): HTMLIFrameElement[] {
  const selector =
    widgetId === undefined
      ? "iframe[data-concierge-widget-id]"
      : `iframe[data-concierge-widget-id="${widgetId}"]`;
  return Array.from(document.querySelectorAll<HTMLIFrameElement>(selector));
}

beforeEach(() => {
  resetDom();
});

afterEach(() => {
  vi.restoreAllMocks();
  resetDom();
});

describe("loader: input attributes (C1)", () => {
  it("reads data-backend-url from the script tag", () => {
    evaluateLoader({
      widgetId: "w_demo",
      backendUrl: "https://api.example.com",
    });
    const [iframe] = widgetIframes("w_demo");
    expect(iframe).toBeDefined();
    expect(iframe.src.startsWith("https://api.example.com/")).toBe(true);
  });

  it("defaults backend to script tag origin when data-backend-url is absent", () => {
    evaluateLoader({
      widgetId: "w_demo",
      scriptSrc: "https://platform.example.test/widget.js",
    });
    const [iframe] = widgetIframes("w_demo");
    expect(iframe).toBeDefined();
    expect(iframe.src.startsWith("https://platform.example.test/")).toBe(true);
  });
});

describe("loader: hardcoded-host audit (FR-003, SC-006)", () => {
  it("loader source contains no hardcoded localhost or :5173", () => {
    const source = loadLoaderSource();
    expect(source).not.toMatch(/localhost/);
    expect(source).not.toMatch(/:5173/);
    expect(source).not.toMatch(/127\.0\.0\.1/);
  });
});

describe("loader: iframe handshake", () => {
  it("posts the host origin to the iframe using the iframe origin", () => {
    evaluateLoader({
      widgetId: "w_demo",
      backendUrl: "https://api.example.com",
    });
    const [iframe] = widgetIframes("w_demo");
    const postMessage = vi.fn();

    Object.defineProperty(iframe, "contentWindow", {
      configurable: true,
      value: { postMessage },
    });

    iframe.dispatchEvent(new Event("load"));

    expect(postMessage).toHaveBeenCalledWith(
      {
        type: "concierge.widget.host_origin",
        origin: window.location.origin,
      },
      "https://api.example.com",
    );
  });
});

describe("loader: hardened iframe attributes (C3)", () => {
  it("applies hardened iframe attributes", () => {
    evaluateLoader({
      widgetId: "w_demo",
      backendUrl: "https://api.example.com",
    });
    const [iframe] = widgetIframes("w_demo");
    expect(iframe).toBeDefined();
    expect(iframe.getAttribute("title")).toBe("Concierge chat widget");
    expect(iframe.getAttribute("referrerpolicy")).toBe(
      "no-referrer-when-downgrade",
    );
    const sandboxTokens = (iframe.getAttribute("sandbox") ?? "")
      .split(/\s+/)
      .filter(Boolean)
      .sort();
    expect(sandboxTokens).toEqual(
      ["allow-forms", "allow-same-origin", "allow-scripts"].sort(),
    );
  });

  it("iframe src encodes widget_id", () => {
    evaluateLoader({
      widgetId: "w demo & co",
      backendUrl: "https://api.example.com",
    });
    const [iframe] = widgetIframes("w demo & co");
    expect(iframe).toBeDefined();
    expect(iframe.src).toContain("widget_id=w%20demo%20%26%20co");
  });
});

describe("loader: idempotency (C2, FR-007, FR-013)", () => {
  it("is idempotent for the same widget id", () => {
    evaluateLoader({
      widgetId: "w_demo",
      backendUrl: "https://api.example.com",
    });
    evaluateLoader({
      widgetId: "w_demo",
      backendUrl: "https://api.example.com",
    });
    expect(widgetIframes("w_demo")).toHaveLength(1);
  });

  it("mounts two iframes for two different widget ids", () => {
    evaluateLoader({
      widgetId: "w_a",
      backendUrl: "https://api.example.com",
    });
    evaluateLoader({
      widgetId: "w_b",
      backendUrl: "https://api.example.com",
    });
    expect(widgetIframes("w_a")).toHaveLength(1);
    expect(widgetIframes("w_b")).toHaveLength(1);
    expect(widgetIframes()).toHaveLength(2);
  });
});

describe("loader: fail-soft (C4, FR-008, FR-009)", () => {
  it("logs one console.error and does not throw when data-widget-id is missing", () => {
    const { consoleErrorSpy } = evaluateLoader({ widgetId: null });
    expect(widgetIframes()).toHaveLength(0);
    expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
  });

  it("logs one console.error and does not throw when data-widget-id is empty", () => {
    const { consoleErrorSpy: spy1 } = evaluateLoader({ widgetId: "" });
    expect(widgetIframes()).toHaveLength(0);
    expect(spy1).toHaveBeenCalledTimes(1);

    resetDom();

    const { consoleErrorSpy: spy2 } = evaluateLoader({ widgetId: "   " });
    expect(widgetIframes()).toHaveLength(0);
    expect(spy2).toHaveBeenCalledTimes(1);
  });

  it("does not throw when currentScript is null", () => {
    expect(() =>
      evaluateLoader({ setCurrentScript: false }),
    ).not.toThrow();
    expect(widgetIframes()).toHaveLength(0);
  });
});

describe("loader: late-mount (C5)", () => {
  it("defers mount when document.body is not yet present", () => {
    evaluateLoader({
      widgetId: "w_demo",
      backendUrl: "https://api.example.com",
      mountBody: false,
    });

    // Body was removed; loader should not have mounted yet.
    expect(document.body).toBeNull();

    // Re-attach body, then fire DOMContentLoaded; loader should mount now.
    const body = document.createElement("body");
    document.documentElement.appendChild(body);
    document.dispatchEvent(new Event("DOMContentLoaded"));

    expect(widgetIframes("w_demo")).toHaveLength(1);
  });
});

describe("loader: storage abstinence (C7, FR-014, Principle IV)", () => {
  it("loader does not touch localStorage, sessionStorage, or document.cookie", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const removeItem = vi.spyOn(Storage.prototype, "removeItem");

    // Happy path.
    evaluateLoader({
      widgetId: "w_demo",
      backendUrl: "https://api.example.com",
    });
    resetDom();
    // Fail-soft path.
    evaluateLoader({ widgetId: null });

    expect(setItem).not.toHaveBeenCalled();
    expect(getItem).not.toHaveBeenCalled();
    expect(removeItem).not.toHaveBeenCalled();

    const source = loadLoaderSource();
    expect(source).not.toMatch(/localStorage|sessionStorage|document\.cookie/);
  });
});

describe("loader: ES2019 syntax baseline (C8, SC-004)", () => {
  it("loader source contains no post-ES2019 syntax tokens", () => {
    // Forbidden tokens: ??, ?., top-level await, # private fields.
    const source = loadLoaderSource();
    expect(source).not.toMatch(/\?\?/);
    expect(source).not.toMatch(/\?\./);
    expect(source).not.toMatch(/\bawait\s+/);
    expect(source).not.toMatch(/^\s*#[a-zA-Z_]/m);
  });

  it("loader contains no import statements", () => {
    const source = loadLoaderSource();
    expect(source).not.toMatch(/^\s*import\s/m);
    expect(source).not.toMatch(/^\s*from\s+['"]/m);
  });
});

describe("host-test.html: sync with loader contract (T021)", () => {
  it("host-test.html embeds the loader with the demo fixture widget id", () => {
    const html = loadHostTestSource();
    expect(html).toMatch(/<script[^>]+src=["']\/widget\.js["']/);
    expect(html).toMatch(
      /data-widget-id=["']9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d["']/,
    );
  });

  it("host-test.html does not use async on the loader script tag", () => {
    // async classic scripts have document.currentScript === null, which
    // makes the loader fail-soft exit before mounting. The host-test page
    // must use a plain or `defer`d script tag.
    const html = loadHostTestSource();
    const scriptTag = html.match(/<script[^>]*src=["']\/widget\.js["'][^>]*>/);
    expect(scriptTag).not.toBeNull();
    expect(scriptTag![0]).not.toMatch(/\basync\b/);
  });
});
