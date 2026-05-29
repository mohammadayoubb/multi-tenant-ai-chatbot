// Owner: Amer
// T040 — Quick-action chip rendering + click-to-insert behavior.
//
// Covers spec FR-064 / SC-001:
//   - Agent-config chips render verbatim, max 6.
//   - An empty list renders no chip row at all.
//   - Clicking a chip sends its text as a chat message.

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("US1: quick-action chip rendering", () => {
  it("renders the chip list verbatim from props", () => {
    render(
      <ChatWidget
        backendUrl={BACKEND}
        initiallyOpen={true}
        chips={["View services", "Pricing", "Book appointment", "Talk to human"]}
      />
    );
    const chips = screen.getAllByTestId("quick-action-chip");
    expect(chips).toHaveLength(4);
    expect(chips.map((c) => c.textContent)).toEqual([
      "View services",
      "Pricing",
      "Book appointment",
      "Talk to human",
    ]);
  });

  it("renders no chip row when the chip list is empty", () => {
    render(<ChatWidget backendUrl={BACKEND} initiallyOpen={true} chips={[]} />);
    expect(screen.queryByTestId("quick-actions")).not.toBeInTheDocument();
  });

  it("clicking a chip sends its text as a chat message", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({ answer: "Here are our prices.", route: "agent" }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<ChatWidget backendUrl={BACKEND} initiallyOpen={true} chips={["Pricing"]} />);
    fireEvent.click(screen.getByTestId("quick-action-chip"));

    // The chip's text becomes the user bubble immediately. Scope the query
    // to the user-bubble testid so the chip's own text doesn't satisfy it.
    await waitFor(() => {
      const userBubble = screen.getByTestId("message-bubble--user");
      expect(userBubble.textContent).toBe("Pricing");
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/chat`);
    expect(JSON.parse(init.body as string)).toEqual({
      message: "Pricing",
      session_id: KNOWN_SESSION,
    });
  });

  it("renders the (sample greeting) placeholder note when placeholderConfig is true", () => {
    render(<ChatWidget backendUrl={BACKEND} initiallyOpen={true} chips={[]} placeholderConfig={true} />);
    expect(
      screen.getByTestId("empty-state-placeholder-note")
    ).toBeInTheDocument();
  });

  it("uses the tenant greeting in the empty state when supplied", () => {
    render(
      <ChatWidget
        backendUrl={BACKEND}
        initiallyOpen={true}
        chips={[]}
        greeting="Welcome to Acme!"
      />
    );
    expect(screen.getByText("Welcome to Acme!")).toBeInTheDocument();
  });
});
