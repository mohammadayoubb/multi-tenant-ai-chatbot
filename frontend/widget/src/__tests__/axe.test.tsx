// Owner: Amer
// T103 — Axe-core accessibility scan.
//
// Mounts the ChatWidget in both closed (bubble-only) and open (panel)
// states and asserts zero `serious` or `critical` violations. `minor` /
// `moderate` violations are logged but don't fail (Streamlit-style DOM
// noise — see research R7 threshold note).

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
import axe from "axe-core";
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

function seriousOrCritical(
  violations: Array<{ id: string; impact?: string | null }>
): Array<{ id: string; impact?: string | null }> {
  return violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
}

describe("US4: axe-core scan (SC-005)", () => {
  it("closed (bubble-only) has zero serious/critical violations", async () => {
    const { container } = render(<ChatWidget backendUrl={BACKEND} />);
    const result = await axe.run(container);
    const hard = seriousOrCritical(result.violations);
    expect(hard).toEqual([]);
  });

  it("open (panel) has zero serious/critical violations", async () => {
    const { container } = render(
      <ChatWidget backendUrl={BACKEND} initiallyOpen={true} chips={["Pricing"]} />
    );
    // Confirm panel is mounted.
    expect(screen.getByTestId("widget-panel")).toBeInTheDocument();
    const result = await axe.run(container);
    const hard = seriousOrCritical(result.violations);
    expect(hard).toEqual([]);
  });
});
