// Owner: Amer
// T045b — SC-001 first-feedback budget.
//
// When /chat takes 500ms to respond, the user bubble + a loading indicator
// MUST appear synchronously (well before the response resolves). This is the
// regression net for spec SC-001 ("first feedback ≤200ms after send").

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

describe("US1: first-feedback budget (SC-001)", () => {
  it("renders the user bubble + loading indicator before the 500ms reply resolves", async () => {
    let resolveFn: (r: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      resolveFn = resolve;
    });
    const fetchMock = vi.fn(async () => pending);
    vi.stubGlobal("fetch", fetchMock);

    render(<ChatWidget backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea");
    fireEvent.change(input, { target: { value: "ping" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // Both must already be on screen synchronously — no awaits between send
    // and these assertions. The fetch promise is still unresolved.
    expect(screen.getByText("ping")).toBeInTheDocument();
    expect(screen.getByTestId("loading-indicator")).toBeInTheDocument();

    // Now resolve so the test cleans up; no further assertions required.
    resolveFn(
      new Response(JSON.stringify({ answer: "pong", route: "agent" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    await screen.findByText("pong");
  });
});
