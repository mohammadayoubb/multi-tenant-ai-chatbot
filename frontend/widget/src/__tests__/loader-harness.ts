// Owner: Amer
// Test harness for frontend/widget/public/widget.js.
//
// Reads the shipping loader source from disk so tests cannot pass against a
// stale or cached copy. Evaluates the loader inside vitest's jsdom document
// with document.currentScript wired to a fake <script> element carrying the
// requested data-* attributes.
import fs from "node:fs";
import path from "node:path";
import { vi } from "vitest";

const LOADER_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "public",
  "widget.js",
);

export function loadLoaderSource(): string {
  return fs.readFileSync(LOADER_PATH, "utf-8");
}

const HOST_TEST_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "public",
  "host-test.html",
);

export function loadHostTestSource(): string {
  return fs.readFileSync(HOST_TEST_PATH, "utf-8");
}

export interface HarnessOptions {
  // null = omit the attribute entirely; "" = present but empty.
  widgetId?: string | null;
  backendUrl?: string;
  scriptSrc?: string;
  mountBody?: boolean;
  setCurrentScript?: boolean;
}

export interface HarnessResult {
  consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  script: HTMLScriptElement;
}

export function evaluateLoader(opts: HarnessOptions = {}): HarnessResult {
  const {
    widgetId = "w_demo",
    backendUrl,
    scriptSrc = "https://platform.example.test/widget.js",
    mountBody = true,
    setCurrentScript = true,
  } = opts;

  if (!mountBody && document.body) {
    document.body.remove();
  }

  const script = document.createElement("script");
  script.src = scriptSrc;
  if (widgetId !== null) {
    script.setAttribute("data-widget-id", widgetId);
  }
  if (backendUrl !== undefined) {
    script.setAttribute("data-backend-url", backendUrl);
  }

  Object.defineProperty(document, "currentScript", {
    configurable: true,
    get: () => (setCurrentScript ? script : null),
  });

  const consoleErrorSpy = vi
    .spyOn(console, "error")
    .mockImplementation(() => {});

  // eslint-disable-next-line no-new-func
  new Function(loadLoaderSource())();

  return { consoleErrorSpy, script };
}

export function restoreBody(): void {
  if (!document.body) {
    const body = document.createElement("body");
    document.documentElement.appendChild(body);
  }
}

export function resetDom(): void {
  restoreBody();
  document.body.innerHTML = "";
  // Clear any custom currentScript getter from prior evaluation.
  try {
    Object.defineProperty(document, "currentScript", {
      configurable: true,
      get: () => null,
    });
  } catch {
    /* ignore — only matters between tests */
  }
}
