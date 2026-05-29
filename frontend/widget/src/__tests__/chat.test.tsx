// Owner: Amer
// Component tests for the widget chat UI (Phase 2).
//
// Covers US1 (happy path), US2 (graceful failure), US3 (privacy / ephemerality)
// from specs/002-widget-chat-ui/spec.md. Maps to T006–T009, T016–T021, T029–T030.

import React from "react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { ChatWidget as ChatPane } from "../ChatWidget";
import { __debugSetToken, clearToken } from "../api";

const BACKEND = "http://localhost:8000";
const KNOWN_TOKEN = "eyJhbGciOiJIUzI1NiJ9.fake.body";
const KNOWN_SESSION = "f1c8d4e2-5a3b-4c7d-8e9f-1a2b3c4d5e6f";

function mockFetchOnce(response: unknown, init: { ok?: boolean; status?: number } = {}) {
  const fetchMock = vi.fn(async () => {
    return new Response(JSON.stringify(response), {
      status: init.status ?? (init.ok === false ? 500 : 200),
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function mockFetchSequence(responders: Array<() => Response | Promise<Response>>) {
  let i = 0;
  const fetchMock = vi.fn(async () => {
    const r = responders[i] ?? responders[responders.length - 1];
    i += 1;
    return r();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function networkErrorFetch() {
  const fetchMock = vi.fn(async () => {
    throw new TypeError("network error");
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  __debugSetToken(KNOWN_TOKEN, KNOWN_SESSION);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearToken();
  cleanup();
});

// =====================================================
// US1 — Visitor sends a message and gets an answer
// =====================================================

describe("US1: happy path", () => {
  it("sends with Authorization header and renders both bubbles", async () => {
    const fetchMock = mockFetchOnce({
      answer: "We're open 9-5",
      route: "agent",
      used_tools: ["rag_search"],
      citations: [],
      ticket_id: null,
    });

    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea");
    fireEvent.change(input, { target: { value: "What are your hours?" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // User bubble appears immediately.
    expect(screen.getByText("What are your hours?")).toBeInTheDocument();

    // Assistant bubble after the mock resolves.
    await screen.findByText("We're open 9-5");

    // One fetch with the expected URL, method, headers, body.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BACKEND}/chat`);
    expect(init.method).toBe("POST");
    const headers = init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe(`Bearer ${KNOWN_TOKEN}`);
    expect(headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({
      message: "What are your hours?",
      session_id: KNOWN_SESSION,
    });
  });

  it("Shift+Enter inserts a newline; empty input does nothing", () => {
    const fetchMock = mockFetchOnce({ answer: "ok", route: "agent" });
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea") as HTMLTextAreaElement;

    // Empty input + Enter: no fetch.
    fireEvent.keyDown(input, { key: "Enter" });
    expect(fetchMock).not.toHaveBeenCalled();

    // Whitespace-only input + Enter: no fetch.
    fireEvent.change(input, { target: { value: "   \n  " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(fetchMock).not.toHaveBeenCalled();

    // Shift+Enter: the keydown is not preventDefault'd; no fetch dispatched.
    fireEvent.change(input, { target: { value: "first line" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("single-in-flight: rapid Enter presses fire one fetch", async () => {
    let resolveFn: ((r: Response) => void) | null = null;
    const pending = new Promise<Response>((resolve) => {
      resolveFn = resolve;
    });
    const fetchMock = vi.fn(async () => pending);
    vi.stubGlobal("fetch", fetchMock);

    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea");
    fireEvent.change(input, { target: { value: "test" } });
    fireEvent.keyDown(input, { key: "Enter" });
    // Try to send again while the first is in flight.
    fireEvent.change(input, { target: { value: "test 2" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Resolve so the React tree can complete; not strictly needed but cleaner.
    resolveFn?.(jsonResponse({ answer: "ok", route: "agent" }));
  });

  it("auto-scroll: scrollTop is set to scrollHeight after a new message", async () => {
    mockFetchOnce({ answer: "ok", route: "agent" });
    const { container } = render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);

    const list = container.querySelector(".message-list") as HTMLDivElement;
    // jsdom defaults scrollHeight to 0; stub it so the effect's assignment is observable.
    Object.defineProperty(list, "scrollHeight", { configurable: true, value: 999 });

    const input = screen.getByTestId("chat-input-textarea");
    fireEvent.change(input, { target: { value: "scroll me" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await screen.findByText("ok");
    expect(list.scrollTop).toBe(999);
  });
});

// =====================================================
// US2 — Graceful failure handling
// =====================================================

describe("US2: 401 → terminal expired state", () => {
  it("shows Session expired and disables input; no retry", async () => {
    const fetchMock = mockFetchSequence([
      () => jsonResponse({ detail: "Token expired" }, 401),
    ]);
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await screen.findByText("Session expired, please reload");
    expect(input).toBeDisabled();
    // No retry button is rendered.
    expect(screen.queryByTestId("retry-button")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("US2: 5xx + retry", () => {
  it("shows retry banner, retry sends exactly one user + one assistant bubble", async () => {
    const fetchMock = mockFetchSequence([
      () => jsonResponse({ detail: "Internal Server Error" }, 500),
      () => jsonResponse({ answer: "We're open 9-5", route: "agent" }, 200),
    ]);
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea");
    fireEvent.change(input, { target: { value: "test 500" } });
    fireEvent.keyDown(input, { key: "Enter" });

    const retry = await screen.findByTestId("retry-button");
    expect(retry).toBeInTheDocument();
    // User bubble is still visible while the banner is up.
    expect(screen.getByText("test 500")).toBeInTheDocument();

    fireEvent.click(retry);
    await screen.findByText("We're open 9-5");

    // Exactly one user bubble and one assistant bubble for the logical exchange.
    expect(screen.getAllByTestId("message-bubble--user")).toHaveLength(1);
    expect(screen.getAllByTestId("message-bubble--assistant")).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("US2: network failure + retry", () => {
  it("shows retry banner; banner copy contains no HTTP codes or stack frames", async () => {
    // First call rejects with network error; second succeeds.
    let i = 0;
    const fetchMock = vi.fn(async () => {
      if (i === 0) {
        i += 1;
        throw new TypeError("Failed to fetch");
      }
      i += 1;
      return jsonResponse({ answer: "ok", route: "agent" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea");
    fireEvent.change(input, { target: { value: "test network" } });
    fireEvent.keyDown(input, { key: "Enter" });

    const banner = await screen.findByRole("alert");
    const bannerText = banner.textContent ?? "";
    // No HTTP codes in the banner text.
    expect(bannerText).not.toMatch(/\b[1-5]\d{2}\b/);
    // No stack-trace tokens.
    expect(bannerText).not.toContain(".js:");
    expect(bannerText).not.toContain(" at ");
    // Banner contains the friendly copy.
    expect(bannerText).toContain("Couldn");

    fireEvent.click(within(banner).getByTestId("retry-button"));
    await screen.findByText("ok");
  });
});

describe("US2: defensive parse sweep (SC-002)", () => {
  const malformedShapes = [
    // Missing required fields (router will throw → error banner).
    { route: "agent" }, // missing answer
    { answer: "a" }, // missing route
    // Required present, optionals missing/wrong-type (must render the reply).
    { answer: "ok 1", route: "agent" },
    { answer: "ok 2", route: "agent", used_tools: null },
    { answer: "ok 3", route: "agent", used_tools: "not an array" },
    { answer: "ok 4", route: "agent", citations: null },
    { answer: "ok 5", route: "agent", citations: "not an array" },
    { answer: "ok 6", route: "agent", ticket_id: null },
    { answer: "ok 7", route: "agent", ticket_id: "" },
    { answer: "ok 8", route: "agent", extraKey: "ignored" },
    { answer: "ok 9", route: "agent", used_tools: ["x", 1, null] },
    { answer: "ok 10", route: "agent", ticket_id: 12345 },
    { answer: "ok 11", route: "workflow" },
    { answer: "ok 12", route: "blocked" },
  ];

  it.each(malformedShapes)("renders or fails-safe for shape %j", async (shape) => {
    mockFetchOnce(shape);
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea");
    fireEvent.change(input, { target: { value: "probe" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // Either the assistant bubble appears (if required fields present) OR
    // the retry banner appears (if a required field was missing). The UI
    // MUST NOT crash and MUST NOT show raw error details.
    await waitFor(() => {
      const assistant = screen.queryByTestId("message-bubble--assistant");
      const alert = screen.queryByRole("alert");
      expect(assistant !== null || alert !== null).toBe(true);
    });

    if (typeof shape.answer === "string" && typeof shape.route === "string") {
      // Required fields present → assistant bubble must render with the answer text.
      expect(screen.getByText(shape.answer)).toBeInTheDocument();
    }
  });
});

describe("US2: route mapping", () => {
  it("escalate + ticket_id shows pill", async () => {
    mockFetchOnce({ answer: "Connecting…", route: "escalate", ticket_id: "abc-123" });
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    fireEvent.change(screen.getByTestId("chat-input-textarea"), {
      target: { value: "help" },
    });
    fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
    await screen.findByText("Connecting…");
    const pill = screen.getByTestId("ticket-pill");
    expect(pill.textContent).toBe("Ticket #abc-123");
  });

  it("escalate without ticket_id suppresses pill", async () => {
    mockFetchOnce({ answer: "Connecting…", route: "escalate", ticket_id: null });
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    fireEvent.change(screen.getByTestId("chat-input-textarea"), {
      target: { value: "help" },
    });
    fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
    await screen.findByText("Connecting…");
    expect(screen.queryByTestId("ticket-pill")).not.toBeInTheDocument();
  });

  it.each(["workflow", "agent", "blocked", "future_route_v3"])(
    "%s renders normally, no pill",
    async (route) => {
      mockFetchOnce({ answer: `Reply via ${route}`, route });
      render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
      fireEvent.change(screen.getByTestId("chat-input-textarea"), {
        target: { value: "x" },
      });
      fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
      await screen.findByText(`Reply via ${route}`);
      expect(screen.queryByTestId("ticket-pill")).not.toBeInTheDocument();
    }
  );
});

describe("US2: no raw codes or tokens in any visible UI", () => {
  it("error banner contains no HTTP code, no token, no stack frame", async () => {
    mockFetchSequence([() => jsonResponse({ detail: "boom" }, 500)]);
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    // Use a message that doesn't itself contain HTTP-code-shaped text.
    fireEvent.change(screen.getByTestId("chat-input-textarea"), {
      target: { value: "hello" },
    });
    fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
    const banner = await screen.findByRole("alert");
    const bannerText = banner.textContent ?? "";
    // FR-017: no HTTP code, no raw response body, no stack frame, no token.
    expect(bannerText).not.toContain(KNOWN_TOKEN);
    expect(bannerText).not.toMatch(/\b[1-5]\d{2}\b/); // any HTTP code
    expect(bannerText).not.toContain("Internal Server Error");
    expect(bannerText).not.toContain(".js:");
  });
});

// =====================================================
// US3 — Privacy + ephemerality
// =====================================================

describe("US3: browser storage discipline (SC-005)", () => {
  it("after several messages, no token / session_id / chat content lands in storage", async () => {
    const replies = [
      { answer: "reply 1", route: "agent" },
      { answer: "reply 2", route: "agent" },
      { answer: "reply 3", route: "escalate", ticket_id: "t-1" },
      { answer: "reply 4", route: "future_route" },
    ];
    mockFetchSequence(replies.map((r) => () => jsonResponse(r)));
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea");

    for (let i = 0; i < replies.length; i += 1) {
      fireEvent.change(input, { target: { value: `msg ${i + 1}` } });
      fireEvent.keyDown(input, { key: "Enter" });
      await screen.findByText(replies[i].answer);
    }

    const forbidden = [
      KNOWN_TOKEN,
      KNOWN_SESSION,
      "msg 1",
      "msg 2",
      "reply 1",
      "reply 2",
      "t-1",
    ];

    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i) ?? "";
      const value = localStorage.getItem(key) ?? "";
      forbidden.forEach((needle) => {
        expect(key).not.toContain(needle);
        expect(value).not.toContain(needle);
      });
    }
    expect(localStorage.length).toBe(0);

    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i) ?? "";
      const value = sessionStorage.getItem(key) ?? "";
      forbidden.forEach((needle) => {
        expect(key).not.toContain(needle);
        expect(value).not.toContain(needle);
      });
    }
    expect(sessionStorage.length).toBe(0);

    forbidden.forEach((needle) => {
      expect(document.cookie).not.toContain(needle);
    });
  });
});

// =====================================================
// US1 — Citation chips (T041)
// =====================================================

describe("US1: citation chips render with clickable links", () => {
  it("renders one chip per citation with target=_blank and rel=noopener noreferrer", async () => {
    mockFetchOnce({
      answer: "Our pricing is on the website.",
      route: "agent",
      citations: [
        { title: "Pricing FAQ", url: "https://example.com/pricing" },
        { title: "Plans Overview", url: "https://example.com/plans" },
      ],
    });
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    fireEvent.change(screen.getByTestId("chat-input-textarea"), {
      target: { value: "How much?" },
    });
    fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
    await screen.findByText("Our pricing is on the website.");

    const chips = screen.getAllByTestId("citation-chip");
    expect(chips).toHaveLength(2);
    expect(chips[0].tagName).toBe("A");
    expect(chips[0].getAttribute("href")).toBe("https://example.com/pricing");
    expect(chips[0].getAttribute("target")).toBe("_blank");
    expect(chips[0].getAttribute("rel")).toBe("noopener noreferrer");
    expect(chips[0].textContent).toBe("Pricing FAQ");
  });

  it("falls back to 'Source' label when title is missing", async () => {
    mockFetchOnce({
      answer: "See here.",
      route: "agent",
      citations: [{ url: "https://example.com/faq" }],
    });
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    fireEvent.change(screen.getByTestId("chat-input-textarea"), {
      target: { value: "ref?" },
    });
    fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
    await screen.findByText("See here.");
    expect(screen.getByTestId("citation-chip").textContent).toBe("Source");
  });

  it("omits the citation row when citations is empty", async () => {
    mockFetchOnce({ answer: "Plain reply.", route: "agent", citations: [] });
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    fireEvent.change(screen.getByTestId("chat-input-textarea"), {
      target: { value: "x" },
    });
    fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
    await screen.findByText("Plain reply.");
    expect(screen.queryByTestId("citation-chips")).not.toBeInTheDocument();
  });
});

// =====================================================
// US1 — Char counter + 2000-char cap (T043)
// =====================================================

describe("US1: char counter + 2000-char cap", () => {
  it("hides the counter well below the cap", () => {
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "short" } });
    expect(screen.queryByTestId("chat-input-counter")).not.toBeInTheDocument();
  });

  it("shows the counter when approaching the cap", () => {
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "x".repeat(1900) } });
    expect(screen.getByTestId("chat-input-counter").textContent).toBe(
      "1900 / 2000"
    );
  });

  it("rejects send when over the 2000-char cap", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    const input = screen.getByTestId("chat-input-textarea") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "x".repeat(2001) } });
    expect(screen.getByTestId("chat-input-send")).toBeDisabled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

// =====================================================
// US1 — Same-mount history preserved across CLOSE/OPEN; RESET clears (T044)
// =====================================================

describe("US1: history persists across CLOSE/OPEN within the same mount", () => {
  it("dispatching CLOSE then OPEN preserves messages; RESET clears them", async () => {
    mockFetchOnce({ answer: "first reply", route: "agent" });
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    fireEvent.change(screen.getByTestId("chat-input-textarea"), {
      target: { value: "first send" },
    });
    fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
    await screen.findByText("first reply");

    // CLOSE then OPEN (pagehide and visibilitychange→hidden RESET in
    // ChatWidget; bare visibilitychange→visible does not). Simulate the
    // visitor minimising the panel and re-opening without leaving the page.
    fireEvent(
      document,
      new Event("visibilitychange") // jsdom defaults to "visible"
    );

    // Messages still present.
    expect(screen.getByText("first send")).toBeInTheDocument();
    expect(screen.getByText("first reply")).toBeInTheDocument();

    // Now simulate page hide → RESET fires.
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    fireEvent(document, new Event("visibilitychange"));

    await waitFor(() => {
      expect(screen.queryByText("first send")).not.toBeInTheDocument();
      expect(screen.queryByText("first reply")).not.toBeInTheDocument();
    });

    // Restore default for downstream tests.
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
  });
});

describe("US3: unmount + remount starts fresh (FR-019 at component level)", () => {
  it("a remounted ChatPane has an empty messages array", async () => {
    mockFetchOnce({ answer: "first reply", route: "agent" });
    const { unmount } = render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);
    fireEvent.change(screen.getByTestId("chat-input-textarea"), {
      target: { value: "first send" },
    });
    fireEvent.keyDown(screen.getByTestId("chat-input-textarea"), { key: "Enter" });
    await screen.findByText("first reply");

    unmount();

    // Remount.
    mockFetchOnce({ answer: "second reply", route: "agent" });
    render(<ChatPane backendUrl={BACKEND} initiallyOpen={true} />);

    // The new pane has zero messages.
    expect(screen.queryByText("first send")).not.toBeInTheDocument();
    expect(screen.queryByText("first reply")).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("message-bubble--user")).toHaveLength(0);
    expect(screen.queryAllByTestId("message-bubble--assistant")).toHaveLength(0);
  });
});
