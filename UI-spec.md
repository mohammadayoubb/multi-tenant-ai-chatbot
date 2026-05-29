# UI-spec.md — Concierge UI Blueprint: SpecKit Specification & Plan

> Source analyzed: [Concierge_UI_Blueprint.md](Concierge_UI_Blueprint.md)
> Companion context: [summary.md](summary.md), [CLAUDE.md](CLAUDE.md), [amer-works.md](amer-works.md)
> Phase scope: Phase 7–8 (Widget + Admin UI) per Concierge build order.

This document turns the natural-language UI blueprint into a production-grade SpecKit specification and implementation plan. It is the single source-of-truth for the next `/speckit-specify` and `/speckit-plan` rounds on the UI surfaces.

---

## 1. Overview

### 1.1 Purpose of the analyzed file

[Concierge_UI_Blueprint.md](Concierge_UI_Blueprint.md) defines **what the Concierge product must look like and feel like from the user's seat** — not how it's built. It captures the three user-facing surfaces (Tenant Manager dashboard, Tenant Admin dashboard, Public Widget) and one cross-cutting surface (Authentication), then enumerates the tabs, fields, allowed actions, and demo behaviors that make the product feel like a real multi-tenant SaaS.

It is a **product blueprint**, not an engineering spec:
- It names screens, tabs, and KPIs but does not define DB columns, endpoint shapes, or component trees.
- It encodes the **single load-bearing UI principle** of the project: *the frontend never decides tenant identity — backend auth or signed widget tokens do.*
- It includes a build priority (P0/P1/P2) and a "what not to build" list that doubles as a security boundary.

### 1.2 Current architecture and workflow

The blueprint sits on top of an already-shipped backend (see [summary.md](summary.md) §1–§7). Three independent auth surfaces are live:

| Surface | Token | TTL | Used by |
|---|---|---|---|
| Admin JWT | `Authorization: Bearer <admin-jwt>` HS256 | 8 h | Streamlit admin UI |
| Widget JWT | `Authorization: Bearer <widget-jwt>` HS256 | 15 min | Visitor iframe |
| Platform-actor headers (legacy) | `X-Actor-ID` + `X-Actor-Role` | — | `/tenants/*` legacy CRUD |

Existing UI implementations — what's actually in the tree today:

| File | Current state | Notes |
|---|---|---|
| [admin/streamlit_app.py](admin/streamlit_app.py) | Shipped | Dispatcher: `?page=accept-invite` → invite flow; otherwise login → role-based dashboard. Guardrails nav entry is a placeholder. |
| [admin/login_page.py](admin/login_page.py) | Shipped | Real `POST /admin/login`; generic error collapse. |
| [admin/accept_invite_page.py](admin/accept_invite_page.py) | Shipped | Real preview + accept + auto-login. |
| [admin/access_denied_page.py](admin/access_denied_page.py) | Shipped | Sign-out only fallback. |
| [admin/platform_dashboard_page.py](admin/platform_dashboard_page.py) | **Invite form only** | No Tenants table, Audit Logs, Settings, or Usage roll-up yet — Phase D is net-new. |
| [admin/widget_page.py](admin/widget_page.py) | Shipped (full CRUD) | Allowed-origins editor, theme JSON, greeting, enabled toggle, unsaved-changes tracking. |
| [admin/cms_page.py](admin/cms_page.py), [admin/leads_page.py](admin/leads_page.py), [admin/usage_page.py](admin/usage_page.py), [admin/tenant_page.py](admin/tenant_page.py) | Read-only with `_SAMPLE_*` fallback + visible `(placeholder)` badge already wired |
| [admin/_admin_http.py](admin/_admin_http.py) | Shipped | Has `http_client()` (Bearer auth from `st.session_state`) + `signed_in_tenant_id()` helper. |
| [admin/brand.py](admin/brand.py) | Shipped, minimal | Currently only `PRODUCT_NAME` / `PRODUCT_TAGLINE` + centered-card CSS; no color/spacing tokens yet. |
| [admin/auth_state.py](admin/auth_state.py) | Shipped | `is_authenticated()`, `get_role()`, `get_tenant_id()`, `set_session()`, `clear_session()`. |
| [frontend/widget/public/widget.js](frontend/widget/public/widget.js) | Shipped, hardened | Idempotent, fail-soft, ES2019 IIFE, sandboxed iframe. **Mounts the iframe immediately — no bubble launcher.** |
| [frontend/widget/src/main.tsx](frontend/widget/src/main.tsx), [frontend/widget/src/api.ts](frontend/widget/src/api.ts), [frontend/widget/src/types.ts](frontend/widget/src/types.ts), [frontend/widget/src/styles.css](frontend/widget/src/styles.css) | Shipped | Token in module-scope `let _token` (api.ts); 4 storage-discipline tests in `__tests__/api.test.ts`. |
| [frontend/widget/src/components/ChatPane.tsx](frontend/widget/src/components/ChatPane.tsx) | Shipped, monolithic (~231 LOC) | Owns state machine, message list, status banners, ticket pill. |
| [frontend/widget/src/components/ChatInput.tsx](frontend/widget/src/components/ChatInput.tsx) | Shipped | Controlled textarea, Enter / Shift+Enter handling. |
| `Bubble.tsx`, `Panel.tsx`, `Message.tsx`, `QuickActions.tsx`, `StatusBanner.tsx` | **None exist** | All proposed extractions from ChatPane. |

**Important UX delta:** the current widget has no bubble launcher and no closed state — the iframe opens immediately at full size. Anything in the blueprint that implies a bubble + click-to-open is net-new behavior, not polish.

Backend endpoints the UI consumes (already real):
- `POST /admin/login`, `POST /admin/invites`, `GET /admin/invites/{token}`, `POST /admin/invites/{token}/accept`
- `POST /widgets/token`, `GET /widgets/config`, `PUT /widgets/config`
- `POST /chat`
- `GET /tenants/{tid}/audit-logs`, `GET /tenants/{tid}/usage`
- `GET /cms/pages`, `POST /cms/pages`, `GET /leads`

### 1.3 How the blueprint interacts with the rest of the system

The blueprint is a **read-from / contract-into document**:
- **Reads from** [CONTRACT.md](CONTRACT.md) (route shapes, table columns), [CLAUDE.md](CLAUDE.md) (tenant safety / widget auth rules), and [summary.md](summary.md) (what's actually built).
- **Contracts into** Phase 7 (Widget) and Phase 8 (Admin UI) of the build order — its tabs map 1:1 onto the routes already shipped.
- **Boundary it enforces:** every UI surface respects backend-issued tenant identity. There is no `tenant_id` input field anywhere in the UI, no role picker, no raw secret exposure.

---

## 2. Feature Analysis

### 2.1 Detected features and behaviors

**Authentication surface (4.1, 4.2)**
- Login card: email + password, loading state, safe error messages, role-based redirect.
- Accept Invite page: email/full_name/password/confirm_password, server-issued tenant + role, password strength validation.
- Access Denied fallback for unknown roles.

**Tenant Manager dashboard (§5)** — six tabs:
- Overview — KPI cards (total / active / suspended tenants, monthly cost, open actions).
- Tenants — CRUD-style table (create, suspend, trigger erasure, view metadata) but **no read access to tenant content**.
- Invites — list + revoke + resend.
- Usage & Cost — aggregate per-tenant with chart.
- Audit Logs — provisioning, suspension, erasure, invite events; filter by actor/tenant/action/date.
- Settings — platform-level non-sensitive knobs only.

**Tenant Admin dashboard (§6)** — nine tabs:
- Overview, CMS Content, Agent Settings, Guardrails, Widget Settings, Origin Allowlist, Leads, Escalations, Usage.
- All tabs scoped to the authenticated admin's tenant.
- CRUD on CMS / Agent / Widget / Origins; read-only on Leads / Escalations / Usage / Audit.

**Public widget (§7, §8)** — visitor surface:
- Floating bubble launcher (bottom-right), tenant-themed.
- Chat panel: greeting, message history (user + assistant bubbles), input.
- Quick actions (View services, Pricing, Book appointment, Talk to human).
- States: idle, loading, lead-capture, escalation, blocked/refusal, error (bad token / bad origin / suspended tenant / expired token).

**AI workflow demos (§9)** — six visitor message categories, each with an expected UI outcome:
| Visitor intent | Backend route | UI result |
|---|---|---|
| FAQ | classifier → rag_search | RAG answer with citations |
| Sales / contact | classifier → capture_lead | Lead appears in Leads tab |
| Human request | classifier → escalate | Ticket appears in Escalations tab |
| Ambiguous | bounded agent | Clarifying question |
| Cross-tenant probe | guardrails block | Refusal message |
| Spam | classifier spam | Refused / ignored |

### 2.2 UI / UX patterns

- **SaaS-style centered card** for auth pages (matches existing [admin/brand.py](admin/brand.py)).
- **Sidebar + topbar layout** for both dashboards: sidebar = tabs; topbar = tenant name, role badge, logout.
- **Table + filter + detail-modal** for all list views (Tenants, Invites, Audit, CMS, Leads, Escalations).
- **KPI card grid** on Overview pages (4 cards per row).
- **Floating bubble + slide-up panel** for the widget.
- **Status pills** for state communication (active/suspended; captured/qualified/spam; pending/used/expired).
- **Placeholder badge** on every read-only page that has not yet been wired to a live endpoint (already used by [admin/_admin_http.py](admin/_admin_http.py)).

### 2.3 State management and data flow

**Admin (Streamlit):**
- Single source: `st.session_state["admin_token"]` (JWT) + decoded claims (tenant_id, role, actor_id).
- Page-level state: filter values, form drafts. Wiped on logout via `auth_state.clear_session`.
- No client-side persistence (no `localStorage`, no cookies — same rule as the widget).
- Routing: `st.query_params["page"]` for public pages (accept-invite); role-based dispatcher otherwise.

**Widget (React iframe):**
- Token already lives in a **module-scope variable** (`let _token` in [api.ts](frontend/widget/src/api.ts)) — verified by four storage-discipline tests in [__tests__/api.test.ts](frontend/widget/src/__tests__/api.test.ts) that assert nothing token-shaped lands in `localStorage`, `sessionStorage`, or `document.cookie`.
- Chat history + state machine (`idle → sending → idle/error/expired`) currently live as direct `useState` calls inside [ChatPane.tsx](frontend/widget/src/components/ChatPane.tsx). Reducer extraction is a Phase E refactor, not a green-field add.
- Single-in-flight guard: send button disabled while a reply is pending (shipped).
- Parent-to-iframe handshake: `postMessage` carries `data-widget-id` + parent origin (shipped in [widget.js](frontend/widget/public/widget.js) ↔ [main.tsx](frontend/widget/src/main.tsx)).

**Data flow per request:**
```
Admin UI         →  PUT /widgets/config        →  require_tenant_admin
                                                  → WidgetConfigService
                                                  → widget_repo (SQL)
                                                  → audit_logger
                                                  → response

Widget iframe    →  POST /widgets/token        →  WidgetTokenService
                                                  → SqlWidgetRepository
                                                  → origin canonicalize
                                                  → JWT mint
                                                  → response

Visitor message  →  POST /chat (Bearer jwt)    →  get_tenant_id_from_widget_token
                                                  → ChatService.handle_message
                                                  → router → tools (rag_search /
                                                              capture_lead /
                                                              escalate)
                                                  → ChatResponse{answer, route,
                                                                 used_tools,
                                                                 citations,
                                                                 ticket_id}
```

### 2.4 APIs, backend interactions, dependencies

All UI calls go through HTTPS to FastAPI on the API origin. Auth header decides which backend dep runs (`require_admin_session`, `require_tenant_admin`, or `get_tenant_id_from_widget_token`).

External runtime deps:
- **Streamlit ≥1.30** for admin UI.
- **React 18 + Vite** for widget.
- **httpx** for admin → API calls (already in [admin/_admin_http.py](admin/_admin_http.py)).
- **PyJWT** (server-side); the widget never validates JWTs — it just carries the bearer.

No third-party UI auth libs. No `localStorage` libs. No global state managers beyond Streamlit's `session_state` and React's `useReducer`.

### 2.5 Reusable components and patterns

**Already extracted (shipped):**
- [admin/brand.py](admin/brand.py) — centered card chrome + `PRODUCT_NAME` / `PRODUCT_TAGLINE`. **Does not yet hold colour / spacing / radius tokens** — only the card CSS and the product strings.
- [admin/_admin_http.py](admin/_admin_http.py) — `http_client()` (Bearer auth from `st.session_state`) + `signed_in_tenant_id()` helper.
- [admin/auth_state.py](admin/auth_state.py) — `is_authenticated()`, `get_role()`, `get_tenant_id()`, `set_session()`, `clear_session()`.
- Widget: [components/ChatPane.tsx](frontend/widget/src/components/ChatPane.tsx) (231 LOC; monolithic — owns state machine, message list, banners, ticket pill) + [components/ChatInput.tsx](frontend/widget/src/components/ChatInput.tsx) (controlled textarea, Enter/Shift+Enter).

**Proposed (not in tree yet):**
- `admin/_table.py` — `render_table(rows, columns, filters)` so Tenants / Audit / CMS / Leads / Escalations stop re-rolling table code.
- `admin/_kpi.py` — `render_kpi_row([(label, value, delta?), ...])` shared by both Overviews.
- `admin/_status_pill.py` — `render_status(value)` for tenant / lead / invite / ticket states.
- `admin/_empty.py` — empty-state card (illustration + line + optional primary CTA).
- Widget: `Bubble.tsx`, `Panel.tsx`, `Message.tsx`, `QuickActions.tsx`, `StatusBanner.tsx` — all proposed extractions from ChatPane. **Bubble is also a new UX state**, not just a refactor (widget is currently always-open).

---

## 3. Problems and Improvements

### 3.1 Weaknesses / debt in the current blueprint

1. **Tenant Manager / Tenant Admin overlap is unclear.** Both have Overview and Usage tabs — the blueprint doesn't enumerate which fields the manager sees vs. the admin. Risk: a copy-paste implementation accidentally surfaces tenant content (CMS / leads / conversations) to the platform operator, violating §5's stated rule.
2. **Streamlit is a UX ceiling.** Floating widgets, polished SaaS layouts, and responsive grids are hard in Streamlit. The blueprint implicitly assumes a React-grade admin UI; the codebase ships Streamlit. The gap means either accept the ceiling for the demo or budget a Next.js rewrite in a later phase.
3. **No explicit accessibility (a11y) requirements** — the blueprint mentions "loading state" and "safe error messages" but not ARIA, keyboard navigation, focus management, or screen-reader semantics. The widget especially needs `role="dialog"`, focus trap, ESC-to-close.
4. **No responsive breakpoints.** Widget must shrink on mobile (full-screen sheet vs. bottom-right bubble); admin must work on a 13" laptop. Streamlit handles this automatically but coarsely; the widget needs explicit CSS breakpoints.
5. **Empty states are missing.** Every table needs an empty-state design (no tenants yet / no leads yet / no escalations). Without them, fresh installs look broken.
6. **No design tokens.** Colors, spacing, and typography are not centralized — each page is at risk of drifting visually. A single `admin/brand.py` constants block + a widget `tokens.css` would fix it.
7. **Widget has no bubble launcher.** [widget.js](frontend/widget/public/widget.js) mounts the iframe immediately at fixed 360×540, with no closed state and no FAB. The blueprint §7 implies a "floating chat bubble" + click-to-open UX. This is a real product decision — either add a bubble (and an open/closed state machine in the iframe) or document the always-open model as intentional. The current spec hand-waves the gap.
8. **State-machine extraction, not green-field state.** [ChatPane.tsx](frontend/widget/src/components/ChatPane.tsx) already runs a clean `idle → sending → idle/error/expired` machine via direct `useState`. The gap is testability + readability (extract `useChatReducer`), not the absence of a state model.
9. **No telemetry hook.** The blueprint doesn't say what UI events to log (login attempt, save, error). Without it, post-demo iteration is blind.

### 3.2 Suggested improvements

| # | Improvement | Effort | Why |
|---|---|---|---|
| 1 | Add an explicit field-level matrix for Tenant Manager vs. Tenant Admin Overview / Usage tabs | S | Closes the privacy gap from §3.1 #1. |
| 2 | Add an a11y section to the spec (ARIA roles, keyboard map, focus order) | S | Cheap, raises product quality bar. |
| 3 | Define responsive breakpoints for the widget (≥640 px → bubble; <640 px → full-screen sheet) | S | Mobile parity matters for embedded widgets. |
| 4 | Extract `_table.py`, `_kpi.py`, `_status_pill.py` shared Streamlit helpers | M | Removes duplication; consistent look. |
| 5 | **Extend `admin/brand.py`** with `COLORS / SPACING / RADIUS` constants (currently only `PRODUCT_NAME` / `PRODUCT_TAGLINE`); add widget `tokens.css` | S | Prevents drift; no new files for admin. |
| 6 | Standard empty-state component for every table | S | Avoid "looks broken" on cold start. |
| 7 | **Extract `useChatReducer`** from the existing ChatPane state-changes (machine is already in place, just inline) | M | Pure refactor; raises testability. |
| 8 | Add `frontend/widget/src/telemetry.ts` (console-only, no PII) that emits structured events | S | Hook for later metrics — costs nothing now. |
| 9 | Plan a Next.js admin UI as a stretch goal in [DECISIONS.md](DECISIONS.md) | — | Document the Streamlit ceiling so the team knows it's an explicit trade-off, not an oversight. |

---

## 4. SpecKit Specify Prompt

> **Use:** paste into `/speckit-specify` to (re-)generate the UI feature spec from scratch.
> **Flow:** RISKY — touches widget auth (Phase 7) and admin role gating (Phase 8). Use the 6-command flow with `/speckit-clarify` and `/speckit-analyze`.

```
Build the complete Concierge UI: a public chat widget, a tenant admin dashboard, a
tenant manager dashboard, and shared authentication pages — wired to the existing
Concierge backend. The UI must demonstrate the multi-tenant SaaS product end to end:
platform operators manage tenants without seeing their content, tenant admins manage
only their own tenant, visitors chat through an embedded widget that the backend
gates by signed token and allow-listed origin.

Load-bearing rule (non-negotiable): the frontend NEVER decides tenant identity or
role. Tenant identity always comes from the admin JWT (admin surfaces) or the signed
widget JWT (widget surface). No tenant_id input field, no role picker, no role
override anywhere in the UI.

ARCHITECTURE
- Admin surface: Streamlit single-page dispatcher in admin/streamlit_app.py.
  Auth state lives in st.session_state only — no localStorage, no cookies. Routing
  is by st.query_params["page"] for public flows (accept-invite) and by decoded JWT
  role otherwise.
- Widget surface: React 18 + Vite, rendered inside an iframe injected by
  frontend/widget/public/widget.js. Token kept in a module-scope variable inside
  the iframe — never in localStorage, sessionStorage, or cookies.
- All UI → backend calls use httpx (admin) or fetch (widget). No SQL in any UI
  module. No secret printed to logs. No tenant_id sent in request bodies.
- Current shipped state of the widget is iframe-always-open (no bubble, no
  closed state). This spec adds a bubble launcher + open/closed state machine
  as net-new behavior, not a polish item.

SURFACES & TABS

1. Authentication (public)
   1.1 Login page (admin/login_page.py — already exists, refine)
       - Centered branded card (use admin/brand.py).
       - Inputs: email, password. Button: "Sign in". Link: "Have an invite?".
       - On submit: POST /admin/login. On 200: store token + claims in
         st.session_state and rerun. On 401: show generic "Invalid email or
         password" — never reveal which field failed.
       - Loading spinner while in flight. Disable button to prevent double-submit.
   1.2 Accept Invite page (admin/accept_invite_page.py — already exists, refine)
       - Route: ?page=accept-invite&token=<uuid>.
       - On mount: GET /admin/invites/{token}; show tenant_name, email, role, exp.
         If status != "pending": show terminal banner ("Invite already used" /
         "Invite expired") and disable form.
       - Form: full_name, password, confirm_password. Client-side: min 8 chars,
         ≥1 letter, ≥1 digit, password === confirm. Submit → POST
         /admin/invites/{token}/accept; on 200 auto-login.
   1.3 Access Denied page (admin/access_denied_page.py — already exists)
       - Shown when JWT decodes to an unknown role. Sign out only.

2. Tenant Manager dashboard (visible only when role == "tenant_manager")
   2.1 Overview — KPI cards: total tenants, active tenants, suspended tenants,
       monthly platform cost USD, open audit-flagged actions. Read-only.
   2.2 Tenants — sortable table (name, slug, status, plan, admin email,
       created_at, actions). Actions: Create tenant (modal), Suspend, Trigger
       erasure (with confirmation), View metadata (modal). Never expose
       conversation / lead / CMS content.
   2.3 Invites — table of all invites across tenants (token, email, role,
       tenant_name, status, expires_at). Actions: Invite new admin, Revoke, Resend.
   2.4 Usage & Cost — chart (daily cost) + table (per-tenant total tokens / cost).
       Filter by tenant + date range.
   2.5 Audit Logs — table of platform-level events. Filter by actor, tenant,
       action, date. Detail modal renders the JSON metadata pretty-printed.
   2.6 Settings — non-sensitive operational settings (rate-limit defaults,
       invite TTL). Saving requires confirmation modal.

3. Tenant Admin dashboard (visible only when role == "tenant_admin")
   3.1 Overview — KPI cards: tenant name, widget status, leads (last 30d),
       escalations (open), conversations (last 30d), tokens used, cost USD.
   3.2 CMS Content (admin/cms_page.py — exists) — table (title, slug, status,
       updated_at). Actions: Create, Edit, Publish/Unpublish, Delete. Editor:
       title + body (markdown) + source_url + status. POST/GET /cms/pages.
   3.3 Agent Settings — form: persona name, greeting, tone (dropdown), language
       (dropdown), tenant business rules (textarea). Save → PUT
       /tenants/{tid}/agent-config.
   3.4 Guardrails — list of tenant-editable rules + blocked topics. Read-only
       view of platform guardrails with a "Locked by platform" badge. Tenant
       rules: add / remove blocked topic, choose refusal tone.
   3.5 Widget Settings (admin/widget_page.py — exists) — fields: widget_id
       (read-only), theme JSON (with live preview), greeting (≤280 chars),
       enabled toggle. Copy-snippet button generates the <script> tag.
   3.6 Origin Allowlist (same page or split) — list editor with URL validation.
       Add / remove triggers PUT /widgets/config; the backend audit-logs each
       change.
   3.7 Leads (admin/leads_page.py — exists) — table (created_at, name,
       contact masked, intent, status, score). Filter by status. Read-only.
   3.8 Escalations — table (ticket_id, opened_at, last message excerpt,
       status, assignee). Actions: change status (pending / in-progress /
       resolved), assign. PATCH /escalations/{id}.
   3.9 Usage (admin/usage_page.py — exists) — chart (daily cost), feature
       breakdown table. Read-only. GET /tenants/{tid}/usage.

4. Public widget (visitor)
   Current shipped state: monolithic ChatPane.tsx renders a chat-only UI inside
   an always-open iframe. This spec adds the bubble launcher, panel/message/
   quick-action component split, and the open/closed state machine.
   4.1 Loader (frontend/widget/public/widget.js) — reads data-widget-id and
       data-backend-url from its script tag; idempotent; fail-soft on missing
       attributes; iframe attrs sandbox="allow-scripts allow-same-origin
       allow-forms", referrerpolicy="no-referrer-when-downgrade",
       title="Concierge chat widget".
   4.2 Bubble (Bubble.tsx) — floating button bottom-right, 56×56 px (mobile:
       48×48 px), tenant theme color, ARIA label "Open chat".
   4.3 Panel (Panel.tsx) — slide-up sheet 380×560 px on desktop, full-screen
       on viewports <640 px. Contains: header (tenant logo + greeting + close
       button), message list, quick actions row, input row.
   4.4 Messages (Message.tsx) — user and assistant bubbles, auto-scroll on new,
       citation chips (small links) under RAG answers, "Ticket #<id>" pill under
       escalate replies.
   4.5 Quick actions (QuickActions.tsx) — chip row above input: "View services",
       "Pricing", "Book appointment", "Talk to human". Tapping inserts the
       phrase into the input.
   4.6 States (StatusBanner.tsx)
       - idle: input enabled.
       - sending: input disabled, spinner in last bubble.
       - lead-capture: chat shows "Thanks! We'll be in touch." after
         capture_lead route.
       - escalation: "A human will reach out — ticket #<id>".
       - blocked: friendly refusal text (no internals).
       - error: token-exchange failure → "Widget unavailable" + retry button.
       - session-expired: "Session expired, please reload" + reload button.

DATA FLOW PER REQUEST
- Admin: every fetch goes through admin/_admin_http.py which pulls the JWT
  from st.session_state. On 401 from the backend, clear session and rerun.
- Widget: on iframe boot, POST /widgets/token with widget_id and the parent
  origin (relayed via postMessage from widget.js). Store the returned JWT in a
  module-scope variable. Every POST /chat sends it as Authorization: Bearer.
  On 401: do NOT auto-refresh; show "Session expired" and offer reload.

EDGE CASES
- Empty states: every table must render an explicit empty-state card with an
  illustrative line ("No leads yet — your widget will populate this when
  visitors share contact info") and any relevant primary action.
- Cold start: if a backend endpoint still returns the placeholder shape,
  render sample rows with a visible "(placeholder)" badge — so the demo never
  looks broken.
- Cross-tenant probe: a forged widget JWT (right tenant, wrong origin) is
  rejected server-side; the widget shows the generic "Widget unavailable"
  banner — never reveal which check failed.
- Suspended tenant: widget shows "This business is currently unavailable".
  Admin login for that tenant fails with the same generic 401.
- Origin not in allowlist: widget shows "This widget is not allowed on this
  domain" (UI hint only — backend still returns the indistinguishable 403).
- Slow network: every fetch shows a spinner within 200 ms; admin pages use
  st.spinner; widget uses an inline animated dot.
- Double-submit: every button disables itself while a request is in flight.
- Long messages: chat input enforces a 2000-char cap with a counter.

ACCESSIBILITY
- All inputs have <label> with explicit htmlFor / Streamlit label_visibility.
- Buttons have descriptive ARIA labels when icon-only.
- Widget panel: role="dialog", aria-modal="true", focus trap, ESC closes,
  focus returns to bubble on close.
- Keyboard map: Enter sends, Shift+Enter newline, Tab cycles inputs, ESC
  closes widget, Cmd/Ctrl+K focuses search where applicable.
- Color contrast: WCAG AA minimum (4.5:1 for body text). Tenant theme colors
  pass contrast against white text or auto-fall back.
- Screen reader: live region (aria-live="polite") on chat history so new
  assistant replies are announced.

RESPONSIVENESS
- Admin Streamlit: works on ≥1280 px (laptop) and ≥1024 px (tablet
  landscape). Mobile not in scope.
- Widget desktop (≥640 px): floating bubble + 380×560 panel.
- Widget mobile (<640 px): bubble pinned bottom-right; on open, panel
  becomes a full-screen sheet with safe-area inset padding.
- All KPI grids reflow to a single column under 768 px.

PERFORMANCE
- Widget loader (widget.js) < 5 KB gzipped, ES2019 target, single-file.
- Widget bundle (iframe React app) < 80 KB gzipped on first load; lazy-load
  any non-critical pieces.
- First chat message latency budget: ≤ 200 ms UI response (echo user
  message + spinner) regardless of backend latency.
- Admin pages: every table caps at 100 rows per page; pagination cursor in
  query params.

ERROR HANDLING
- Network error: retry banner with a single click-to-retry. No exponential
  backoff (would mask real outages from the user).
- 401 from admin route: clear session, redirect to login with a banner
  "Your session expired".
- 403 from admin route: show "Not authorized" inline; do NOT redirect.
- 422 with field errors: surface per-field inline messages.
- 5xx: generic "Something went wrong, please try again" — never leak server
  detail or stack trace.
- Widget token exchange failure: "Widget unavailable" + Retry. Do not crash
  the host page. Do not throw.

ANIMATIONS / INTERACTIONS
- Bubble → Panel: scale + fade transition, 180 ms ease-out.
- Message bubble enter: slide-up + fade, 120 ms.
- Quick action tap: 80 ms scale-down feedback.
- KPI card hover: 1 px shadow lift; no rotation.
- All animations respect prefers-reduced-motion (disable transitions).

OUT OF SCOPE
- File uploads, voice input, attachments in the widget.
- Mobile admin UI (Streamlit ceiling).
- A native iOS/Android widget.
- Internationalization beyond the language dropdown in Agent Settings.
- Theming the admin UI per tenant (tenant theme only applies to the widget).
- Billing UI, subscription management, plan upgrades.
- A built-in "live chat" replacing the agent — escalations are async only.
```

---

## 5. SpecKit Plan Prompt

> **Use:** paste into `/speckit-plan` after `/speckit-specify` + `/speckit-clarify` produce a sound spec.md.

```
Produce an implementation plan for the Concierge UI spec (admin Streamlit
dashboard + React widget + shared auth pages). Build incrementally on top of
the existing partial implementation in admin/ and frontend/widget/. Re-use
shipped backend endpoints — do not invent new ones; flag any gap as a
contract change for the owning teammate.

IMPLEMENTATION PHASES
Phase A — Foundations (1 PR, no spec change)
  - Note: admin/_admin_http.py, admin/auth_state.py, admin/brand.py already
    exist — extend, do not re-create.
  - Add NEW shared Streamlit helpers: admin/_table.py, admin/_kpi.py,
    admin/_status_pill.py, admin/_empty.py.
  - Extend (not create) admin/brand.py with COLORS / SPACING / RADIUS constants
    alongside the existing PRODUCT_NAME / PRODUCT_TAGLINE.
  - Add NEW frontend/widget/src/tokens.css with CSS custom properties.
  - Add NEW frontend/widget/src/telemetry.ts (console-only no-op stub).
  Risks: low. Backwards-compatible refactor only.

Phase B — Auth UX polish (1 PR)
  - Refine admin/login_page.py: loading state, generic error, link to invite.
  - Refine admin/accept_invite_page.py: pre-mount invite preview, terminal
    banner for non-pending status, post-accept auto-login.
  - admin/access_denied_page.py: copy + sign-out only.
  Risks: low. Uses existing endpoints.

Phase C — Tenant Admin dashboard completion (3 PRs)
  - PR1: Overview + Usage refinement using shared KPI helper.
  - PR2: Agent Settings page (NEW endpoint needed: PUT /tenants/{tid}/agent-config
    — flag Nasser to confirm contract). Guardrails page reads platform rules
    via a NEW read endpoint (flag Ayoub).
  - PR3: Escalations page (NEW endpoint needed: PATCH /escalations/{id} —
    flag Nasser).
  Risks: medium. Three new backend endpoints; mock until live.

Phase D — Tenant Manager dashboard completion (2 PRs)
  - PR1: Tenants table + create/suspend/erase actions (consumes existing
    /tenants/* legacy routes; confirm with Hiba whether to migrate to
    admin-JWT-gated equivalents).
  - PR2: Invites table + revoke/resend; Audit Logs platform-scope view;
    Settings page.
  Risks: medium. Must NOT leak tenant content into manager views — assert
  with integration tests.

Phase E — Widget polish (2 PRs)
  - PR1: Componentize ChatPane.tsx (currently 231 LOC, monolithic) into
    Bubble / Panel / Message / QuickActions / StatusBanner. Extract
    useChatReducer from the existing inline state machine.
    Adds the bubble launcher (NEW UX state — widget is currently always-open).
    Wires open/closed state machine in the iframe; widget.js loader still
    mounts the iframe but the panel renders collapsed-to-bubble by default.
  - PR2: Accessibility pass — role="dialog", aria-modal, focus trap, ESC
    handler, focus return to bubble on close, keyboard map, reduced-motion.
    Responsive breakpoints (mobile sheet mode below 640 px).
  Risks: medium. Visible UI change; existing vitest tests in
  __tests__/api.test.ts (storage discipline) and __tests__/chat.test.tsx
  (UI + edge cases) must keep passing after the reshape.

Phase F — Cross-cutting QA + demo seed (1 PR)
  - Demo seed script populates 2 tenants × N pages × N leads × N escalations.
  - Update tests/smoke/test_cross_tenant_e2e.py with widget-UI assertions
    (Playwright optional; skip if heavy).
  - Update RUNBOOK.md demo flow.
  Risks: low. Mostly docs + seed.

FILE STRUCTURE (deltas)
  admin/
    _admin_http.py            (exists)
    _table.py                 (new)
    _kpi.py                   (new)
    _status_pill.py           (new)
    _empty.py                 (new)
    brand.py                  (extend: design tokens)
    auth_state.py             (exists)
    streamlit_app.py          (dispatcher; extend sidebar)
    login_page.py             (refine)
    accept_invite_page.py     (refine)
    access_denied_page.py     (exists)
    platform_dashboard_page.py (extend: full TM dashboard)
    tenant_dashboard.py       (new dispatcher for TA tabs)
    overview_page.py          (new — TA + TM share via role param)
    cms_page.py               (exists; refine table)
    agent_settings_page.py    (new)
    guardrails_page.py        (new)
    widget_page.py            (exists; refine theme preview)
    leads_page.py             (exists)
    escalations_page.py       (new)
    usage_page.py             (exists)
    tenants_page.py           (new — TM)
    invites_page.py           (new — TM)
    audit_page.py             (new — TM)
    settings_page.py          (new — TM)

  frontend/widget/src/
    main.tsx                  (orchestrator; thin)
    api.ts                    (exists)
    tokens.css                (new)
    telemetry.ts              (new)
    state/useChatReducer.ts   (new)
    components/
      Bubble.tsx              (new)
      Panel.tsx               (new)
      Message.tsx             (new)
      QuickActions.tsx        (new)
      StatusBanner.tsx        (new)
      EmptyState.tsx          (new)
    a11y/
      FocusTrap.tsx           (new)

COMPONENT HIERARCHY (widget)
  <App>
    <Bubble onClick={open}/>            // when closed
    <Panel onClose={close}>             // when open, dialog role
      <FocusTrap>
        <Header/>
        <StatusBanner state={…}/>
        <MessageList>
          <Message/>... (live region)
        </MessageList>
        <QuickActions/>
        <InputRow/>
      </FocusTrap>
    </Panel>

BACKEND vs FRONTEND RESPONSIBILITIES
- Frontend renders, validates client-side (UX), and shows feedback.
- Backend is the source of truth for: tenant identity, role, allowed
  origins, content, and all authorization decisions.
- Anything sensitive the UI claims (suspended tenant, blocked origin,
  invalid invite) is also enforced server-side. UI hints are convenience,
  not security.

DATABASE / SCHEMA CHANGES
- None for Phases A, B, E, F.
- Phase C may require: tenant_agent_configs row (already in migration 0004)
  surfaced via Nasser's new endpoint.
- Phase C escalations: escalation_tickets table (already in migration 0004)
  surfaced via Nasser's new PATCH endpoint.
- No new tables. No new migrations owned by Amer.

API CONTRACTS (six endpoints, all confirmed MISSING; flagged to owners)
- PUT /tenants/{tid}/agent-config           [Nasser]
    Model already exists: TenantAgentConfig in app/db/models.py.
    Needs: repo + service + route. Half the work is done.
- GET /tenants/{tid}/platform-guardrails    [Ayoub] (read-only metadata)
    No model, no route. Likely a thin read of guardrails/main.py state.
- PATCH /escalations/{id}                   [Nasser]
    Model already exists: EscalationTicket in app/db/models.py.
    Needs: repo + service + route.
- PUT /tenants/{tid}/settings               [Hiba] (TM-scope)
    No model yet. Scope of "settings" needs Hiba's confirmation before spec.
- POST /admin/invites/{token}/revoke        [Amer + Hiba review]
    No route in app/api/routes/admin_invites.py. Repo has the row; add a
    revoked_at column + service method.
- POST /admin/invites/{token}/resend        [Amer + Hiba review]
    No route. Re-mints token + extends expiry on the existing invite row.
Mock all six in the admin UI until the owning teammate ships; render with
(placeholder) badge so the demo never looks broken.

TESTING STRATEGY
- Admin: Streamlit AppTest harness per page (already used). Mock httpx via
  httpx.MockTransport. Test: happy path, placeholder fallback, 401 → logout,
  403 → inline error, 422 → field errors.
- Widget: vitest component tests with mocked fetch. Test: token exchange
  failure → "Widget unavailable"; 401 → "Session expired"; ESC closes;
  focus trap; no token in localStorage/cookies/sessionStorage.
- E2E: extend tests/smoke/test_cross_tenant_e2e.py with widget-UI
  assertions (Playwright optional).
- Accessibility: axe-core in vitest for widget; manual keyboard pass for
  admin.
- Performance: lighthouse-ci budget check on the widget bundle in CI.

MIGRATION / REFACTOR STRATEGY
- Phase A is a pure-refactor PR — no behavior change. Get it merged first
  so every subsequent phase uses the shared helpers.
- Phase E reshape of main.tsx ships behind no flag (the widget is not yet
  production-traffic); old code is replaced wholesale in one PR with vitest
  coverage.
- Streamlit dispatcher (streamlit_app.py) extends incrementally — each new
  page lands behind a sidebar entry that only renders for the right role.

RISKS & DEPENDENCIES
- Streamlit ceiling: dashboards may feel less polished than a Next.js
  equivalent. Documented as accepted trade-off in DECISIONS.md.
- Three new endpoints from Nasser (agent config, escalation patch, etc.)
  may slip — mocks ensure UI work isn't blocked.
- Theme JSON live preview risk: untrusted JSON parsing must be sandboxed
  (parse + validate schema before rendering — never eval / inject).
- Focus trap correctness: rely on a small audited helper (do not pull
  focus-trap-react if a 30-line implementation suffices).
- Bundle size budget: Vite tree-shake must stay aggressive; verify with
  vite-plugin-visualizer in CI.

IMPLEMENTATION ORDER
  1. Phase A (foundations, 1 PR)
  2. Phase B (auth UX, 1 PR)
  3. Phase E PR1 (widget componentization) — parallel with B
  4. Phase C PR1 (Overview + Usage refinement) — parallel with B
  5. Phase E PR2 (widget a11y + responsive)
  6. Phase C PR2 (Agent Settings + Guardrails — mocked until backend)
  7. Phase D PR1 (Tenants page)
  8. Phase D PR2 (Invites + Audit + Settings)
  9. Phase C PR3 (Escalations — mocked until backend)
  10. Phase F (seed + RUNBOOK + smoke extension)

VALIDATION / CHECKPOINTS
- After each PR: `ruff check .`, `mypy app/`, `pytest`, `docker compose build`
  all green.
- After Phase A: every existing admin page still renders identically — no
  visible regression.
- After Phase B: a fresh invite → accept → auto-login round-trip works in
  under 30 s.
- After Phase E: widget passes axe-core a11y check with zero violations;
  bundle ≤ 80 KB gzipped; loader ≤ 5 KB gzipped.
- After Phase C/D: TM dashboard cannot fetch any /cms/pages, /leads,
  /conversations, or /chat-history endpoint — assert in an integration test
  that gives a TM JWT and verifies 403 on each.
- After Phase F: a fresh clone + docker compose up + RUNBOOK demo flow
  completes end-to-end without manual fixups.

DEFINITION OF DONE (UI feature)
- All P0 build items from Concierge_UI_Blueprint.md §11 are live and
  demoable.
- The five §10 minimal demo flow scenarios all pass on the live stack.
- No widget token in localStorage / cookies / sessionStorage (verified by
  vitest).
- No torch / transformers in any image (Constitution Principle V).
- DECISIONS.md updated for any non-trivial choice (Streamlit ceiling,
  state-machine reducer, mock-until-live pattern).
- CLAUDE.md "Active Spec-Kit Feature" pointer updated if a new spec is
  opened for the UI work.
```

---

## 6. Pre-Merge Checklist (UI work specifically)

Paste into the PR description for any UI PR derived from this spec.

```
- [ ] No tenant_id input field anywhere in the UI
- [ ] No role picker anywhere in the UI
- [ ] No widget token in localStorage / cookies / sessionStorage (vitest assertion)
- [ ] No admin JWT outside st.session_state
- [ ] Every fetch error path tested (401 / 403 / 422 / 5xx / network)
- [ ] Every table has an empty-state component
- [ ] Every page has a (placeholder) badge fallback for not-yet-live endpoints
- [ ] Widget axe-core check: 0 violations
- [ ] Widget bundle ≤ 80 KB gzipped; loader ≤ 5 KB gzipped
- [ ] Tenant Manager cannot fetch tenant content endpoints (integration test)
- [ ] Tenant Admin cannot fetch other tenants (integration test)
- [ ] prefers-reduced-motion respected
- [ ] WCAG AA contrast verified on tenant theme colors (with fallback)
- [ ] DECISIONS.md updated if a non-trivial UI decision was made
- [ ] PR tagged for Hiba (any tenant_id / role / RLS impact) or Ayoub
      (any guardrail / secret / origin impact)
```
