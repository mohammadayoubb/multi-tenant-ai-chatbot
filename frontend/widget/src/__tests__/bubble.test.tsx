// Owner: Amer
// T100 — Bubble launcher: initial state shows only the bubble; clicking
// opens the panel; closing returns to the bubble.

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
const KNOWN_TOKEN = "eyJhbGciOiJIUzI1NiJ9.fake.body";
const KNOWN_SESSION = "f1c8d4e2-5a3b-4c7d-8e9f-1a2b3c4d5e6f";

beforeEach(() => {
  __debugSetToken(KNOWN_TOKEN, KNOWN_SESSION);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearToken();
  cleanup();
});

describe("US4: bubble launcher", () => {
  it("renders only the bubble at first mount", () => {
    render(<ChatWidget backendUrl={BACKEND} />);
    expect(screen.getByTestId("widget-bubble")).toBeInTheDocument();
    expect(screen.queryByTestId("widget-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-input-textarea")).not.toBeInTheDocument();
  });

  it("clicking the bubble opens the panel", () => {
    render(<ChatWidget backendUrl={BACKEND} />);
    fireEvent.click(screen.getByTestId("widget-bubble"));
    expect(screen.getByTestId("widget-panel")).toBeInTheDocument();
    expect(screen.getByTestId("chat-input-textarea")).toBeInTheDocument();
    expect(screen.queryByTestId("widget-bubble")).not.toBeInTheDocument();
  });

  it("clicking close returns to the bubble", () => {
    render(<ChatWidget backendUrl={BACKEND} />);
    fireEvent.click(screen.getByTestId("widget-bubble"));
    fireEvent.click(screen.getByTestId("widget-close"));
    expect(screen.getByTestId("widget-bubble")).toBeInTheDocument();
    expect(screen.queryByTestId("widget-panel")).not.toBeInTheDocument();
  });
});
