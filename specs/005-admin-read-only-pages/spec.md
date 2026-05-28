# Feature Specification: Admin Read-Only Pages

**Feature Branch**: `005-admin-read-only-pages`
**Created**: 2026-05-27
**Status**: Draft
**Input**: User description: "Build the four read-only admin pages: Tenant overview, CMS list, Leads viewer, Usage dashboard."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tenant overview page (Priority: P1)

A tenant administrator opens the admin app and selects the Tenant tab. They see a clear header card describing their tenant (name, slug, status, plan, created date) and a table of the most recent 20 audit log entries showing who did what and when. The page is read-only, so the administrator cannot accidentally change anything — they are observing tenant identity and recent administrative activity at a glance.

**Why this priority**: The Tenant overview is the landing surface for any administrator opening the admin app. Without it, the operator has no quick way to confirm which tenant they are looking at or to spot suspicious recent activity. It is the single most important read-only view because it answers "who am I, and what has happened lately?"

**Independent Test**: Open the admin app, navigate to the Tenant tab, and confirm the header card displays the five identity fields and the audit log table shows up to 20 rows ordered by recency. Verify that if the audit log endpoint is not yet live, the page still renders sample data with a clearly visible "(placeholder)" badge.

**Acceptance Scenarios**:

1. **Given** a live tenant detail endpoint and a live audit log endpoint, **When** the administrator opens the Tenant tab, **Then** the header card shows the real tenant name, slug, status, plan, and created date, and the audit log table shows the 20 most recent entries with created_at, actor_role, action, and metadata truncated to 80 characters.
2. **Given** the audit log endpoint still returns the placeholder shape, **When** the administrator opens the Tenant tab, **Then** the page renders sample audit rows with a visible "(placeholder)" badge so the demo does not appear broken.
3. **Given** the page is loaded, **When** the administrator inspects it, **Then** no edit, suspend, or erase controls are visible anywhere on the page.

---

### User Story 2 - CMS list page (Priority: P2)

A tenant administrator opens the CMS tab to review the knowledge base that the agent draws from. They see a list of CMS pages with title, slug, status, and last-updated date. They can filter the list by status (draft, published, archived). Clicking a row opens a read-only detail viewer showing the page's title, slug, body, and source URL. No editing, creating, or deleting is possible from this page.

**Why this priority**: After identity, the next most important question is "what content is the agent serving?" An auditable read-only view of CMS content lets the administrator verify coverage and spot stale or missing pages without risk of accidental mutation. Editing remains on a separate slice owned by another team.

**Independent Test**: Navigate to the CMS tab, confirm the table renders pages and supports filtering by status, click a row, and confirm the detail viewer shows the full page contents read-only. Verify the placeholder fallback path also works when the CMS list endpoint is not live.

**Acceptance Scenarios**:

1. **Given** a live CMS pages endpoint, **When** the administrator opens the CMS tab, **Then** the table lists pages with title, slug, status, and updated_at.
2. **Given** the administrator selects a status filter, **When** they choose "published", **Then** only published pages remain visible in the table.
3. **Given** the administrator clicks a row, **When** the detail viewer opens, **Then** it shows title, slug, body, and source_url with no editing controls.
4. **Given** the CMS endpoint returns the placeholder shape, **When** the page loads, **Then** sample pages render with a visible "(placeholder)" badge.

---

### User Story 3 - Leads viewer page (Priority: P2)

A tenant administrator opens the Leads tab to see captured leads from the chat widget. The table displays created date, name, contact (redacted display showing only the first 3 characters followed by asterisks), intent, status, and quality score. The administrator can filter by status (captured, qualified, spam). The view is strictly read-only: no editing fields, no manual qualification controls, no exports.

**Why this priority**: Leads are sensitive personal data. A redacted read-only view gives the administrator visibility for review and triage decisions while keeping the contact channel obscured by default and removing any chance of accidental edits. Read-only first; richer lead management is a separate slice.

**Independent Test**: Navigate to the Leads tab and verify rows appear with the contact field redacted to the documented pattern, that the status filter narrows results, and that the placeholder fallback path renders sample leads with the "(placeholder)" badge when the endpoint is not live.

**Acceptance Scenarios**:

1. **Given** a live leads endpoint, **When** the administrator opens the Leads tab, **Then** the table renders rows with created_at, name, redacted contact, intent, status, and quality_score.
2. **Given** any contact value, **When** rendered in the table, **Then** only the first three characters appear in clear text and the remainder is replaced with asterisks.
3. **Given** the administrator selects "qualified" in the status filter, **When** the table refreshes, **Then** only qualified leads are shown.
4. **Given** the leads endpoint returns the placeholder shape, **When** the page loads, **Then** sample leads render with a visible "(placeholder)" badge.

---

### User Story 4 - Usage dashboard page (Priority: P3)

A tenant administrator opens the Usage tab to understand how their tenant is consuming the platform this month. They see month-to-date total tokens, total cost in USD, a breakdown by feature (chat, embedding, classifier, rag, agent, guardrails), and a simple line chart of daily cost. The view is read-only: no rate-limit configuration, no billing actions, no admin-grade controls.

**Why this priority**: Usage visibility is valuable for planning and cost awareness but is the least urgent of the four pages because the platform team owns rate limits and billing actions elsewhere. The page exists to inform the tenant administrator, not to let them act.

**Independent Test**: Navigate to the Usage tab and verify that totals, the feature breakdown, and the daily-cost line chart all render from the aggregation endpoint. Verify the placeholder fallback path works when the endpoint is not live.

**Acceptance Scenarios**:

1. **Given** a live usage aggregation endpoint, **When** the administrator opens the Usage tab, **Then** the page shows total tokens this month, total cost USD this month, a per-feature breakdown across the six features, and a daily-cost line chart.
2. **Given** the usage endpoint returns the placeholder shape, **When** the page loads, **Then** sample totals, breakdown, and chart render with a visible "(placeholder)" badge.
3. **Given** the page is loaded, **When** the administrator inspects it, **Then** no rate-limit or billing controls are visible.

---

### Edge Cases

- The Tenant detail endpoint is unreachable or returns a non-2xx response (404, 4xx, 5xx, or a network failure): the page falls back to sample data with a visible "(placeholder)" badge, never a raw stack trace. The two render paths are "real data" and "placeholder" — nothing else.
- The audit log, CMS, leads, or usage endpoint returns an empty list (not the placeholder shape, just no records): the table should render an empty state with a short "no entries yet" message rather than collapsing or erroring.
- A long audit log `metadata_json` blob (well above 80 characters): the rendered cell must be truncated to 80 characters with an ellipsis so the table layout does not break.
- A contact value shorter than 3 characters in the Leads viewer: redaction must not crash; show the available characters followed by at least one asterisk to indicate redaction.
- The Tenant tab is opened by a user whose role is not Tenant Manager or higher: access control belongs upstream, but the page must not display tenant data if it received an unauthorized response — it should display an error state.
- The Usage daily-cost series spans fewer than two data points: the line chart must degrade gracefully (e.g., render a single marker or an empty-state message) rather than error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The admin app sidebar MUST expose four navigation entries — Tenant, CMS, Leads, Usage — that route to the four new read-only pages, in addition to the existing Widget tab which MUST remain untouched.
- **FR-002**: All four pages MUST fetch their data exclusively through HTTP GET calls to existing backend endpoints; they MUST NOT perform any write actions or direct database queries.
- **FR-003**: Each page MUST detect when a consumed endpoint still returns the placeholder shape and, in that case, render sample data with a clearly visible "(placeholder)" badge so the demo does not appear broken.
- **FR-004**: The Tenant overview page MUST display a header card containing the tenant name, slug, status, plan, and created_at.
- **FR-005**: The Tenant overview page MUST display the 20 most recent audit log entries with columns created_at, actor_role, action, and metadata_json truncated to 80 characters.
- **FR-006**: The Tenant overview page MUST NOT expose any edit, suspend, or erase controls.
- **FR-007**: The CMS list page MUST display a table of CMS pages with columns title, slug, status, and updated_at, and MUST support filtering by status across the values draft, published, and archived.
- **FR-008**: The CMS list page MUST allow opening a read-only detail viewer per row that shows title, slug, body, and source_url, with no create, edit, or delete affordances.
- **FR-009**: The Leads viewer page MUST display a table with columns created_at, name, redacted contact, intent, status, and quality_score, where the redacted contact shows only the first three characters in clear text followed by asterisks.
- **FR-010**: The Leads viewer page MUST support filtering by status across the values captured, qualified, and spam, and MUST NOT expose any lead editing or manual qualification controls.
- **FR-011**: The Usage dashboard page MUST display total tokens for the current month, total cost in USD for the current month, a per-feature breakdown across chat, embedding, classifier, rag, agent, and guardrails, and a line chart of daily cost.
- **FR-012**: The Usage dashboard page MUST NOT expose any rate-limit configuration or billing controls.
- **FR-013**: Each page MUST handle endpoint errors (any non-2xx response — including 404, 4xx, and 5xx — and network/transport failures) by falling back to the same canned sample data path used for placeholder responses, with the visible "(placeholder)" badge displayed. No raw stack trace, response body, or unredacted error payload is shown to the administrator.
- **FR-014**: Each page file MUST remain small and self-contained (target ~120 lines); a shared HTTP helper MUST be extracted only if duplicated logic appears in more than two pages.
- **FR-015**: Each page MUST be covered by a Streamlit AppTest harness that exercises both the happy path and the placeholder-fallback path, with the backend mocked at the transport layer so the tests do not require a running backend.
- **FR-016**: Tenant scoping MUST be derived from trusted server-side context (the administrator's session, not query parameters or user input), consistent with the platform's tenant safety rules.

### Key Entities *(include if feature involves data)*

- **Tenant summary**: A read-only projection of a tenant exposing name, slug, status, plan, and created_at. Sourced from the platform's tenant detail endpoint.
- **Audit log entry**: A timestamped record of an administrative action on a tenant, with actor role, action label, and structured metadata. Displayed in reverse-chronological order, limited to the 20 most recent entries.
- **CMS page summary**: A listing-row projection of a CMS page exposing title, slug, status, and updated_at.
- **CMS page detail**: An expanded read-only view of a single CMS page exposing title, slug, body, and source_url.
- **Lead**: A captured visitor contact exposing created_at, name, contact channel value (rendered redacted), intent, status, and quality_score.
- **Usage rollup**: A current-month aggregate exposing total tokens, total USD cost, a per-feature breakdown across chat/embedding/classifier/rag/agent/guardrails, and a daily-cost time series.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tenant administrator can open the admin app and reach each of the four new pages within two clicks from the landing view (sidebar click only), with no page taking more than three seconds to render its initial content under normal conditions.
- **SC-002**: When any of the four consumed endpoints is not yet live, the corresponding page still renders with sample data and a visible "(placeholder)" badge 100% of the time, so a demo walkthrough never shows a broken page.
- **SC-003**: Across all four pages, zero write actions can be triggered from the UI; an audit of the rendered DOM/widgets shows no edit, create, delete, suspend, erase, rate-limit, or billing controls.
- **SC-004**: In the Leads viewer, every rendered contact value displays at most the first three characters in clear text, verified by automated tests covering short, normal, and long contact values.
- **SC-005**: Each page is covered by automated tests for both the happy path and the placeholder-fallback path, with mocked transport, and the test suite for these pages completes in under 30 seconds locally.
- **SC-006**: Each new page file stays at or near the ~120-line target; if a shared helper is introduced, it is justified by duplication appearing in more than two pages.

## Assumptions

- The administrator viewing these pages is authenticated and authorized via the existing admin session mechanism; this slice does not introduce a new auth layer.
- The tenant identity used to scope every request is derived from the administrator's verified session on the server side, not from client-supplied parameters, consistent with the platform's tenant safety rules.
- The CMS list, leads list, and audit log endpoints expose at minimum the fields named in this spec; if a teammate's endpoint is not yet live, the page detects the placeholder shape and falls back to sample data with a "(placeholder)" badge.
- Status vocabularies used for filtering (CMS: draft/published/archived; Leads: captured/qualified/spam) match the values produced by the corresponding endpoints.
- The contact redaction rule (first 3 characters in the clear, remainder masked) is sufficient for in-app display in this slice; deeper privacy controls (full masking, export gating) are handled elsewhere.
- The Usage dashboard's "this month" window is calendar-month-to-date in the tenant's billing timezone; the aggregation endpoint is responsible for that calculation, and the page renders whatever range the endpoint returns.
- Pagination, sorting beyond reverse chronological for audit logs, full-text search, and CSV export are out of scope for this slice.
- Streamlit remains the admin UI framework, and the existing Widget tab from Phase 4 continues to function unchanged.
