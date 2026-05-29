// Owner: Amer
// Pure-function tests for the chat reducer. Covers every action in the
// ChatAction union plus the single-in-flight guard and the RETRY_LAST gate.

import { describe, expect, it } from "vitest";
import {
  initialState,
  reducer,
  type ChatAction,
  type ChatState,
} from "../state/useChatReducer";
import type { ChatMessage } from "../types";

const userMsg = (id: string, content = "u"): ChatMessage => ({
  id,
  role: "user",
  content,
});
const assistantMsg = (id: string, content = "a"): ChatMessage => ({
  id,
  role: "assistant",
  content,
});

const sendStart = (id: string, prompt: string): ChatAction => ({
  type: "SEND_START",
  userMessage: userMsg(id, prompt),
  prompt,
});

describe("reducer: initial state", () => {
  it("starts closed (bubble-first) with no messages and idle status", () => {
    expect(initialState).toEqual({
      open: false,
      messages: [],
      status: "idle",
      pendingPrompt: null,
      errorKind: null,
    });
  });
});

describe("reducer: OPEN / CLOSE", () => {
  it("OPEN sets open=true", () => {
    const closed: ChatState = { ...initialState, open: false };
    expect(reducer(closed, { type: "OPEN" })).toMatchObject({ open: true });
  });
  it("CLOSE sets open=false but preserves messages", () => {
    const withMessages: ChatState = {
      ...initialState,
      messages: [userMsg("u1"), assistantMsg("a1")],
    };
    const after = reducer(withMessages, { type: "CLOSE" });
    expect(after.open).toBe(false);
    expect(after.messages).toHaveLength(2);
  });
});

describe("reducer: SEND_START", () => {
  it("appends user message + flips to sending", () => {
    const after = reducer(initialState, sendStart("u1", "hi"));
    expect(after.status).toBe("sending");
    expect(after.messages).toHaveLength(1);
    expect(after.messages[0]).toMatchObject({ role: "user", content: "hi" });
    expect(after.pendingPrompt).toBe("hi");
    expect(after.errorKind).toBeNull();
  });
  it("is ignored while sending (single-in-flight guard)", () => {
    const sending = reducer(initialState, sendStart("u1", "first"));
    const ignored = reducer(sending, sendStart("u2", "second"));
    expect(ignored).toBe(sending);
  });
  it("is ignored when expired", () => {
    const expired = reducer(initialState, { type: "SESSION_EXPIRED" });
    const ignored = reducer(expired, sendStart("u1", "anything"));
    expect(ignored).toBe(expired);
  });
});

describe("reducer: SEND_OK", () => {
  it("appends assistant message + flips to idle + clears pending/error", () => {
    const sending = reducer(initialState, sendStart("u1", "hi"));
    const ok = reducer(sending, {
      type: "SEND_OK",
      assistantMessage: assistantMsg("a1", "hello"),
    });
    expect(ok.status).toBe("idle");
    expect(ok.pendingPrompt).toBeNull();
    expect(ok.errorKind).toBeNull();
    expect(ok.messages).toHaveLength(2);
    expect(ok.messages[1]).toMatchObject({
      role: "assistant",
      content: "hello",
    });
  });
});

describe("reducer: SEND_ERROR", () => {
  it.each(["network", "server"] as const)("kind=%s sets status=error", (kind) => {
    const sending = reducer(initialState, sendStart("u1", "x"));
    const err = reducer(sending, { type: "SEND_ERROR", kind });
    expect(err.status).toBe("error");
    expect(err.errorKind).toBe(kind);
    // pendingPrompt is preserved so RETRY_LAST can resend it.
    expect(err.pendingPrompt).toBe("x");
  });
});

describe("reducer: SESSION_EXPIRED", () => {
  it("flips status to expired and clears pendingPrompt", () => {
    const sending = reducer(initialState, sendStart("u1", "x"));
    const exp = reducer(sending, { type: "SESSION_EXPIRED" });
    expect(exp.status).toBe("expired");
    expect(exp.pendingPrompt).toBeNull();
  });
});

describe("reducer: RETRY_LAST", () => {
  it("flips error->sending and clears errorKind", () => {
    const sending = reducer(initialState, sendStart("u1", "x"));
    const errored = reducer(sending, { type: "SEND_ERROR", kind: "server" });
    const retrying = reducer(errored, { type: "RETRY_LAST" });
    expect(retrying.status).toBe("sending");
    expect(retrying.errorKind).toBeNull();
    expect(retrying.pendingPrompt).toBe("x");
  });
  it("is a no-op when status is not error", () => {
    const sending = reducer(initialState, sendStart("u1", "x"));
    expect(reducer(sending, { type: "RETRY_LAST" })).toBe(sending);
  });
  it("is a no-op when pendingPrompt is null", () => {
    expect(reducer(initialState, { type: "RETRY_LAST" })).toBe(initialState);
  });
});

describe("reducer: RESET", () => {
  it("clears messages/status/pending/error but preserves open=true", () => {
    const withState: ChatState = {
      open: true,
      messages: [userMsg("u1"), assistantMsg("a1")],
      status: "error",
      pendingPrompt: "stuck",
      errorKind: "server",
    };
    const after = reducer(withState, { type: "RESET" });
    expect(after).toEqual({ ...initialState, open: true });
  });
  it("preserves open=false through RESET", () => {
    const closed: ChatState = {
      open: false,
      messages: [userMsg("u1")],
      status: "idle",
      pendingPrompt: null,
      errorKind: null,
    };
    const after = reducer(closed, { type: "RESET" });
    expect(after.open).toBe(false);
    expect(after.messages).toHaveLength(0);
  });
});
