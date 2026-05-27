# Contract: Widget Chat Endpoint (Consumer Side)

This is the consumer's view of `POST /chat`. The platform contract is owned by Nasser (CONTRACT.md §2.9); this document records exactly what the widget sends, what it expects back, and how it handles every response shape.

The widget is a strict **consumer** — it does not extend, modify, or rely on undocumented fields. If Nasser's contract changes, the widget continues to work as long as the required fields (`answer`, `route`) are present.

## Request

```
POST /chat
Authorization: Bearer <jwt>            # the token from feature 001's exchange, in the iframe's memory only
Content-Type: application/json
```

Body:

```json
{
  "message": "<visitor text, trimmed, non-empty, ≤ 4000 chars>",
  "session_id": "<UUID from feature 001's token response>"
}
```

| Field | Type | Source | Notes |
|---|---|---|---|
| `message` | string | visitor input via `ChatInput` | After `.trim()`. Empty / whitespace-only messages MUST NOT be sent (FR-003). Length ≤ 4000 chars enforced client-side. |
| `session_id` | UUID (string) | `getSessionId()` from `api.ts` | The session identifier returned by feature 001's `/widgets/token` call. The widget never decodes the JWT to obtain it. |

The widget MUST NOT include `tenant_id` in the body. The server derives `tenant_id` from the bearer token (Constitution Principle I + spec.md FR-004).

## Success response (HTTP 200)

```json
{
  "answer": "string (required)",
  "route": "workflow | agent | blocked | escalate (required)",
  "used_tools": ["rag_search", "..."],
  "citations": [ /* opaque to widget */ ],
  "ticket_id": "uuid-or-null"
}
```

Per [data-model.md §2](../data-model.md#2-chatresponse-consumer-shape-defensive-parse-of-nassers-post-chat-reply), the widget parses defensively:

| Field | Required by widget? | Default if missing/wrong type | Effect on UI |
|---|---|---|---|
| `answer` | yes | (whole response treated as malformed → throws → retry banner) | rendered as assistant message text |
| `route` | yes | (whole response treated as malformed → retry banner) | drives the `route` branch below |
| `used_tools` | no | `[]` | not rendered in v1 |
| `citations` | no | `[]` | not rendered in v1 (passed through unchanged for future use) |
| `ticket_id` | no | `null` | rendered as ticket pill only when `route === "escalate"` AND value is a non-empty string |

### `route` field handling

| Value | Widget behavior |
|---|---|
| `"workflow"` | Render `answer` as a normal assistant message. No pill. |
| `"agent"` | Render `answer` as a normal assistant message. No pill. |
| `"blocked"` | Render `answer` as a normal assistant message. The platform-side guardrail has already produced a safe refusal message; the widget displays it verbatim. No special UI. (Edge case from spec.md.) |
| `"escalate"` | Render `answer` as a normal assistant message. Display "Ticket #<ticket_id>" pill at the bottom of the conversation pane IFF `ticket_id` is a non-empty string. If `ticket_id` is missing/null, omit the pill — never show "Ticket #null". |
| any other value | Render `answer` as a normal assistant message (treat as `"agent"`). No pill. The unknown value is logged client-side via `console.warn` for diagnostics. |

## Failure responses

### HTTP 401 — terminal

The bearer token is expired, invalid, or has been rejected by the platform. The widget:

1. Transitions to the `"expired"` state.
2. Renders "Session expired, please reload" in place of the loading indicator.
3. Disables the input affordance.
4. Does NOT attempt to re-acquire a token (FR-013). The visitor must reload the host page; that triggers feature 001's fresh token exchange.

### HTTP 4xx (other) / 5xx / network error — retryable

The widget:

1. Transitions to the `"error"` state.
2. Renders a banner with retry copy ("Couldn't reach the assistant. **Retry**.") — never the HTTP code, never the response body (FR-017).
3. Keeps the pending user message visible in the conversation pane.
4. Clicking Retry: re-sends the same `message` + `session_id` exactly once per click. On success, the conversation pane shows one user-message and one assistant-reply for the logical exchange (FR-015, FR-016).
5. If a retry itself fails, returns to `"error"` state; the visitor can retry again.

### Malformed success body

If the response is HTTP 200 but the body is missing `answer` or `route` (or they're the wrong type), the widget treats it identically to a 5xx failure — `"error"` state, retry banner. This is the FR-011/FR-012 defensive-parse path.

## Headers

| Header | Required | Notes |
|---|---|---|
| `Authorization: Bearer <jwt>` | yes | From `api.ts` `getToken()`. The component layer never sees the token. |
| `Content-Type: application/json` | yes | Standard. |

The widget MUST NOT send custom platform-internal headers (no `X-Tenant-Id`, no `X-Widget-Id`, etc.). All trusted identity flows through the JWT.

## What the widget MUST NOT do

- Decode the JWT to inspect claims. The token is opaque to the widget.
- Re-acquire a token on 401. The reload is the only refresh path.
- Persist any request, response, or token to browser storage at any point (FR-018).
- Display raw HTTP status codes, raw response bodies, stack traces, or platform identifiers to the visitor (FR-017).
- Issue more than one `/chat` request at a time (FR-005). Concurrent sends are coalesced by the `"sending"` state guard.

## Examples

### Successful exchange (developer console)

```
fetch("/chat", {
  method: "POST",
  headers: {
    "Authorization": "Bearer eyJ...",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    message: "What are your hours?",
    session_id: "f1c8d4e2-5a3b-4c7d-8e9f-1a2b3c4d5e6f",
  }),
});
```

```http
HTTP/1.1 200 OK
{"answer":"We're open 9-5 Mon-Fri.","route":"agent","used_tools":["rag_search"],"citations":[],"ticket_id":null}
```

Widget renders: `"What are your hours?"` (user bubble) → `"We're open 9-5 Mon-Fri."` (assistant bubble). No pill.

### Escalation

```http
HTTP/1.1 200 OK
{"answer":"Let me connect you with a human.","route":"escalate","ticket_id":"abc-123"}
```

Widget renders: assistant bubble + "Ticket #abc-123" pill at bottom of pane.

### Expired token

```http
HTTP/1.1 401 Unauthorized
{"detail":"Token expired"}
```

Widget renders: "Session expired, please reload". Input disabled. No retry.

### Server error

```http
HTTP/1.1 500 Internal Server Error
{"detail":"Internal Server Error"}
```

Widget renders: retry banner with "Couldn't reach the assistant. **Retry**." No HTTP code shown.
