# Widget-Routes Contract (UI consumer view)

What the embedded widget iframe sends and expects from the backend. All requests originate from inside the iframe; the loader script (`widget.js`) only injects the iframe — it never makes API calls itself.

---

## *POST /widgets/token* — public (browser-origin gated)

Issued on iframe boot.

Request:
```json
{ "widget_id": "<uuid>" }
```
- `Origin` header set by the browser; backend validates against the tenant's allow-list.
- Backend does NOT trust `tenant_id` from any field.

Response 200:
```json
{ "token": "<jwt>", "expires_in": 900, "session_id": "<uuid>" }
```

JWT claims:
```
{ tenant_id, widget_id, origin, session_id, iat, exp }
```

Response 403 (every refusal cause collapses to the same body):
```json
{ "error": "widget_unavailable" }
```

UI behavior: on 403, render the "Widget unavailable" status banner with a retry button. **Never** disclose which check failed — origin mismatch, unknown widget, suspended tenant, and rate-limit all look identical.

---

## *POST /chat* — widget JWT

Sent for every visitor message.

Request:
```
Authorization: Bearer <widget-jwt>
Content-Type: application/json
```
```json
{ "message": "user text", "session_id": "<uuid>" }
```

Response 200:
```json
{ "answer": "assistant text",
  "route": "rag_search" | "capture_lead" | "escalate" | "agent" | "blocked",
  "used_tools": [ { "name": "rag_search", "args": {...} } ],
  "citations": [ { "title": "Pricing FAQ", "url": "https://..." } ],
  "ticket_id": "<uuid>" }
```

UI defensive parsing (already shipped):
- `answer` and `route` are required; missing = treat as error.
- `citations`, `used_tools`, `ticket_id` default to `[]` / `[]` / `null` if absent.
- Unknown `route` values render as a plain assistant reply (forward-compatibility).

Response 401:
```json
{ "error": "token_invalid" }
```
UI behavior: dispatch `SESSION_EXPIRED`; show "Session expired, please reload"; do **not** auto-refresh.

Response 429: render "Please wait a moment and try again."

Response 5xx: render error banner with retry; clicking retry re-issues the last user message exactly once.

---

## **GET /tenants/{tid}/agent-config** — widget JWT *(MISSING)*

Called once on first panel open to populate greeting + quick-action chips.

Expected response 200:
```json
{ "persona_name": "Acme Concierge",
  "greeting": "Hi! How can I help?",
  "tone": "professional",
  "language": "en",
  "business_rules": "...",
  "chips": ["View services", "Pricing", "Book appointment", "Talk to human"] }
```

UI mock until live: hard-coded English defaults with `(placeholder)` decoration on a small footer note.

---

## Storage discipline (constitution Principle IV)

The widget MUST NOT write the token, the session_id, or any chat content to:
- `localStorage`
- `sessionStorage`
- `document.cookie`
- IndexedDB

The only persistent surface is the page-lifetime module-scope variables in [api.ts](frontend/widget/src/api.ts). This is enforced by 4 vitest tests in `__tests__/api.test.ts` that this plan keeps green.

Page navigation / refresh discards all state (FR-070). This is a feature, not a bug.

---

## Postmessage handshake (widget.js ↔ iframe main.tsx)

`widget.js` to iframe (on mount):
```js
{ type: "concierge.widget.host_origin", origin: window.location.origin }
```

iframe to `widget.js` (on open/close, for iframe sizing):
```js
{ type: "concierge.widget.resize", width: 380, height: 560 }
{ type: "concierge.widget.resize", width: 80,  height: 80 }   // collapsed
```

Both messages validate `event.origin` against the loader's known host and reject any other origin.
