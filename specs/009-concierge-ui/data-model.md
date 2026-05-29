# Phase 1 — Data Model: Concierge UI

This is **UI-side** data model only. It documents the shape of state held in admin `st.session_state`, in the widget iframe (React state + module-scope tokens + reducer state), and the entity projections rendered on each surface.

**This plan introduces zero new database tables and zero migrations.** Backend persistence shapes are documented in [contracts/](contracts/).

---

## A. Admin-side state (Streamlit `st.session_state`)

| Key | Type | Lifetime | Source | Notes |
|---|---|---|---|---|
| `admin_token` | `str` (JWT, HS256) | Until logout or browser close | `POST /admin/login` response | Bearer token — never written to localStorage; cleared by `auth_state.clear_session()`. |
| `admin_role` | `Literal["tenant_admin", "tenant_manager"]` | Same as `admin_token` | Decoded JWT claim | Used by `streamlit_app.py` dispatcher only. |
| `admin_tenant_id` | `str` (UUID) | Same as `admin_token` | Decoded JWT claim | Tenant-admin only; tenant-manager value is the platform meta-tenant or null. |
| `admin_actor_id` | `str` (UUID) | Same as `admin_token` | Decoded JWT claim | Used by audit-log filters defaulting to "my actions". |
| `admin_full_name` | `str` | Same as `admin_token` | Server-issued at login | Displayed in topbar. |
| `<page>_draft` | per-page model | Per page session | Page form state | Cleared on save success or on tab switch. |
| `<page>_saved` | per-page model | Per page session | Last-known good after save | Used for unsaved-changes detection on `widget_page.py`. |

**Invariant:** every fetch through `_admin_http.http_client()` reads `admin_token` and attaches `Authorization: Bearer <token>`. On 401, `auth_state.clear_session()` wipes every `admin_*` key and `st.rerun()` lands the user on login.

---

## B. Widget-side state (iframe React app)

### B.1 Module-scope (in `frontend/widget/src/api.ts`)

| Variable | Type | Lifetime |
|---|---|---|
| `_token` | `string \| null` | Page lifetime (cleared on widget unmount / page nav) |
| `_sessionId` | `string \| null` | Same as `_token` |
| `_expiresAt` | `number \| null` (ms epoch) | Same |
| `_hostOrigin` | `string \| null` | Set by `postMessage` handshake from `widget.js` |

Storage discipline: **none of these are mirrored to `localStorage`, `sessionStorage`, or `document.cookie`** — enforced by 4 vitest assertions in [__tests__/api.test.ts](frontend/widget/src/__tests__/api.test.ts).

### B.2 Reducer state (new `state/useChatReducer.ts`)

```ts
type ChatMessage =
  | { kind: "user"; id: string; text: string; createdAt: number }
  | { kind: "assistant"; id: string; text: string; route: string;
      citations?: { title: string; url: string }[];
      ticketId?: string;
      createdAt: number };

type Status = "idle" | "sending" | "error" | "expired";

interface ChatState {
  open: boolean;                    // bubble closed vs panel open
  messages: ChatMessage[];          // chat history (Q3: persists across reopen)
  status: Status;
  pendingPrompt: string | null;     // last user prompt awaiting reply (for retry)
  errorKind: "network" | "rate_limited" | "blocked" | "unknown" | null;
}

type ChatAction =
  | { type: "OPEN" }
  | { type: "CLOSE" }
  | { type: "SEND_START"; userMsg: ChatMessage }
  | { type: "SEND_OK"; assistantMsg: ChatMessage }
  | { type: "SEND_ERROR"; kind: "network" | "rate_limited" | "blocked" | "unknown" }
  | { type: "SESSION_EXPIRED" }
  | { type: "RETRY_LAST" }
  | { type: "RESET" };               // bound to page-navigation event (Q3)
```

**Transitions:**

```
idle  --SEND_START-->  sending
sending  --SEND_OK-->  idle           (append assistant message)
sending  --SEND_ERROR-->  error       (append error pseudo-message + pendingPrompt set)
sending  --SESSION_EXPIRED-->  expired (terminal until reload)
error  --RETRY_LAST-->  sending       (re-issue pendingPrompt)
*  --OPEN-->  *open=true                (idempotent; preserves messages, FR-070)
*  --CLOSE-->  *open=false              (idempotent; preserves messages, FR-070)
*  --RESET-->  initial                 (RESET fires on visibilitychange to hidden + navigation)
```

The state machine is a **pure function**, testable without React. The `useChatReducer` hook wraps `useReducer` and exposes:
```ts
{ state: ChatState; open(): void; close(): void; send(text: string): void; retry(): void; }
```

### B.3 Quick-action chips

Loaded once at panel-open time via `GET /tenants/{tid}/agent-config` (delivered in Phase 2A, task T039a). Until that task lands, a hard-coded fallback array of 4 strings is rendered with a `(placeholder)` decoration as a dev-time safety net.

| Field | Type | Source |
|---|---|---|
| `chips` | `string[]` (len 0..6) | Tenant agent config |

---

## C. Entity projections rendered per surface

These describe what fields the UI displays, derived from the backend entities documented in [contracts/](contracts/). No new entities are created.

### C.1 Tenant Admin → Overview KPI cards
```
{ tenantName, widgetEnabled: boolean,
  leadsLast30d: int, escalationsOpen: int, conversationsLast30d: int,
  tokensThisMonth: int, costUsdThisMonth: float }
```

### C.2 Tenant Admin → CMS table row
```
{ id: uuid, title: str, slug: str, status: "draft"|"published"|"archived",
  updatedAt: iso }
```
Detail view adds `body: markdown, sourceUrl: url?`.

### C.3 Tenant Admin → Widget Settings
```
{ widgetId: uuid, theme: {primaryColor, textColor, bubbleColor, borderRadius},
  greeting: str (<=280), enabled: bool, allowedOrigins: url[] }
```

### C.4 Tenant Admin → Agent Settings
```
{ personaName: str, greeting: str, tone: "professional"|"friendly"|"casual",
  language: ISO-639-1, businessRules: str, chips: str[] (0..6) }
```

### C.5 Tenant Admin → Leads table row
```
{ id: uuid, capturedAt: iso, name: str, contactMasked: str (first 3 + '***'),
  intent: str, status: "captured"|"qualified"|"spam", score: float }
```
Detail view does NOT unmask contact (FR-024 forbids export and full reveal).

### C.6 Tenant Admin → Escalations table row
```
{ ticketId: uuid, openedAt: iso, lastMessageExcerpt: str (max 120 chars),
  status: "pending"|"in_progress"|"resolved",
  assigneeId: uuid?, assigneeName: str? }
```
Assignee dropdown sourced from `GET /tenants/{tid}/admin-users` (new endpoint; placeholder until live).

### C.7 Tenant Admin → Audit row
```
{ createdAt: iso, actorRole: str, actorName: str, action: str,
  metadataPreview: str (truncated to 80 chars), fullMetadata: json (modal) }
```

### C.8 Tenant Manager → Tenants table row
```
{ id: uuid, name: str, slug: str, status: "active"|"suspended",
  plan: str, adminEmail: str, createdAt: iso }
```
Never includes content totals beyond aggregate counts.

### C.9 Tenant Manager → Invites table row
```
{ token: uuid, email: str, role: "tenant_admin"|"tenant_manager",
  tenantName: str, status: "pending"|"used"|"expired"|"revoked",
  expiresAt: iso }
```

### C.10 Tenant Manager → Audit Logs row
Same as C.7 but with an added `tenantName` column and no tenant scoping.

### C.11 Tenant Manager → Usage & Cost row
```
{ tenantName: str, totalTokens: int, costUsd: float, dailyCost: [{date, cost}] }
```
No conversation, lead, or page content.

---

## D. State transitions of interest (UI-side)

### D.1 Invite acceptance

```
GET /admin/invites/{token}      → status: "pending"|"used"|"expired"|"revoked"|"unknown"
  pending  →   render form
  used     →   render terminal banner "Invite already used"
  expired  →   render terminal banner "Invite expired"
  revoked  →   render terminal banner "Invite revoked"
  unknown  →   render terminal banner "Invite link not recognized"

POST /admin/invites/{token}/accept (body: full_name + password + confirm)
  200 → POST /admin/login (auto) → dispatcher routes by role
  422 → render per-field error (weak password / mismatch)
  410 → render terminal banner "Invite no longer valid"
  409 → render terminal banner "Account already exists"
```

### D.2 Widget panel open / close (FR-070)

```
initial:           open=false, messages=[]
user clicks bubble: OPEN  → open=true, messages preserved (initially [], greeting shown)
user types + sends: SEND_START → messages.push(user), status=sending
backend 200:       SEND_OK → messages.push(assistant), status=idle
backend 401:       SESSION_EXPIRED → status=expired (terminal)
user clicks close: CLOSE → open=false, messages preserved
user reopens:      OPEN  → open=true, messages still present
user refreshes:    (page lifecycle ends) → all state lost → fresh initial state
```

### D.3 Origin allow-list edit (audit-logged)

```
user adds origin URL → client validates URL shape →
  PUT /widgets/config (allowed_origins = current + new)
    200 → toast "Saved"; backend audit-logs widget.origin_added
    422 → inline field error
    409 → toast "Conflict — refresh and retry"
```

---

## E. Recap of Constitution Check (post-design)

| Principle | Status | Where verified |
|---|---|---|
| I — Tenant Isolation | ✓ | All entity projections derive `tenant_id` from server-issued tokens (Section A, B.1). |
| II — Layered Architecture | ✓ | UI consumes backend via httpx/fetch only; no SQL in `admin/` or `frontend/widget/`. |
| III — Bounded Agent | ✓ | No new tool. Chip list is data, rendered by the widget; the agent doesn't see it. |
| IV — Defense-in-Depth Auth | ✓ | Token-storage rules made explicit in §A and §B.1; vitest assertions enforce. |
| V — Lean Serving & Redaction | ✓ | No model code. Lead detail view does not unmask (§C.5). Telemetry is no-op. |
| VI — Phased Build | ✓ | UI phases sit in Constitution Phases 7/8; Phase 2A closes leftover backend items from Phases 1, 2, and 5 inside this feature. Sequenced so backend endpoints land before the UI tasks that consume them. |
| VII — Clean & Simple Code | ✓ | Single shared `audit_page.py` for two roles (R10); pure-function reducer; no speculative state fields. |
