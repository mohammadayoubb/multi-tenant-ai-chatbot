# Feature Specification: Concierge UI

**Feature Branch**: `009-concierge-ui`
**Created**: 2026-05-29
**Status**: Draft
**Input**: User description: "Build the complete Concierge UI: a public chat widget, a tenant admin dashboard, a tenant manager dashboard, and shared authentication pages — wired to the existing Concierge backend. Load-bearing rule: the frontend NEVER decides tenant identity or role."

## Clarifications

### Session 2026-05-29

- Q: Where do the widget quick-action chips come from? → A: Per-tenant, configured by the tenant admin in Agent Settings (one-per-line list, max 6); product seeds the four defaults on tenant creation.
- Q: How is an escalation ticket assigned to an owner? → A: From a drop-down listing the signed-in tenant's own admin users (sourced from a new tenant-scoped admin-users read endpoint).
- Q: Does the widget chat history persist when the visitor closes and reopens the bubble? → A: Yes within the same page lifetime (in-memory only); a page navigation or refresh resets the conversation.
- Q: Is lead export (CSV / download) in scope for v1? → A: No — out of scope; Leads tab remains read-only on-screen only.
- Q: Can a tenant admin view the audit log for their own tenant? → A: Yes — a read-only Audit tab scoped to the signed-in tenant only, reusing the existing tenant-scoped audit-log endpoint.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visitor chats with the embedded widget (Priority: P1)

A visitor lands on a tenant's public website, opens the floating chat bubble in the bottom-right corner, and asks a question. The widget greets them with the tenant's configured greeting, answers FAQ questions from the tenant's own content, captures contact info when the visitor expresses sales intent, escalates to a human when asked, and refuses unsafe prompts — all without ever exposing another tenant's data or letting the visitor influence which tenant they are talking to.

**Why this priority**: The widget is the only surface a paying customer's end-users actually touch. Without it, the product has no visible value. Every other surface (admin, manager) exists to configure or observe this one.

**Independent Test**: A reviewer can drop the widget script tag onto a static HTML page hosted on an allow-listed domain, open it in a browser, exchange the four canonical message types (FAQ, sales, human-request, unsafe), and confirm each produces the expected reply category and side-effect (no side-effect / lead row / ticket / refusal). Cross-tenant probe (forged token) must produce a generic "widget unavailable" response with no leak of which check failed.

**Acceptance Scenarios**:

1. **Given** a host page on an allow-listed origin, **When** the visitor opens the widget and asks an FAQ question, **Then** the widget returns an answer drawn only from that tenant's content within 3 seconds and shows source chips for any cited content.
2. **Given** a visitor in the middle of a chat, **When** they ask "Can I get a quote? My email is jane@example.com", **Then** the widget acknowledges with a friendly capture confirmation and a new lead row appears in the tenant admin's Leads tab attributed to that tenant only.
3. **Given** a visitor asks "Can I speak to a person?", **When** the widget routes to escalation, **Then** the chat shows a ticket pill and a corresponding open escalation appears for the tenant admin.
4. **Given** an attacker forges a widget session token claiming a different tenant or an origin not in the allow-list, **When** the widget attempts to send a message, **Then** the widget displays a generic "Widget unavailable" message indistinguishable from a missing-widget or rate-limited case.
5. **Given** the visitor's session token has expired, **When** they submit another message, **Then** the widget displays "Session expired, please reload" and disables input — no silent reauthentication.
6. **Given** the visitor is on a mobile viewport (< 640 px), **When** they tap the bubble, **Then** the chat opens as a full-screen sheet rather than a fixed-size panel.

---

### User Story 2 - Tenant admin configures their own tenant (Priority: P1)

A business owner (tenant admin) signs in, lands on an overview that shows their widget status, conversation/lead/escalation totals, and usage. They can edit CMS content, change the agent persona and greeting, tune tenant guardrails, edit widget appearance and the origin allow-list, work through new leads and open escalations, and review usage — restricted at every turn to their own tenant.

**Why this priority**: Without this surface, a tenant cannot self-serve and the product becomes a consulting deliverable instead of SaaS. This is the surface most demoed to prospects.

**Independent Test**: A reviewer signs in as a seeded tenant admin, walks through every tab, makes one change per writable tab (add CMS page, edit greeting, add origin, change escalation status), signs out, signs back in, and confirms each change persisted. Then signs in as a second tenant admin and confirms none of the first tenant's data is visible.

**Acceptance Scenarios**:

1. **Given** a signed-in tenant admin, **When** they add an origin to the allow-list and save, **Then** a widget hosted on that new origin can immediately obtain a token, and the previous origin still works.
2. **Given** a signed-in tenant admin, **When** they remove an origin and save, **Then** a widget hosted on the removed origin can no longer obtain a token.
3. **Given** a signed-in tenant admin, **When** they create a new CMS page and publish it, **Then** the widget begins answering related FAQ questions from that content within the documented indexing window.
4. **Given** a signed-in tenant admin viewing their Overview, **When** the page renders, **Then** every KPI displays only data belonging to their tenant and no record from another tenant is reachable from any tab.
5. **Given** a tenant admin's session expires mid-session, **When** they take their next action, **Then** they are returned to the login page with a "Your session expired" banner — they are never auto-logged into another tenant.

---

### User Story 3 - Tenant manager runs the platform without seeing tenant content (Priority: P2)

A platform operator (tenant manager) signs in, lands on a platform overview, provisions a new tenant, invites that tenant's first admin, monitors aggregate usage and cost across tenants, and reviews dangerous-action audit logs. They can suspend or trigger erasure for a tenant, but at no point can they read that tenant's conversations, leads, or CMS content.

**Why this priority**: This is the SaaS-operations surface. Critical for proving the platform model and audit story, but secondary for a single-tenant demo. P2 because the demo can land with tenant admin and widget alone.

**Independent Test**: A reviewer signs in as the tenant manager, provisions a new tenant, issues an invite, watches the invited admin complete the accept flow, then verifies (a) the new tenant appears in the Tenants table with correct metadata, (b) the manager cannot navigate to any CMS / Leads / Escalations / Conversations endpoint for that tenant via any UI path, (c) every administrative action (provision, invite, suspend, erase) appears in the Audit Logs.

**Acceptance Scenarios**:

1. **Given** a signed-in tenant manager, **When** they create a tenant and issue an invite, **Then** the invite link, when opened, allows the recipient to set a password and immediately land on their tenant admin dashboard for the correct tenant.
2. **Given** a signed-in tenant manager, **When** they suspend a tenant, **Then** the next widget token request for that tenant returns "this business is currently unavailable" and the suspension is recorded in the audit log.
3. **Given** a signed-in tenant manager, **When** they view the Usage & Cost tab, **Then** the breakdown shows totals per tenant but never exposes individual conversations, leads, or page content.
4. **Given** a signed-in tenant manager, **When** they attempt to fetch any tenant-content endpoint through the UI, **Then** every navigation path declines — no tab, modal, or detail view surfaces conversations, leads, or CMS bodies.

---

### User Story 4 - Bubble launcher and unified visual identity (Priority: P3)

The widget today is always-open and visually unmounted from the host page; the admin pages have only a minimal centered card on auth pages. This story adds the bubble launcher / open-close UX, shared empty states, status pills, and a small design-token system so the product looks and feels coherent across surfaces. Accessibility and responsiveness baselines (focus trap, ESC, keyboard map, mobile sheet, reduced-motion, WCAG AA contrast) ship as part of this story.

**Why this priority**: P3 because every prior story is functional without it — but without this story the product feels rough, mobile is broken, and assistive-tech users cannot use the widget at all.

**Independent Test**: A reviewer audits the widget with an a11y tool, navigates the entire chat with only the keyboard, and confirms the bubble→panel→close cycle, focus return, and ESC behavior. The same reviewer resizes the browser to 360 px wide and confirms the widget reflows to full-screen. They turn on prefers-reduced-motion and confirm transitions are disabled.

**Acceptance Scenarios**:

1. **Given** the widget script is embedded, **When** the page loads, **Then** only a 56×56 bubble appears bottom-right — no panel until the bubble is activated.
2. **Given** the widget panel is open, **When** the user presses Escape, **Then** the panel closes and keyboard focus returns to the bubble.
3. **Given** a viewport narrower than 640 px, **When** the user opens the widget, **Then** the panel occupies the full viewport with safe-area insets respected.
4. **Given** the user has set prefers-reduced-motion, **When** the widget opens or a message arrives, **Then** no scale/fade transitions play.
5. **Given** a tenant admin table is empty, **When** the page loads, **Then** an explanatory empty-state card appears with one short sentence describing what populates the table.
6. **Given** the visitor has sent and received several chat messages, **When** they close the panel and reopen the bubble on the same page, **Then** the full conversation is still visible and the same session continues; **When** they instead refresh the page, **Then** the conversation resets to an empty greeting.

---

### Edge Cases

- **Cold start with no live backend data**: every read-only admin page shows a visible "(placeholder)" badge with sample rows so the demo does not look broken.
- **Forged token / wrong origin**: every refusal cause (unknown widget, origin mismatch, rate-limited) collapses to one indistinguishable response so attackers cannot enumerate.
- **Suspended tenant**: widget shows "this business is currently unavailable"; admin login for that tenant fails with the same generic 401 used for all auth failures.
- **Origin not in allow-list**: widget shows a friendly "this widget is not allowed on this domain" hint but the backend response is the same indistinguishable refusal.
- **Slow backend**: every fetch shows a loading indicator within 200 ms (spinner on admin; animated dots in chat).
- **Double-submit**: every button disables itself while a request is in flight; chat input rejects a second Enter while a reply is pending.
- **Long visitor message**: chat input caps at 2 000 characters and shows a counter; messages over the cap cannot be sent.
- **Empty table**: every list view renders an explicit empty-state card with a one-line explanation of what will populate it.
- **Unsupported role on JWT**: user lands on an "Access denied" page with a sign-out action; no dashboard is rendered.
- **Theme JSON typo**: invalid theme JSON is rejected with an inline error; the widget keeps its last-known-good theme.
- **Browser without JavaScript**: widget shows nothing on the host page (fail-soft); admin surface refuses to render and tells the user to enable JavaScript.

## Requirements *(mandatory)*

### Functional Requirements

#### Cross-cutting

- **FR-001**: The frontend MUST NOT decide tenant identity or role under any path — tenant and role MUST always be derived from a backend-issued admin session token or widget session token.
- **FR-002**: The UI MUST NOT expose any input field that accepts a tenant identifier, role, or signing secret from the user.
- **FR-003**: Session tokens MUST live only in memory while the surface is open and MUST NOT be written to browser persistent storage of any kind.
- **FR-004**: Every UI surface MUST refuse to render past the login boundary when the session token is missing, malformed, or rejected by the backend.
- **FR-005**: When the backend returns an authentication failure during use, the UI MUST clear in-memory session state and route the user to the appropriate entry point (login for admin, "Session expired" notice for widget) without auto-reauthentication.
- **FR-006**: Every action that produces a side-effect MUST disable its trigger control while the request is in flight to prevent double-submission.
- **FR-007**: Every list view MUST render an explicit empty-state explanation when no rows exist, distinct from the loading state.
- **FR-008**: Every read-only view that depends on a backend endpoint not yet returning real data MUST display a visible "(placeholder)" indicator so observers know they are not looking at production data.

#### Authentication

- **FR-010**: The login surface MUST authenticate a user by email and password and MUST collapse every failure cause (unknown email, wrong password, suspended account, unknown role) to a single indistinguishable error message.
- **FR-011**: A successful login MUST route the user to the dashboard appropriate to their backend-issued role; an unknown role MUST land on an "Access denied" page with only a sign-out action.
- **FR-012**: The invite-acceptance surface MUST display the inviting tenant's name, the invitee's email, and the assigned role before asking for a password — and MUST NOT let the invitee change any of those values.
- **FR-013**: The invite-acceptance surface MUST refuse to render the password form when the invite status is not "pending" (already used / expired / unknown) and MUST show the reason.
- **FR-014**: The invite-acceptance form MUST enforce a minimum password strength (≥ 8 characters, at least one letter and one digit, and confirm-password match) before submission.
- **FR-015**: A successful invite acceptance MUST auto-sign-in the new admin and route them to their tenant's dashboard with no further credential prompt.

#### Tenant Admin dashboard

- **FR-020**: The tenant-admin surface MUST display a per-tenant overview with at minimum: tenant name, widget status, last-30-day lead count, open escalation count, last-30-day conversation count, and aggregated usage / cost.
- **FR-021**: The CMS tab MUST support listing, creating, editing, publishing/unpublishing, and deleting tenant content; every operation MUST be scoped to the signed-in tenant only.
- **FR-022**: The Widget Settings tab MUST allow the tenant admin to edit greeting (≤ 280 characters), theme, and enabled flag, and MUST provide a copy-snippet control that produces the embed code for that tenant's widget.
- **FR-023**: The Origin Allow-list tab MUST allow add and remove of valid URLs; every change MUST be persisted only after a successful save and MUST be recorded in that tenant's audit log.
- **FR-024**: The Leads tab MUST display captured leads in read-only form with contact information masked (first three characters visible, remainder obscured) and MUST allow filtering by status. The Leads tab MUST NOT provide an export, download, or copy-all action in this version.
- **FR-025**: The Escalations tab MUST allow a tenant admin to change ticket status (pending / in-progress / resolved) and assign an owner selected from a drop-down of the signed-in tenant's own admin users. Free-text assignees MUST NOT be accepted. Every status change and assignee change MUST be recorded in that tenant's audit log.
- **FR-026**: The Agent Settings tab MUST allow editing persona name, greeting, tone, language, free-text business rules, and the tenant's quick-action chip list (one phrase per line, maximum 6) — and only those fields. On tenant creation, the chip list is seeded with four product defaults that the tenant admin may edit or replace.
- **FR-027**: The Guardrails tab MUST present platform guardrails as read-only with a clear "locked by platform" indicator and MUST allow tenant-editable rules only for tenant-scoped policies.
- **FR-028**: The Usage tab MUST display daily cost, total tokens, and feature breakdown — read-only — for the signed-in tenant only.
- **FR-029**: No tenant-admin tab MUST surface another tenant's data, including in modals, search results, or detail views.
- **FR-030**: The tenant-admin surface MUST provide a read-only Audit tab that lists audit events for the signed-in tenant only, filterable by actor, action, and date. The tab MUST display origin allow-list changes, escalation status and assignee changes, CMS publish/unpublish events, and Widget Settings changes. The tab MUST NOT surface audit events from any other tenant or any platform-manager action.

#### Tenant Manager dashboard

- **FR-040**: The tenant-manager surface MUST display a platform overview with totals for tenants, active tenants, suspended tenants, monthly platform cost, and open audit-flagged actions.
- **FR-041**: The Tenants tab MUST allow create, suspend, and erasure actions; suspend and erasure MUST require an explicit confirmation step.
- **FR-042**: The Invites tab MUST allow issuing a new admin invite, revoking an outstanding invite, and resending an invite, and MUST display invite status and expiry.
- **FR-043**: The Usage & Cost tab MUST display aggregate usage per tenant with date and tenant filters and MUST NOT expose individual conversations, leads, or CMS content.
- **FR-044**: The Audit Logs tab MUST display platform-level events filterable by actor, tenant, action, and date, and MUST allow inspecting metadata in a detail view.
- **FR-045**: The Settings tab MUST allow editing only platform-level non-sensitive operational settings and MUST require a confirmation step on save.
- **FR-046**: No tenant-manager surface MUST allow navigation to, fetch of, or display of any tenant's conversation, lead, or CMS content — regardless of role flag or query parameter.

#### Public widget

- **FR-060**: The widget MUST display a floating launcher in the bottom-right of the host page; the chat panel MUST be hidden until the launcher is activated.
- **FR-061**: The widget MUST obtain a session token from the backend by presenting its widget identifier and the host-page origin; the token MUST be kept only in memory.
- **FR-062**: The widget MUST send every chat request with its in-memory session token; on rejection of the token, it MUST surface "session expired, please reload" and disable input — it MUST NOT silently reauthenticate.
- **FR-063**: The widget MUST render the tenant's configured greeting, theme color, and persona on first open.
- **FR-064**: The widget MUST present quick-action chips above the input, sourced from the signed-in tenant's Agent Settings chip list (zero to six chips). Activating a chip MUST insert its text into the input. When the tenant's chip list is empty, no chip row MUST be rendered.
- **FR-065**: The widget MUST distinctly render: idle, sending, lead-captured, escalation (with ticket reference), blocked-by-guardrails, error, and session-expired states.
- **FR-066**: The widget MUST present a clickable source reference under any answer that cites tenant content.
- **FR-067**: The widget MUST cap chat input at 2 000 characters and display a counter as the limit approaches.
- **FR-068**: The widget MUST fail-soft on any boot error: it MUST NOT throw to the host page, MUST log a single console error, and MUST NOT mount duplicate launchers if loaded twice on the same page.
- **FR-069**: On viewports narrower than 640 px the widget panel MUST occupy the full viewport with safe-area inset padding; on wider viewports it MUST appear as a fixed-size sheet anchored to the launcher.
- **FR-070**: The widget MUST preserve chat history and the active session identifier across close-and-reopen of the panel within the same page lifetime. A page navigation or full refresh MUST reset both — no persistent storage MUST be used to extend history beyond the page lifetime.

#### Accessibility

- **FR-080**: Every form field MUST have a visible or programmatically associated label; icon-only buttons MUST have an accessible name.
- **FR-081**: The widget panel MUST be presented as a modal dialog: it MUST trap keyboard focus, MUST close on Escape, and MUST return focus to the launcher on close.
- **FR-082**: The chat history MUST be announced to assistive technology as new assistant messages arrive without stealing focus.
- **FR-083**: Body text contrast MUST meet WCAG AA (≥ 4.5:1); when the tenant theme color cannot meet that ratio against widget chrome, the surface MUST fall back to an accessible default.
- **FR-084**: When the user prefers reduced motion, all UI transitions MUST be disabled or reduced to instant.
- **FR-085**: The visitor MUST be able to compose, send, and review a complete chat using only the keyboard.

### Key Entities

- **Admin session**: a backend-issued credential that names a single user, their role (tenant_admin or tenant_manager), and (for tenant_admin) the tenant they administer. Held in memory only.
- **Widget session**: a backend-issued credential that names a single tenant, widget, host origin, and chat session. Held in memory only inside the widget iframe.
- **Tenant**: a business customer of the platform, identified by name and slug, with a status (active / suspended), plan, and creation date.
- **Invite**: a one-time, time-limited credential that allows a recipient to create an admin account for a specified tenant and role.
- **CMS page**: a unit of tenant content with title, slug, body, source URL, and publish status — used to answer visitor questions.
- **Lead**: a record of visitor contact information captured by the widget, attributed to the tenant whose widget captured it.
- **Escalation**: a request originated by the widget for a human to follow up on a chat, with status (pending / in-progress / resolved) and optional assignee (referencing an admin user of the same tenant).
- **Audit event**: a record of a privileged action (tenant create / suspend / erase, invite issue / revoke, widget origin change, ticket status change) with actor, tenant, action, and metadata.
- **Widget configuration**: the per-tenant settings that govern widget appearance, greeting, allowed origins, and enabled state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A visitor can complete an end-to-end FAQ exchange (open widget → ask question → receive cited answer) on a desktop browser in under 15 seconds, with the first feedback (echo + loading indicator) appearing within 200 ms of pressing send.
- **SC-002**: A tenant admin can land on their dashboard, navigate to Widget Settings, copy the embed snippet, and deploy it onto a new allow-listed origin in under 5 minutes starting from receiving the invite email.
- **SC-003**: In a side-by-side review across at least two seeded tenants, a tenant admin cannot reach a single record (CMS, lead, escalation, conversation, usage) belonging to the other tenant via any UI path — verified by negative-test traversal of every tab and detail view.
- **SC-004**: A tenant manager cannot reach a single record of tenant-private content (CMS body, lead detail, conversation, individual escalation message) through any UI path while still being able to operate every platform-level action — verified by the same negative-test traversal.
- **SC-005**: The widget passes an automated accessibility scan with zero "serious" or "critical" violations, and a keyboard-only operator can complete an FAQ exchange end-to-end without using a pointer device.
- **SC-006**: On a viewport ≤ 360 px wide, the widget opens as a full-screen sheet without horizontal scrolling and remains operable; on a viewport ≥ 1280 px the admin dashboard renders without overflow or clipping.
- **SC-007**: 95% of admin pages render their first paint within 1 second of navigation on a baseline laptop connected to a local backend; the widget script and bundle load to interactive within 2 seconds on a standard 4G profile.
- **SC-008**: In a cross-tenant red-team drill, no widget-side action — including forged token, wrong origin, suspended tenant — reveals which check rejected the request; every refusal collapses to an indistinguishable user-visible message.
- **SC-009**: At least 95% of attempts to complete the four canonical visitor flows (FAQ, lead capture, human escalation, refusal of cross-tenant probe) produce the expected category of response in a recorded demo run.
- **SC-010**: Every privileged action taken from the tenant-manager surface (tenant create, suspend, erase, invite issue, invite revoke) results in a corresponding entry visible in the Audit Logs tab within the same session.

## Assumptions

- The backend already provides the authentication, widget-token, chat, CMS-create, leads, audit-log, and usage endpoints documented in the project contract. A set of further endpoints (agent-config read/write — including the quick-action chip list, platform-guardrails read, escalation list and status PATCH — including the assignee, tenant-settings update, invite revoke and resend, tenant-scoped admin-users list, CMS edit / publish / delete, and platform-scope tenants / audit-logs reads) is confirmed missing and will be supplied by the responsible teammates. The authoritative inventory and shapes live in [contracts/missing-endpoints.md](contracts/missing-endpoints.md); the UI renders placeholder fallbacks for each until they ship.
- The admin surfaces are delivered as a single dispatcher application that routes by signed-in role; mobile support for admin surfaces is out of scope (admin works on laptop / tablet-landscape only). The widget is delivered as an embeddable application loaded by a small script tag.
- The widget is mounted via a small loader script on the tenant's website; today the loader mounts the chat surface always-open at fixed size, and adding a bubble launcher with an open/closed state is part of this work, not a polish item.
- Tenant theming applies only to the widget; the admin surfaces share one neutral product theme.
- A single user-interface language is supported beyond the language selector inside agent settings; internationalization of the UI chrome is out of scope.
- No billing or subscription UI is in scope; cost views are observational only.
- File uploads, voice input, message attachments, and native mobile widgets are out of scope.
- Lead export (CSV / JSON / clipboard) is out of scope for v1; tenant admins consume leads through the on-screen Leads tab only.
- Token discipline (no browser persistent storage) is enforced by automated test in the widget and is treated as a non-negotiable invariant in every iteration.
- Empty-state and (placeholder) treatment is used to keep the demo presentable when a downstream endpoint has not yet shipped; placeholder rows are always visually distinct from real data.
- Authentication failures, origin failures, and rate-limit failures collapse to indistinguishable user-visible responses on the widget surface to prevent enumeration; the same anti-enumeration property already applies to the admin login.
