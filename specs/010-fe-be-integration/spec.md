# Feature Specification: Concierge frontend / backend integration retrofit

**Feature Branch**: `010-fe-be-integration`
**Created**: 2026-05-29
**Status**: Draft
**Input**: User description: "Close the 13 missing endpoints from [specs/009-concierge-ui/contracts/missing-endpoints.md](../009-concierge-ui/contracts/missing-endpoints.md), wire the existing admin + widget UI surfaces to live data, and graduate the stub router + stub agent + three tools to the production shape mandated by [Concierge_Backend_Blueprint.md](../../Concierge_Backend_Blueprint.md). Two tracks: Track 1 = integration retrofit; Track 2 = real router + real LLM agent + real tools + bounded loop + memory + version-controlled prompts. Load-bearing rule: the frontend NEVER decides tenant identity or role."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tenant admin works through every tab without seeing placeholder data (Priority: P1)

A tenant admin signs in and walks through all nine of their tabs — Overview, CMS, Agent, Guardrails, Widget, Leads, Escalations, Usage, Audit. On a healthy stack, every tab renders real data attributed to their tenant only. Edits saved on the writable tabs (CMS create / edit / publish / delete, Agent persona + chips, Guardrails tenant overrides, Widget config, Escalation status + assignee) persist across sign-out / sign-in. None of these surfaces show a "(placeholder)" caption anymore.

**Why this priority**: This is the surface a paying customer's owner actually uses. Without it, the product is consulting-ware. The placeholder fallback exists today as a development-time safety net; with this feature, real data lights up every screen.

**Independent Test**: A reviewer signs in as a seeded `tenant_admin`, walks all 9 tabs, performs one write per writable tab, signs out, signs back in, and confirms each change persisted. They then sign in as a second tenant's admin and confirm none of the first tenant's data is visible on any tab. The reviewer also confirms zero "(placeholder)" badges appear while the api container is healthy.

**Acceptance Scenarios**:

1. **Given** a signed-in tenant admin on a healthy stack, **When** they open the Agent tab, **Then** the page shows their persona name, tone, language, business rules, and 0–6 chips from the live agent configuration — no canned English defaults.
2. **Given** a signed-in tenant admin, **When** they edit the persona name and save, **Then** the save button disables while in flight, a success toast appears within 2 seconds, the value persists across sign-out, and the widget on the tenant's site picks up the new chips on next panel-open.
3. **Given** a signed-in tenant admin, **When** they create a CMS page and publish it, **Then** the page appears in the list with a "published" status pill, and an audit-log entry of type `cms.page_published` is visible in the Audit tab within the next refresh.
4. **Given** a signed-in tenant admin viewing the Escalations tab, **When** they change a ticket's status to "in_progress" and assign it to themselves, **Then** the row updates without a full page reload, and two separate audit-log entries (`escalation.status_changed`, `escalation.assignee_changed`) appear in the Audit tab.
5. **Given** a signed-in tenant admin attempts to delete a CMS page, **When** they click Delete, **Then** a confirmation dialog appears; only after confirm does the row disappear and a `cms.page_deleted` audit entry appear.
6. **Given** tenant admin A is signed in, **When** they open every tab, **Then** no record belonging to tenant B is reachable from any view, link, or detail panel.

---

### User Story 2 - Visitor message in an ambiguous or multi-step turn reaches the agent and completes safely (Priority: P1)

A visitor on a tenant's website opens the bubble launcher and asks a question whose intent is ambiguous, or a question that requires two tool calls in sequence (for example, "I'm looking for pricing on your enterprise plan and want someone to email me jane@acme.example"). The router classifies it with low confidence (or as "ambiguous"); the turn is handed off to the agent. The agent — a single tool-calling LLM — picks among `rag_search`, `capture_lead`, and `escalate` under uncertainty, executes the right sequence within hard loop bounds, and the visitor sees a coherent answer with any captured side-effects (lead row, escalation ticket) attributed to the correct tenant.

**Why this priority**: The blueprint floor: *"the agent must genuinely handle multi-tool, ambiguous turns, not just sit behind the router as dead weight."* Without this, the chat product is a thin FAQ bot. With this, it does the job the SaaS sells.

**Independent Test**: A reviewer crafts two visitor messages — one ambiguous one-tool turn ("Can you tell me about your services?") and one multi-tool turn ("I want pricing and someone to email me at test@example.com"). Sending each through the widget, the reviewer confirms (a) the high-confidence FAQ turn goes through the cheap workflow path; (b) the ambiguous and multi-tool turns reach the agent (visible via a new `agent.turn_started` audit-log entry); (c) the agent completes within the 5-iteration / 4000-token caps; (d) `capture_lead` writes a row attributed to the tenant; (e) `escalate` writes a real row to `escalation_tickets` (table from migration 0004) that surfaces in the tenant admin's Escalations tab.

**Acceptance Scenarios**:

1. **Given** a visitor sends "What are your opening hours?" through a tenant's widget, **When** the router classifies it with confidence ≥ 0.70 as `faq`, **Then** the workflow path serves a RAG answer with citation chips and no `agent.turn_started` audit row appears.
2. **Given** a visitor sends "Hmm, maybe I want a demo?", **When** the router returns `ambiguous` OR confidence below the threshold, **Then** the agent receives the turn, picks the appropriate tool sequence, and the response carries one of the routes `agent`, `escalate`, or `workflow`.
3. **Given** a visitor sends a turn requiring two tool calls (pricing question + contact info), **When** the agent runs, **Then** the agent makes at most 5 tool iterations, the response includes both citation chips (from `rag_search`) and a lead-capture confirmation (from `capture_lead`), and a real `Lead` row is created with the visitor's contact attributed to the correct tenant.
4. **Given** a hostile visitor sends prompt-injection content claiming to be tenant B, **When** the agent processes the turn, **Then** no tool call can mutate `tenant_id`, no lead is written under a different tenant, and the `tenant_id` field is silently stripped from any tool argument before execution.
5. **Given** a visitor sends a turn that triggers the agent into a long chain, **When** the agent hits either the 5-iteration cap or the 4000-token cap, **Then** the agent halts, calls `escalate` once, returns a safe "I've escalated this to a human" message, and emits an `agent.iteration_cap_hit` or `agent.token_cap_hit` audit-log entry.
6. **Given** a visitor sends a request for human contact, **When** the agent calls `escalate`, **Then** a real row is inserted into `escalation_tickets` for the correct tenant, the response carries the real `ticket_id`, and the ticket appears in the tenant admin's Escalations tab on the next page render.
7. **Given** the modelserver `/predict` endpoint is unreachable, **When** a visitor sends any message, **Then** the router fails soft to the agent path (never silent-routes to a destructive tool like `capture_lead`).

---

### User Story 3 - Tenant manager runs platform operations without seeing tenant content (Priority: P2)

A tenant manager signs in and operates across their six tabs: Overview, Tenants, Invites, Usage & Cost, Audit Logs, Settings. They can list / suspend / erase tenants, issue / revoke / resend invites, adjust platform-level tenant settings, monitor aggregate usage and cost, and review platform-wide audit logs. At no point can they read another tenant's CMS content, conversations, leads, or escalation details.

**Why this priority**: This is the SaaS-operations surface. P2 because the demo can land with TA + widget alone, but enterprise customers will not commit without the platform story.

**Independent Test**: A reviewer signs in as a seeded `tenant_manager`, walks all 6 tabs, performs one write per writable tab (issue an invite, revoke an outstanding invite, suspend a tenant, update a setting), signs out and back in, confirms each change persisted. They then attempt to navigate to a `/cms/pages` or `/leads` URL via the address bar — every such attempt returns the byte-uniform 403.

**Acceptance Scenarios**:

1. **Given** a signed-in tenant manager, **When** they open the Tenants tab, **Then** the table lists every tenant in the platform with metadata only (name, slug, plan, status, created_at) — no per-tenant content fields.
2. **Given** a signed-in tenant manager issues an invite, **When** the invitee accepts within the configured TTL, **Then** the invite is marked `used`, the new admin can sign in immediately, and the original invite link no longer works.
3. **Given** a signed-in tenant manager revokes an outstanding invite, **When** the invitee opens the link, **Then** the link displays the same canned "invite unavailable" message it would show for an expired link.
4. **Given** a signed-in tenant manager opens the Audit Logs tab, **When** they filter by actor role, tenant, action, and date range, **Then** the feed reflects the filters and never displays redacted metadata fields as raw text.
5. **Given** a signed-in tenant manager, **When** they navigate via the address bar to any tenant-content endpoint (CMS pages, leads, escalations, audit-log entries with content), **Then** the server returns the same byte-uniform 403 as any other unauthorized access — no information about why is leaked.
6. **Given** a signed-in tenant manager updates a setting in the Settings tab, **When** they confirm the change in a dialog, **Then** the save shows a spinner, a success toast appears, and a `tenant.settings_updated` audit entry is visible in the Audit Logs tab on next refresh.

---

### User Story 4 - Tenant persona injected into the prompt at runtime, never hardcoded (Priority: P2)

A platform operator pushes a prompt change to the platform system prompt in a single version-controlled file. The change ships behind a CI gate that runs the agent-tool eval against a golden set; if accuracy drops below threshold, the merge is blocked. The platform system prompt and the per-tenant persona (name, tone, business rules) are assembled at runtime — never co-located in code. When a tenant admin updates their persona via the Agent tab, the next visitor message uses the new persona without requiring a redeploy.

**Why this priority**: Blueprint quote — *"Prompts are code. A prompt change with no diff history is an outage you can't bisect."* Without this, tenants are stuck with a hardcoded voice; platform operators are flying blind on prompt drift.

**Independent Test**: A reviewer edits the platform system prompt file in a PR, sees the CI gate run the agent-tool eval and report pass/fail, confirms the merge is blocked on a deliberately-bad edit and unblocks on a fix. Separately, a tenant admin changes the persona name in the Agent tab, then a visitor's next message receives a response in the new persona without any restart.

**Acceptance Scenarios**:

1. **Given** the platform system prompt is in version control, **When** a PR edits the prompt file, **Then** the CI agent-tool eval runs against the golden set and the PR is blocked if accuracy drops below the threshold in `eval_thresholds.yaml`.
2. **Given** a tenant admin changes the persona name from "Concierge" to "Acme Helper", **When** they save, **Then** the next visitor message receives a response framed by the new persona — no app restart, no cache flush required.
3. **Given** the agent constructs a turn's prompt, **When** the assembly runs, **Then** the resulting prompt contains exactly three named blocks: platform system (locked), tenant persona (injected from `tenant_agent_configs`), and tool schemas (generated from Pydantic models). No per-tenant string lives in code.
4. **Given** a malicious tenant tries to override platform guardrails via their persona text, **When** the prompt is assembled, **Then** the platform system block remains the system role; tenant persona is a labelled, lower-trust block; platform refusal patterns still fire.

---

### Edge Cases

- **Cold start with no agent_config row for a tenant**: `GET /tenants/{tid}/agent-config` returns 404; widget falls back to hard-coded English defaults; admin Agent tab shows an empty form (no placeholder fallback for writes).
- **Forged widget JWT claiming tenant B**: `POST /chat` validates the signature; any failure collapses to a single 401 indistinguishable from "no token" / "expired token".
- **Cross-tenant assignee_id on PATCH /escalations/{id}**: server returns 422; the PATCH does not partially apply (no status change happens either).
- **Invite revoked then accepted**: accept returns the same canned "invite unavailable" message used for expired and never-existed invites.
- **CMS page deleted while a visitor's chat references it**: visitor's already-rendered citation chips remain (no live invalidation); the next turn's `rag_search` does not retrieve the deleted page.
- **Modelserver `/predict` slow or 5xx**: router fails soft to agent path; visitor's first turn may take longer than usual; no destructive workflow path is invoked under uncertainty.
- **`capture_lead` flooded by a hostile prompt**: per-session rate limit (default 5/hour) returns `{status: "rate_limited"}` from the 6th call onward; agent surfaces a friendly "I've captured your details" message; `lead.rate_limited` audit entry recorded.
- **Agent loop forced toward 5-iteration cap by adversarial input**: hard halt, single `escalate` call, safe message; `agent.iteration_cap_hit` audit emitted.
- **Redis unavailable mid-session**: chat continues without memory; one `memory.unavailable` audit-log entry per session; visitor sees no error.
- **Tenant admin opens the Audit tab during a live demo**: 200+ rows render via cursor pagination; no full-table scroll lag.
- **Streamlit rerun loses focus state**: write actions remain idempotent — a successful PUT followed by a Streamlit rerun does not re-issue the PUT.

---

## Requirements *(mandatory)*

### Functional Requirements — Track 1: Integration retrofit

- **FR-001**: System MUST expose 13 new HTTP endpoints whose paths, methods, request bodies, response shapes, and auth deps match the contract in [specs/009-concierge-ui/contracts/missing-endpoints.md](../009-concierge-ui/contracts/missing-endpoints.md) exactly.
- **FR-002**: Every new write endpoint MUST emit at least one audit-log entry using the existing redaction-on-metadata path; the new audit vocabulary entries are `tenant.agent_config_updated`, `tenant.settings_updated`, `cms.page_published`, `cms.page_unpublished`, `escalation.created`, `escalation.status_changed`, `escalation.assignee_changed`, `admin.invite_revoked`, `admin.invite_resent`.
- **FR-003**: Every new request body MUST forbid unknown fields; specifically, no body MAY carry `tenant_id`, `actor_id`, or `role`. The server MUST derive these from the verified JWT only.
- **FR-004**: Cross-tenant access on any new endpoint MUST return a byte-uniform 403 indistinguishable from "endpoint not found" or "wrong role" refusal cases.
- **FR-005**: Tenant-manager-only endpoints MUST return the same byte-uniform 403 when called with a `tenant_admin` JWT.
- **FR-006**: The admin UI MUST stop showing "(placeholder)" captions on any tab whose endpoints are live; the placeholder fallback MUST remain as a transport-failure safety net only.
- **FR-007**: Every admin write MUST disable its submit control while the request is in flight, surface a success toast on 2xx, and surface a friendly error toast on non-2xx without exposing raw server text.
- **FR-008**: Destructive admin actions (CMS delete, invite revoke) MUST require an explicit confirm step before executing.
- **FR-009**: The widget chat surface MUST fetch the tenant's greeting and quick-action chips from the agent-config endpoint on first panel-open; the hard-coded English defaults MUST remain available as a fail-soft fallback on 404 / 501 / transport failure.
- **FR-010**: The widget MUST keep the bubble launcher, mobile sheet under 640 px, ESC-to-close, focus trap, and reduced-motion behaviors already shipped in feature 009 (US4 a11y baseline).
- **FR-011**: New admin pages MUST adopt the existing draft-state pattern (server snapshot + working copy + dirty indicator) for any editable form.
- **FR-012**: The widget session credential MUST remain in module-scope memory only; no `localStorage`, `sessionStorage`, or cookie storage is permitted (Constitution Principle IV).
- **FR-013**: All loading indicators MUST be visible within 200 ms of any user-initiated fetch.

### Functional Requirements — Track 2: Agent, tools, memory, prompts

- **FR-014**: The router MUST call the real ONNX classifier via `modelserver /predict` and consume `{label, confidence}` from the response.
- **FR-015**: When confidence ≥ a configurable threshold (default 0.70) AND the label is a confident workflow label, the router MUST route the turn through the deterministic workflow path. Otherwise (low confidence OR `ambiguous` label) the router MUST route the turn to the agent.
- **FR-016**: When `label = spam` the router MUST always block, regardless of confidence.
- **FR-017**: When the modelserver is unreachable or returns 5xx, the router MUST fail soft to the agent path; it MUST NEVER silent-route to a destructive workflow (e.g., `capture_lead`) on uncertainty.
- **FR-018**: The agent MUST be a single tool-calling LLM with a hard-coded tool allowlist of exactly `{rag_search, capture_lead, escalate}`. No fixed graph; the agent picks under uncertainty.
- **FR-019**: The agent loop MUST halt at the smaller of 5 tool-call iterations or 4000 total tokens per visitor turn. On cap-hit it MUST call `escalate` once, return a safe "I've escalated this" message, and emit an `agent.iteration_cap_hit` or `agent.token_cap_hit` audit-log entry.
- **FR-020**: The agent MUST emit audit-log entries `agent.turn_started`, `agent.tool_called`, and `agent.turn_completed` per visitor turn; entries MUST NOT contain message content.
- **FR-021**: All three tools MUST use Pydantic argument schemas with `extra=forbid`; any LLM-supplied `tenant_id`, `session_id`, or `actor_id` field MUST be dropped at the schema boundary before the tool executes.
- **FR-022**: `tenant_id` for every tool call MUST come from the `ChatService` trusted parameter (sourced from the verified widget JWT) and never from tool arguments or message content.
- **FR-023**: `rag_search` MUST retrieve from the tenant's CMS content only, filtered by `tenant_id`. The lexical baseline ships in this feature; pgvector ANN retrieval is out of scope.
- **FR-024**: `capture_lead` MUST validate name (optional, 1..200 chars), contact (optional, email-or-phone regex), and intent (required, 1..1000 chars); intent MUST pass through the redaction utility before persist; the resulting `Lead` row MUST be attributed to the trusted tenant.
- **FR-025**: `capture_lead` MUST be rate-limited per session at a default of 5 writes per session per hour, configurable per tenant via `tenant_settings.rate_limit_lead_per_session`. The 6th call MUST return `{status: "rate_limited"}` and emit a `lead.rate_limited` audit entry.
- **FR-026**: `escalate` MUST INSERT a real row into `escalation_tickets` (table already in migration 0004); the returned `ticket_id` MUST match the inserted row's UUID; only one escalation per session is permitted (subsequent calls return the existing ticket_id); a cross-tenant assertion MUST run at INSERT time.
- **FR-027**: Tickets created by `escalate` MUST surface in `GET /escalations` (endpoint #5) for the correct tenant within the next page render.
- **FR-028**: Short-term session memory MUST live in Redis under the key `session:{tenant_id}:{session_id}` with a TTL of 1800 seconds and a max of 12 messages per session. Messages MUST be redacted before write.
- **FR-029**: If Redis is unavailable, the chat path MUST continue without memory and emit one `memory.unavailable` audit-log entry per session; the visitor MUST NOT see an error.
- **FR-030**: The platform system prompt MUST live at [app/prompts/system_prompt.md](../../app/prompts/system_prompt.md) under version control; the file MUST parse at load time into three labelled blocks: PLATFORM_SYSTEM (locked), TENANT_PERSONA (placeholder for runtime injection), and TOOL_SCHEMAS (generated from Pydantic models).
- **FR-031**: The per-tenant persona block (persona_name, tone, business_rules) MUST be injected at runtime from `tenant_agent_configs` via endpoint #2; no per-tenant string MAY live in code.
- **FR-032**: When a tenant admin updates the persona via endpoint #1, the next visitor message MUST use the new persona without an app restart.
- **FR-033**: A prompt-change PR MUST be blocked from merging if the agent-tool eval (`evals/agent_tool.py`) drops below the threshold defined in `eval_thresholds.yaml`.
- **FR-034**: The platform system block MUST remain the system role at LLM invocation; the tenant persona block MUST be labelled as a lower-trust user-supplied region; platform refusal patterns MUST still fire regardless of persona text.

### Functional Requirements — Architectural / cross-cutting

- **FR-035**: No new container, image, or Compose service MAY be added; the lean-image audit MUST continue to pass.
- **FR-036**: No new dev-header authentication surface MAY be added; the existing `CONCIERGE_ENV=dev` guard MUST remain the only path that honors `X-Concierge-*` headers.
- **FR-037**: Exactly two new database migrations MAY land — `0005_admin_invites_revoked_at.py` and `0006_tenant_settings.py` (plus a single ADD COLUMN for `tenant_settings.rate_limit_lead_per_session`); no new tables.
- **FR-038**: All existing RLS policies MUST be preserved; every new repository method MUST take `tenant_id` explicitly OR set `app.tenant_id` via the existing `_tenant_context()` pattern.
- **FR-039**: This feature MUST NOT write to `rag_chunks`, `messages`, or `traces` tables. Those remain owned by other phases.
- **FR-040**: All five existing CI eval gates (classifier, rag, agent-tool, red-team, redaction) MUST remain green. The agent-tool eval graduates from mock to real evaluator within this feature.
- **FR-041**: The smoke E2E suite MUST remain green; one new probe per new write endpoint MUST be added to the cross-tenant E2E.

### Key Entities

- **Agent Config (`tenant_agent_configs`)**: per-tenant persona record — `persona_name`, `greeting`, `tone`, `language`, `business_rules`, `chips[0..6]`. Source of truth for tenant-specific prompt injection (FR-031).
- **Escalation Ticket (`escalation_tickets`)**: a real row created by the `escalate` tool, surfaced in the admin Escalations tab; fields include `ticket_id`, `tenant_id`, `conversation_id`, `status`, `assignee_id`, `opened_at`, `last_message_excerpt`.
- **Tenant Setting (`tenant_settings`)**: platform-tunable per-tenant limits — `default_invite_ttl_seconds`, `rate_limit_chat_per_minute`, `rate_limit_token_per_minute`, `rate_limit_lead_per_session`.
- **Admin Invite revoke marker**: `admin_invites.revoked_at` timestamp column added by migration 0005; consumed by the revoke + status-check paths.
- **Audit Log entry (`audit_logs`)**: existing table; consumed by 8 new Track-1 vocab entries + 8 new Track-2 vocab entries. Metadata redacted before persist.
- **Session Memory (Redis)**: key `session:{tenant_id}:{session_id}`, value list of redacted messages, TTL 1800 s, max 12 entries.
- **Platform System Prompt**: single version-controlled file at `app/prompts/system_prompt.md`, parsed into PLATFORM_SYSTEM + TENANT_PERSONA + TOOL_SCHEMAS blocks at load.
- **Tool argument schemas**: Pydantic models `RagSearchArgs`, `CaptureLeadArgs`, `EscalateArgs`; `extra=forbid`; the boundary at which LLM-supplied `tenant_id` is stripped.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tenant admin can walk all 9 of their tabs on a healthy stack without seeing a single "(placeholder)" badge.
- **SC-002**: A tenant manager can walk all 6 of their tabs on a healthy stack without seeing a single "(placeholder)" badge.
- **SC-003**: Across 100 randomly seeded visitor messages, ≥ 80 % are served by the workflow path (high-confidence labels) and ≤ 20 % reach the agent — proving the agent handles the hard turns, not the bulk.
- **SC-004**: For every multi-tool ambiguous turn in the curated "Friday demo" set (≥ 5 turns spanning rag→lead, rag→escalate, lead→escalate combinations), the agent completes within the 5-iteration / 4000-token caps and produces the expected side-effects (lead row OR escalation row OR both).
- **SC-005**: Forged-JWT cross-tenant probes against every new endpoint return a byte-identical 403 response body — no field, header, or timing channel discloses which check failed.
- **SC-006**: A prompt-injection adversarial test (`tests/security/test_agent_prompt_injection.py`) confirms that no LLM-supplied `tenant_id`, `session_id`, or `actor_id` reaches any tool function; cross-tenant lead-write attempts fail closed.
- **SC-007**: The 6th `capture_lead` call within a single session within an hour returns `rate_limited` and a `lead.rate_limited` audit-log entry is recorded; 100 % consistency across replays.
- **SC-008**: A real `escalation_tickets` row is created on every `escalate` tool call; the row appears in the tenant admin's Escalations tab on the next page render within 5 seconds.
- **SC-009**: A tenant admin's persona change is reflected in the next visitor message within 60 seconds and without any container restart.
- **SC-010**: A deliberately-bad prompt edit fails the CI agent-tool eval and blocks the merge; reverting the edit unblocks the merge — both within one CI run cycle.
- **SC-011**: Every admin save action surfaces a loading indicator within 200 ms and a success/error toast within 2 seconds of the request returning.
- **SC-012**: All five existing eval gates (classifier, rag, agent-tool, red-team, redaction) and the lean-image audit, smoke-e2e, lint, and build jobs are green on the merged PR.
- **SC-013**: When the Redis container is stopped mid-session, the next chat turn still completes; exactly one `memory.unavailable` audit-log entry is recorded; no visitor-facing error appears.
- **SC-014**: A reviewer walking the demo flow in [RUNBOOK.md](../../RUNBOOK.md) §Demo Flow steps 1–9 reaches "All CI required checks green" without intervention beyond the documented operator actions.

---

## Assumptions

- **Tenant Manager dashboard exists** as the placeholder/minimal surface shipped in feature 008/009 and is enhanced — not rebuilt — by this feature.
- **Existing JWT auth deps are correct as-is**: `require_tenant_admin`, `require_admin_session`, `get_tenant_id_from_widget_token` are not modified; new routes pick the right dep from this set.
- **LLM provider is treated as a substitution point**: the choice of LLM vendor (Anthropic Claude vs OpenAI vs local) is made in `/speckit-clarify` or `/speckit-plan` and recorded in DECISIONS.md; the spec does not pin a vendor.
- **pgvector indexing remains a follow-on (BLOCKED.md N1)**: `rag_search` uses the lexical baseline only in this feature; the published index path is not part of acceptance.
- **`messages` table durable persistence is out of scope**: Redis short-term memory is the only conversation memory layer shipped here; durable message storage remains tracked under BLOCKED.md N2.
- **`traces` table writes are out of scope**: observability stays at stdout via existing `widget_logging`; traces table population is a later observability feature.
- **No realtime layer**: WebSocket and SSE are explicitly excluded; admin pages refresh on Streamlit rerun; widget chat remains synchronous request/response.
- **Constitution holds**: tenant isolation (Principle I), trusted tenant_id (Principle II), bounded agent (Principle III), in-memory widget token (Principle IV), lean serving (Principle V), audit-every-write (Principle VI), simplest-defensible-implementation (Principle VII) — all preserved.
- **Existing eval golden sets remain authoritative**: feature does not introduce new golden sets; thresholds in `eval_thresholds.yaml` are unchanged.
- **Two-track delivery dovetail is mechanical**: Track 2's `EscalationRepository.create()` lands before Track 1's `PATCH /escalations/{id}` PR ships; Track 1's `PUT /tenants/{tid}/agent-config` lands before Track 2's prompt loader PR ships. Order enforced in `/speckit-plan`.
- **Admin desktop ceiling holds**: 1280 px minimum viewport remains a tested baseline; no mobile admin work is in scope (Decision 15).
- **Audit-log vocabulary additions are additive**: existing audit consumers (Audit tab readers) ignore unknown action strings, so additions do not break the read path.
