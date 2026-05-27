// Owner: Amer
// Token store + fetch helpers for the widget iframe.
//
// Per Constitution Principle IV and spec.md FR-011 / FR-012 / FR-018:
//   the session credential AND any conversation content live in module-scope
//   or React-state memory only. NEVER write to localStorage, sessionStorage,
//   cookies, or IndexedDB.

import type { ChatErrorKind, ChatResponse, WidgetTokenResponse } from "./types";

let _token: string | null = null;
let _sessionId: string | null = null;
let _expiresAt: number | null = null;

export class ApiError extends Error {
  readonly kind: "expired" | ChatErrorKind;
  constructor(kind: "expired" | ChatErrorKind, message?: string) {
    super(message ?? `api_error_${kind}`);
    this.name = "ApiError";
    this.kind = kind;
  }
}

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

// Test-only setter — wires a known token into the module-scope store so
// component tests don't need to walk through the full token exchange.
export function __debugSetToken(token: string, sessionId: string): void {
  _token = token;
  _sessionId = sessionId;
  _expiresAt = Date.now() + 900_000;
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

// ---------------------------------------------------------------------------
// Phase 2 — chat message exchange
// ---------------------------------------------------------------------------

const CHAT_PATH = "/chat";

/**
 * Send a chat message to the platform.
 *
 * On HTTP 401: throws ApiError("expired"). Terminal — caller must show the
 *   "Session expired, please reload" prompt and not retry (FR-013).
 * On any other non-2xx: throws ApiError("server"). Caller shows retry banner.
 * On network failure: throws ApiError("network"). Caller shows retry banner.
 * On 2xx with malformed body (missing `answer` or `route`): throws
 *   ApiError("server"). Defensive parse per FR-011 / FR-012.
 * On 2xx with well-formed body: returns ChatResponse with safe defaults
 *   applied to optional fields.
 */
export async function sendChatMessage(
  backendUrl: string,
  message: string
): Promise<ChatResponse> {
  const token = _token;
  const sessionId = _sessionId;
  if (token === null || sessionId === null) {
    throw new ApiError("expired");
  }

  let res: Response;
  try {
    res = await fetch(`${backendUrl}${CHAT_PATH}`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  } catch {
    throw new ApiError("network");
  }

  if (res.status === 401) {
    throw new ApiError("expired");
  }
  if (!res.ok) {
    throw new ApiError("server");
  }

  let raw: unknown;
  try {
    raw = await res.json();
  } catch {
    throw new ApiError("server");
  }

  return parseChatResponse(raw);
}

/** Defensive parse: `answer` + `route` required; everything else defaults. */
function parseChatResponse(raw: unknown): ChatResponse {
  if (typeof raw !== "object" || raw === null) {
    throw new ApiError("server");
  }
  const obj = raw as Record<string, unknown>;
  const answer = obj.answer;
  const route = obj.route;
  if (typeof answer !== "string" || typeof route !== "string") {
    throw new ApiError("server");
  }

  const used_tools = Array.isArray(obj.used_tools)
    ? (obj.used_tools.filter((v) => typeof v === "string") as string[])
    : [];
  const citations = Array.isArray(obj.citations) ? obj.citations : [];
  const ticket_id =
    typeof obj.ticket_id === "string" && obj.ticket_id.length > 0
      ? obj.ticket_id
      : null;

  return { answer, route, used_tools, citations, ticket_id };
}
