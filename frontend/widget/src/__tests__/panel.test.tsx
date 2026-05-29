// Owner: Amer
// T101 — Panel dialog semantics + focus trap + ESC handling.
//
// Verifies:
//   - role="dialog" and aria-modal="true" are present on the panel.
//   - aria-labelledby points at the rendered header title.
//   - Tab past the last focusable child wraps to the first; Shift+Tab from
//     the first wraps to the last.
//   - ESC inside the panel triggers close (returning to the bubble).

import React from "react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ChatWidget } from "../ChatWidget";
import { __debugSetToken, clearToken } from "../api";

const BACKEND = "http://localhost:8000";
const TOKEN = "eyJhbGciOiJIUzI1NiJ9.fake.body";
const SESSION = "f1c8d4e2-5a3b-4c7d-8e9f-1a2b3c4d5e6f";

beforeEach(() => {
  __debugSetToken(TOKEN, SESSION);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearToken();
  cleanup();
});

describe("US4: panel dialog semantics", () => {
  it("renders role=dialog + aria-modal=true + aria-labelledby on the panel", () => {
    render(<ChatWidget backendUrl={BACKEND} initiallyOpen={true} />);
    const panel = screen.getByTestId("widget-panel");
    expect(panel.getAttribute("role")).toBe("dialog");
    expect(panel.getAttribute("aria-modal")).toBe("true");
    const titleId = panel.getAttribute("aria-labelledby");
    expect(titleId).toBeTruthy();
    expect(document.getElementById(titleId as string)).not.toBeNull();
  });

  it("focus trap wraps Tab from last → first and Shift+Tab from first → last", () => {
    render(
      <ChatWidget
        backendUrl={BACKEND}
        initiallyOpen={true}
        chips={["pick-me"]}
      />
    );

    const trap = screen.getByTestId("focus-trap");
    const focusables = Array.from(
      trap.querySelectorAll<HTMLElement>(
        "a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])"
      )
    );
    expect(focusables.length).toBeGreaterThanOrEqual(2);
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    // Forward wrap: focus the last, press Tab → wraps to first.
    last.focus();
    expect(document.activeElement).toBe(last);
    fireEvent.keyDown(trap, { key: "Tab" });
    expect(document.activeElement).toBe(first);

    // Backward wrap: focus the first, press Shift+Tab → wraps to last.
    first.focus();
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(trap, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("ESC closes the panel and returns to the bubble", () => {
    render(<ChatWidget backendUrl={BACKEND} initiallyOpen={true} />);
    const trap = screen.getByTestId("focus-trap");
    fireEvent.keyDown(trap, { key: "Escape" });
    expect(screen.queryByTestId("widget-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("widget-bubble")).toBeInTheDocument();
  });
});
