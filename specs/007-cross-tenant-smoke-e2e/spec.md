# Feature Specification: Cross-Tenant Smoke E2E

**Feature Branch**: `007-cross-tenant-smoke-e2e`
**Created**: 2026-05-28
**Status**: Draft
**Input**: User description: "Replace the placeholder smoke test with a real end-to-end check that proves tenant isolation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prove Cross-Tenant Content Isolation in CI (Priority: P1)

As the platform team, before any change merges to `main`, we need an automated check that runs the full stack and proves Tenant A's chat answers never leak Tenant B's content (and vice versa). This is the single most important guarantee Concierge makes to customers, and it must be verified end-to-end, not via unit-level mocks.

**Why this priority**: Tenant isolation is the highest-priority property of the entire platform (per project rules). A placeholder smoke test gives false confidence; a real cross-tenant probe is the only way to catch regressions in routing, RAG filtering, widget auth, or repository scoping before they reach production.

**Independent Test**: Can be fully tested by provisioning two tenants with distinct branded content ("alpha-cookies" vs. "bravo-pastries"), issuing each tenant's widget the same question, and asserting that each answer contains only its own brand keyword and never the other tenant's keyword. If this single scenario passes, the platform has demonstrated baseline tenant isolation across the public chat path.

**Acceptance Scenarios**:

1. **Given** Tenant A and Tenant B are provisioned with disjoint CMS content (A mentions "alpha-cookies", B mentions "bravo-pastries") and their content has been ingested into RAG, **When** a visitor on Tenant A's widget asks "what cookies do you have?", **Then** the response references "alpha-cookies" and does not contain the string "bravo-pastries".
2. **Given** the same setup, **When** a visitor on Tenant B's widget asks "what cookies do you have?", **Then** the response references "bravo-pastries" and does not contain the string "alpha-cookies".
3. **Given** both tenants are configured with one allowed origin each, **When** the chat endpoint receives a request bearing a token whose origin claim does not match the tenant's registered allowed origin, **Then** the request is rejected with HTTP 403.

---

### User Story 2 - Verify Lead Capture and Escalation Stay Tenant-Scoped (Priority: P2)

As the platform team, we need confidence that the two write-tools the agent can call — `capture_lead` and `escalate` — produce records that are scoped to the originating tenant and observable via audit logs. A leak in either direction (writing a lead under the wrong tenant, or escalating without an audit trail) is as serious as a content leak.

**Why this priority**: Lead capture and escalation are the only agent tools that write tenant-owned state. Read-side isolation (Story 1) is necessary but not sufficient; write-side isolation must be independently verified. This story is P2 because the read path is the more common attack surface and ships first.

**Independent Test**: Can be fully tested by triggering a lead capture via Tenant A's widget, then querying lead storage and asserting the new lead's `tenant_id` equals Tenant A's id and is not visible to Tenant B; then triggering an escalation via Tenant A's widget and asserting the ticket is created and an audit log entry references Tenant A.

**Acceptance Scenarios**:

1. **Given** a chat session authenticated as Tenant A, **When** the agent calls the lead-capture tool with sample contact data, **Then** the response includes a `lead_id` and a follow-up read confirms the lead is stored with `tenant_id = A`.
2. **Given** a chat session authenticated as Tenant A, **When** the agent calls the escalate tool, **Then** the response includes a `ticket_id` and an audit log entry exists referencing the action, tenant A, and the ticket.

---

### User Story 3 - Smoke Test Runs Reliably in CI and Locally (Priority: P3)

As any developer on the team, when I push a branch I want the smoke test to spin up the full stack, run the isolation probes, tear the stack down, and produce a clear pass/fail signal — without flakiness from missing health checks or partially-booted services.

**Why this priority**: Test correctness (Stories 1 and 2) is paramount; ergonomics around running the test come next. A flaky smoke test gets disabled, and a disabled smoke test protects no one.

**Independent Test**: Can be fully tested by running the smoke entrypoint script against a stack that is intentionally unhealthy (e.g., one dependency not yet ready) and confirming the test waits for healthchecks instead of failing immediately, and by running it against a healthy stack and confirming a non-zero exit code on any assertion failure.

**Acceptance Scenarios**:

1. **Given** the stack is being brought up, **When** the smoke runner starts, **Then** it waits for each service's healthcheck to report healthy before issuing any probe requests, up to a bounded timeout.
2. **Given** the smoke test passes, **When** CI completes (success or failure), **Then** the stack is torn down and no orphan containers, networks, or volumes remain attached to the runner.
3. **Given** any assertion fails, **When** the run completes, **Then** the runner exits with a non-zero status and the failing assertion plus the offending tenant/scenario is captured in the log output.

---

### Edge Cases

- A tenant's CMS content has not finished ingesting when the chat probe fires — the test must wait for ingestion to complete (or RAG to return results) up to a bounded timeout rather than racing.
- The chat answer references neither brand keyword (e.g., the agent escalates or asks a clarifying question instead of answering) — this is a regression in tool selection and the test must fail rather than treat "no leak" as success.
- The forged-origin probe receives an answer instead of 403 — must fail loudly; silent acceptance is the worst possible outcome.
- Docker Compose is already running locally with a different state from CI — the smoke runner must either tear down and rebuild or refuse to run, never silently reuse contaminated state.
- One of the platform services (api, modelserver, guardrails) has no healthcheck defined — the smoke runner must add or require one rather than sleeping a fixed duration.
- Tenant provisioning, widget-config registration, or CMS ingestion endpoints are still under development and not yet shipped — the smoke test must declare these as required dependencies and fail with a clear "endpoint not available" message rather than passing vacuously.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The smoke test MUST provision two distinct tenants (Tenant A and Tenant B) through the platform's tenant-creation endpoint, each with their own widget configuration and a single allowed origin.
- **FR-002**: The smoke test MUST seed each tenant with at least two CMS pages containing disjoint, tenant-specific keywords ("alpha-cookies" for A; "bravo-pastries" for B) and ensure that content is searchable via RAG before any chat probe is issued.
- **FR-003**: The smoke test MUST obtain a short-lived widget token for each tenant via the documented widget-session flow, supplying the tenant's `widget_id` and a matching origin.
- **FR-004**: The smoke test MUST issue an identical chat question ("what cookies do you have?") under each tenant's token and assert that the response for Tenant A contains the string "alpha-cookies" and not "bravo-pastries", and conversely for Tenant B.
- **FR-005**: The smoke test MUST attempt a chat request bearing a token whose origin claim does not match the tenant's allowed-origin list (forged-origin scenario) and assert that the request is rejected with HTTP 403.
- **FR-006**: The smoke test MUST exercise the lead-capture tool via Tenant A's widget and assert that the returned `lead_id` corresponds to a stored lead whose `tenant_id` equals Tenant A's id.
- **FR-007**: The smoke test MUST exercise the escalate tool via Tenant A's widget and assert that the returned `ticket_id` is accompanied by an audit-log entry referencing Tenant A and the escalation action.
- **FR-008**: The smoke test MUST be executable as a single command (the smoke-runner script) that returns exit code 0 on full success and non-zero on any assertion failure or precondition failure.
- **FR-009**: The smoke-runner MUST verify that every required service (API, modelserver, guardrails, and any other dependency required to answer a chat request end-to-end) reports healthy via its declared healthcheck before issuing probes, with a bounded wait.
- **FR-010**: The CI pipeline MUST include a dedicated job that brings up the full stack, executes the smoke test, and tears the stack down on completion regardless of pass/fail outcome.
- **FR-011**: Any platform service that participates in answering a chat request and does not currently expose a healthcheck MUST have one added so the smoke-runner's readiness wait is reliable.
- **FR-012**: The smoke test MUST NOT depend on internal-only credentials or service-to-service auth shortcuts in ways that bypass the same authorization the public chat path enforces (i.e., it tests the real path, not a privileged backdoor).
- **FR-013**: The smoke test MUST clean up the two tenants it provisions (or run against a disposable database) so repeated runs do not accumulate orphan tenants, widgets, leads, or audit-log entries.
- **FR-014**: On any failure, the smoke test MUST log which tenant and which scenario failed, including the offending response payload where present, without leaking secrets or full tokens.

### Key Entities

- **Smoke Tenant**: A short-lived test tenant (A or B) provisioned at the start of the run, with one widget configuration, one allowed origin, two CMS pages, and disjoint keyword content. Identified by its `tenant_id`.
- **Smoke Widget Session**: A widget-token-bearing session scoped to a single smoke tenant; used to exercise the chat, lead-capture, and escalate paths exactly as a real visitor's browser would.
- **Isolation Probe**: One assertion pair (Tenant A asks → expect alpha keyword and no bravo; Tenant B asks → expect bravo and no alpha) plus the forged-origin negative probe.
- **Smoke Run Report**: The aggregated pass/fail summary produced by the runner, identifying which probes ran, which passed, which failed, and where each failure occurred.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A complete smoke run (stack up → probes → stack down) completes in under 10 minutes on the CI runner.
- **SC-002**: The smoke job blocks merge: 100% of PRs that introduce a cross-tenant leak in chat content, lead capture, or escalation are caught and rejected by the smoke gate before merge.
- **SC-003**: The smoke job is non-flaky: across 20 consecutive runs against an unchanged main branch, the pass rate is 100% (no spurious failures from race conditions or missing healthchecks).
- **SC-004**: The forged-origin negative probe rejects with the correct HTTP 403 status on every run; any other status (including 200 with a benign answer, or 500) is treated as a hard failure.
- **SC-005**: After each run, regardless of pass/fail, the CI runner has zero leftover containers, networks, or named volumes tied to the smoke stack.
- **SC-006**: A team member can run the same smoke test locally with one command and receive identical pass/fail behavior as in CI (modulo stack startup time).

## Assumptions

- The endpoints referenced in the probe sequence (tenant provisioning, widget-config registration, CMS page creation, RAG ingestion trigger, widget-session token issuance, chat, and the lead/escalate tools) either already exist or will be in place before this smoke test is enabled as a merge gate. If they are not yet shipped, the smoke job runs but is allowed to fail loudly with "dependency not available" rather than be silently skipped.
- Docker Compose is the canonical local and CI stack runner; no Kubernetes, no remote staging environment is required for this smoke check.
- The smoke test runs against a disposable database that is recreated per CI job; production-grade migrations and cleanup are out of scope for this feature.
- The chat agent will, on a straightforward keyword question against well-seeded CMS content, choose to call `rag_search` and answer from that content rather than escalate. If the agent's tool-selection logic regresses such that the keyword question triggers escalation, that itself is a regression worth surfacing — the smoke test will fail and the agent eval gates will follow up.
- "alpha-cookies" and "bravo-pastries" are arbitrary disjoint marker strings chosen so that any leakage is detected by exact substring match; the chosen words are not meaningful brand decisions.
- Performance / load testing, UI screenshot diffing, and multi-region testing are explicitly out of scope for this feature, per the user input.
- Audit-log readability for the escalate probe assumes Hiba's audit-log table is queryable (directly or via an admin endpoint) from the smoke runner; if no read path exists yet, the test will assert only the `ticket_id` return value and mark the audit-log check as a known follow-up.
