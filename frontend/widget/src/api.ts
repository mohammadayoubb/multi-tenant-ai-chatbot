// Owner: Amer
// Token store + fetch helpers for the widget iframe.
//
// Per Constitution Principle IV and spec.md FR-011 / FR-012:
//   the session credential lives in module-scope memory only.
//   NEVER write it to localStorage, sessionStorage, cookies, or IndexedDB.

import type { WidgetTokenResponse } from "./types";

let _token: string | null = null;
let _sessionId: string | null = null;
let _expiresAt: number | null = null;

export async function exchangeToken(
  backendUrl: string,
  widgetId: string
): Promise<WidgetTokenResponse> {
  const res = await fetch(`${backendUrl}/widgets/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ widget_id: widgetId }),
  });
  if (!res.ok) {
    throw new Error(`token_exchange_failed_${res.status}`);
  }
  const data = (await res.json()) as WidgetTokenResponse;
  _token = data.token;
  _sessionId = data.session_id;
  _expiresAt = Date.now() + data.expires_in * 1000;
  return data;
}

export function getToken(): string | null {
  return _token;
}

export function getSessionId(): string | null {
  return _sessionId;
}

export function clearToken(): void {
  _token = null;
  _sessionId = null;
  _expiresAt = null;
}

// Test-only accessor — used by the storage-discipline vitest to inspect the
// module-scope store without going through browser storage APIs.
export function __debugTokenStoreSnapshot(): {
  token: string | null;
  sessionId: string | null;
  expiresAt: number | null;
} {
  return { token: _token, sessionId: _sessionId, expiresAt: _expiresAt };
}
