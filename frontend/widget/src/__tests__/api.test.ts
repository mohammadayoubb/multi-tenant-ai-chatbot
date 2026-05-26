// Owner: Amer
// Storage-discipline tests for the widget token API helper.
//
// Validates Constitution Principle IV + spec.md FR-011 / FR-012 / SC-004:
//   after a successful token exchange, the session credential lives only in
//   module-scope memory. It MUST NEVER appear in localStorage, sessionStorage,
//   document.cookie, or IndexedDB at any point in the iframe's lifecycle.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  __debugTokenStoreSnapshot,
  clearToken,
  exchangeToken,
  getSessionId,
  getToken,
} from "../api";

const FAKE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake.body";
const FAKE_SESSION_ID = "f1c8d4e2-5a3b-4c7d-8e9f-1a2b3c4d5e6f";

describe("widget token api: storage discipline", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    document.cookie.split(";").forEach((c) => {
      const eqPos = c.indexOf("=");
      const name = eqPos > -1 ? c.substring(0, eqPos).trim() : c.trim();
      document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
    });
    clearToken();

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          token: FAKE_TOKEN,
          expires_in: 900,
          session_id: FAKE_SESSION_ID,
        }),
      }))
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearToken();
  });

  it("stores the token in module memory after a successful exchange", async () => {
    await exchangeToken("http://localhost:8000", "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d");
    expect(getToken()).toBe(FAKE_TOKEN);
    expect(getSessionId()).toBe(FAKE_SESSION_ID);
    const snapshot = __debugTokenStoreSnapshot();
    expect(snapshot.token).toBe(FAKE_TOKEN);
  });

  it("never writes the token to localStorage", async () => {
    await exchangeToken("http://localhost:8000", "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d");
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)!;
      const value = localStorage.getItem(key) ?? "";
      expect(value).not.toContain(FAKE_TOKEN);
      expect(value).not.toContain(FAKE_SESSION_ID);
    }
    expect(localStorage.length).toBe(0);
  });

  it("never writes the token to sessionStorage", async () => {
    await exchangeToken("http://localhost:8000", "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d");
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i)!;
      const value = sessionStorage.getItem(key) ?? "";
      expect(value).not.toContain(FAKE_TOKEN);
      expect(value).not.toContain(FAKE_SESSION_ID);
    }
    expect(sessionStorage.length).toBe(0);
  });

  it("never writes the token to document.cookie", async () => {
    await exchangeToken("http://localhost:8000", "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d");
    expect(document.cookie).not.toContain(FAKE_TOKEN);
    expect(document.cookie).not.toContain(FAKE_SESSION_ID);
  });

  it("clearToken wipes the in-memory store", async () => {
    await exchangeToken("http://localhost:8000", "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d");
    clearToken();
    expect(getToken()).toBeNull();
    expect(getSessionId()).toBeNull();
    const snapshot = __debugTokenStoreSnapshot();
    expect(snapshot.token).toBeNull();
    expect(snapshot.sessionId).toBeNull();
    expect(snapshot.expiresAt).toBeNull();
  });

  it("propagates failure when the exchange returns non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 403,
        json: async () => ({ error: "widget_unavailable" }),
      }))
    );
    await expect(
      exchangeToken("http://localhost:8000", "00000000-0000-0000-0000-000000000000")
    ).rejects.toThrow();
    expect(getToken()).toBeNull();
  });
});
