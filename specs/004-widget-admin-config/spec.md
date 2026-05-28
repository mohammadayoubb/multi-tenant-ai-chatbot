# Feature Specification: Tenant Admin Widget Configuration Page

**Feature Branch**: `004-widget-admin-config`
**Created**: 2026-05-27
**Status**: Draft
**Input**: User description: "Build the tenant_admin widget configuration page. Tenant admins manage their widget: allowed origins (used by the platform's origin allowlist during token exchange), greeting text, an enabled flag, and a theme. Every change to the origin allowlist is audited via Hiba's add_audit_log function. Backend: GET /widgets/config and PUT /widgets/config under tenant_admin role; service + tenant-scoped repository function. Frontend: a Streamlit admin page with origins editor, theme editor with preview, greeting input, enabled toggle, save. Out of scope: other admin pages, JWT key rotation, bulk import."

## Clarifications

### Session 2026-05-27

- Q: When an admin removes an origin, how are JWTs already issued for that origin handled? → A: Passive expiry via the existing short JWT TTL (no new denylist, no session-revocation channel; tenants needing immediate hard-stop use the `enabled = false` toggle instead).
- Q: How quickly must origin-allowlist changes propagate to the token endpoint? → A: Live read from `widget_configs` on every token request (no cache, no invalidation step). Propagation is effectively immediate.
- Q: What schema applies to the theme JSON value? → A: Free-form JSON blob; only "must parse as JSON" is enforced now. The strict schema (palette, font, position, etc.) lands together with the widget runtime's theme support in a later phase.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tenant admin updates the widget's allowed origins (Priority: P1)

A tenant administrator (e.g., the business's web ops person) needs to add their production website's origin to the widget allowlist so that the embed snippet on that site will be accepted by the platform's token endpoint. They open the admin Widget page, type the new origin, click Add, then Save. The platform records the change in the audit log, and from that moment the widget on the new origin can successfully exchange tokens.

**Why this priority**: This is the **only** way a tenant can ship the widget on a real website. Without an origin editor a tenant cannot self-serve onto new domains — every new domain becomes a support ticket. Origin allowlist accuracy also directly governs the platform's tenant-isolation guarantee at the widget-auth boundary (an origin in tenant A's allowlist must never accidentally appear in tenant B's, and removals must take effect promptly).

**Independent Test**: A tenant admin logs into the admin UI, navigates to the Widget tab, adds a new origin string, removes an existing one, and clicks Save. Two audit log entries are written (`widget.origin_added`, `widget.origin_removed`). A token exchange from the new origin succeeds; a token exchange from the removed origin fails.

**Acceptance Scenarios**:

1. **Given** a tenant admin viewing the Widget page with current allowed origins `["https://acme.com"]`, **When** they add `https://blog.acme.com` and click Save, **Then** the widget config row's `allowed_origins` is updated to include both, and exactly one `widget.origin_added` audit log entry is recorded with the new origin in its metadata.
2. **Given** a tenant admin viewing the Widget page with `["https://acme.com", "https://blog.acme.com"]`, **When** they remove `https://blog.acme.com` and click Save, **Then** the widget config is updated and exactly one `widget.origin_removed` audit log entry is recorded.
3. **Given** a tenant admin with the widget `enabled` flag set to `true`, **When** they remove the last origin so that the saved list would be empty, **Then** the save is rejected with a validation error explaining that an enabled widget must have at least one allowed origin.
4. **Given** a tenant admin types a value that is not a valid URL (e.g., `"acme.com"` without a scheme, or `"javascript:alert(1)"`), **When** they click Save, **Then** the save is rejected with a per-field validation error and no audit log entry is written.
5. **Given** a user **without** the `tenant_admin` role, **When** they attempt to load the Widget page or call the underlying update endpoint directly, **Then** they receive a forbidden response and no widget config row is modified.

---

### User Story 2 - Tenant admin updates the widget's greeting and enabled flag (Priority: P1)

A tenant admin wants to change the first message visitors see ("Hello! How can we help?" → "Hi from Acme support!") and temporarily disable the widget during a maintenance window. They edit the greeting text, toggle the enabled flag, and click Save. The widget loaded by visitors reflects the new greeting on next mount; while disabled, the widget either does not appear on tenant sites or shows a neutral unavailable indicator (whichever the platform already enforces).

**Why this priority**: Greeting and enabled toggle are the two day-one self-serve customizations every tenant expects. Without them the tenant must contact support for trivial changes, undermining the "tenant manages their own widget" promise.

**Independent Test**: A tenant admin edits the greeting to a new string under the 280-character limit, toggles enabled off, then on, and saves. The widget config row reflects the changes after each save. No audit log entries are written for greeting/enabled changes (they are not security-sensitive enough to audit).

**Acceptance Scenarios**:

1. **Given** the current greeting is `"Welcome"`, **When** the admin saves a new greeting of `"Hello from Acme"` under 280 characters, **Then** the row is updated and no audit log entry is required for this change.
2. **Given** an admin attempts to save a greeting longer than 280 characters, **When** they click Save, **Then** the save is rejected with a length validation error.
3. **Given** the current `enabled` value is `true`, **When** the admin toggles it to `false` and saves, **Then** the row reflects `enabled=false` immediately. Toggling enabled to `true` while the saved `allowed_origins` is empty is rejected with the same validation error as User Story 1 acceptance scenario 3.

---

### User Story 3 - Tenant admin previews and updates the widget theme (Priority: P2)

A tenant admin wants the widget's colors to match their brand. They open the Widget page, edit the theme as a JSON document, see a live preview reflecting the change, and save. The next time a visitor loads the widget on the tenant's site, the widget renders with the new theme (subject to the widget runtime's theme support landing in a later phase).

**Why this priority**: Brand alignment is a strong adoption driver for B2C tenants but is not a launch blocker — the widget ships with a default theme that's acceptable. Theme is also the first place a tenant could break their widget by typing invalid JSON, so the validation/preview UX matters but is secondary to origin/greeting/enabled.

**Independent Test**: A tenant admin pastes a JSON document into the theme editor, observes the preview pane update, and clicks Save. The widget config row's `theme_json` field is updated. The save is rejected if the document is not valid JSON.

**Acceptance Scenarios**:

1. **Given** the theme editor contains a valid JSON document, **When** the admin clicks Save, **Then** the row is updated and the preview pane shows the widget rendered with that theme (or a placeholder iframe if a live preview is not feasible in the admin UI environment).
2. **Given** the admin types invalid JSON, **When** they pause typing, **Then** the editor surfaces a JSON parse error inline (without clicking Save) and the Save button is disabled or the save is rejected.
3. **Given** the admin clears the theme field entirely, **When** they save, **Then** the widget reverts to the platform default theme on next visitor mount.

---

### Edge Cases

- Two tenant admins from the same tenant edit the widget config simultaneously. The second Save overwrites the first; this is acceptable as long as the audit log captures both transitions accurately.
- A tenant admin attempts to add an origin that is already in the list (duplicate). The save succeeds with no net change and **no audit log entry** is written for the no-op.
- An origin's case differs from an existing entry (`https://Acme.com` vs `https://acme.com`). Both are treated as the same origin for allowlist purposes (case-insensitive host comparison).
- An origin contains a trailing slash or path (`https://acme.com/` or `https://acme.com/widget`). The system stores and compares the origin form (scheme + host + optional port) only; trailing slashes and paths are stripped on save.
- The widget's `enabled` flag flips from `true` to `false`. Existing widget JWTs already issued to visitors keep working until they expire (short TTL handles revocation). Disabling does not retroactively log out active conversations.
- A tenant admin tries to add an origin in a scheme other than `http` or `https` (`ftp://...`, `data:...`, `file://...`). The save is rejected — only HTTP and HTTPS schemes are valid origins for a browser-loaded widget.
- The audit log function is temporarily unavailable. The save **fails closed** — the widget config is **not** updated, the admin sees an error, and no partial state is persisted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a tenant admin to view the current widget configuration for their own tenant only.
- **FR-002**: The system MUST allow a tenant admin to update the widget configuration: allowed origins, greeting text, theme, and enabled flag.
- **FR-003**: Both view and update operations MUST be gated by the `tenant_admin` role; users without this role MUST receive a forbidden response.
- **FR-004**: All view and update operations MUST resolve `tenant_id` from server-trusted context (authenticated session or token), never from the request body.
- **FR-005**: Each tenant admin MUST be able to view and modify only their own tenant's widget configuration, never another tenant's.
- **FR-006**: An origin entry MUST be a syntactically valid URL with scheme `http` or `https`, a non-empty host, and no other scheme (`ftp`, `data`, `file`, `javascript`, etc., are rejected).
- **FR-007**: Origin comparison MUST be case-insensitive on the host component and normalized to the `scheme://host[:port]` form (trailing slashes and path components are stripped at save time).
- **FR-008**: If `enabled = true`, the `allowed_origins` list MUST contain at least one valid origin; saving an enabled widget with an empty origin list is rejected.
- **FR-009**: Every net addition to `allowed_origins` MUST emit exactly one audit log entry with action `widget.origin_added` and metadata identifying the added origin.
- **FR-010**: Every net removal from `allowed_origins` MUST emit exactly one audit log entry with action `widget.origin_removed` and metadata identifying the removed origin.
- **FR-011**: Audit log entries for origin changes MUST be emitted via the platform's existing audit log function (the same one used for tenant provision/suspend/erase). Direct writes to the audit_logs table from this feature are prohibited.
- **FR-012**: A no-op origin change (saving a list identical to what's already stored) MUST NOT produce an audit log entry.
- **FR-013**: If the audit log call fails, the widget configuration update MUST also fail and roll back; the admin MUST NOT see a successful save when the audit entry was not recorded.
- **FR-014**: The greeting text MUST be limited to 280 characters; saves of longer greetings are rejected.
- **FR-015**: The theme value MUST be a valid JSON **object** (or null); JSON scalars (strings, numbers, booleans) and JSON arrays are rejected with HTTP 422. No further schema validation is applied at this phase — the theme is stored as a free-form JSON object. The admin UI presents a JSON textarea with live parse-error feedback; typed fields and a strict schema land together with the widget runtime's theme support in a later phase.
- **FR-016**: The admin UI MUST display the current widget configuration and indicate unsaved changes clearly so the admin knows what will be written.
- **FR-017**: The admin UI MUST disable the Save button or otherwise prevent submission while any field has a validation error.
- **FR-018**: The admin UI MUST show the outcome of a save (success or specific per-field error) immediately after the save attempt.
- **FR-019**: Visitors loading the widget on origin X MUST receive a successful token on the next token-exchange request after a tenant admin adds X to the allowlist. The platform's token endpoint MUST read `allowed_origins` and `enabled` live from `widget_configs` on every token request; this feature introduces no caching layer. Propagation is therefore effectively immediate (bounded only by database read latency).
- **FR-020**: Tokens already issued for an origin that is subsequently removed MUST be allowed to expire passively via the existing short JWT TTL (5 minutes per feature 001's token-exchange contract). This feature does NOT introduce a JTI denylist or session-revocation channel. Tenants who require immediate hard-stop access for any in-flight session can toggle the widget's `enabled` flag to `false`; the platform-level enforcement of the disabled state is governed by FR-019.

### Key Entities *(include if feature involves data)*

- **Widget configuration**: One row per tenant capturing the editable widget settings. Fields: tenant_id (the tenant this config belongs to — required for isolation), allowed_origins (list of origin strings), theme (JSON document or null for default), greeting (short text), enabled (boolean). Owned by the tenant; only modifiable by users with the tenant_admin role on that tenant.
- **Audit log entry**: A record of a security-relevant change. For this feature, only origin additions and removals produce audit entries. Each entry carries: tenant_id, actor user id, action (one of `widget.origin_added`, `widget.origin_removed`), and metadata (the affected origin string).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tenant admin can add a new origin and confirm the change is live (a visitor on that origin gets a successful token exchange) without contacting platform support.
- **SC-002**: For every origin addition and removal performed via the admin page, exactly one corresponding audit log entry exists in the audit log. Net counts match: N origin additions = N `widget.origin_added` entries; N removals = N `widget.origin_removed` entries.
- **SC-003**: An attempt to view or modify the widget configuration by a user without the `tenant_admin` role on the relevant tenant is refused with no data leak and no state change.
- **SC-004**: An attempt by tenant admin A to read or modify tenant B's widget configuration is refused with the same response as if no such config existed (no cross-tenant data leak).
- **SC-005**: An attempt to save the widget with an empty allowed-origins list while `enabled = true` is rejected with a clear validation message; the row is unchanged.
- **SC-006**: An attempt to save an invalid origin (wrong scheme, missing host, malformed URL) is rejected before any audit log entry is written and before the row is modified.
- **SC-007**: When the audit log function is unavailable, no widget configuration change is persisted; the admin sees a failure.
- **SC-008**: A tenant admin completes a typical "add one origin and save" round-trip in under 30 seconds from page load, including reading current state and confirming the save.

## Assumptions

- The `tenant_admin` role and its dependency wiring are owned by another team member (per the project's role/ownership rules). This feature consumes the role check via the project's shared dependency mechanism; until that mechanism is available, the role check is mocked in tests with a clearly-marked stand-in that the implementation will swap for the real dep once it lands.
- The audit log function (`add_audit_log` or equivalent) is owned by the platform team and is consumed via its documented function signature. This feature does not write to the audit log table directly.
- The widget configuration row schema (the `widget_configs` table) is owned by the platform team and has the columns this feature needs (`tenant_id`, `allowed_origins`, `theme`, `greeting`, `enabled`). If a column is missing, this feature blocks on a coordinated schema change; it does not silently add columns.
- The admin UI is the Streamlit-based admin app that already exists in the project. This feature adds one new page; it does not restructure the admin app's navigation or auth model.
- "Theme" is stored as JSON but is not consumed by the live widget runtime in this feature — the widget runtime's theme support is a later phase. Saving theme JSON in this feature is forward-compatible plumbing.
- Out of scope: the other admin pages (a later phase), rotating the JWT signing key from the admin UI (intentionally never permitted from the UI — that's an ops/Vault action), and bulk import of origins (a usability follow-up).
