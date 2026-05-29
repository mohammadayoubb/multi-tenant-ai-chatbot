# Research — 010 fe/be integration retrofit

Phase 0 output. Resolves the open decisions that the spec deliberately deferred.

## R1 — LLM provider for the Track-2 agent loop

**Decision:** Anthropic Claude (Sonnet 4.6 by default) via the `anthropic` Python SDK, with native function-calling.

**Rationale:**
- Native tool-calling API is well-matched to the bounded-agent pattern (FR-018, FR-019): tools declared via JSON Schema, the SDK returns tool_use blocks the loop can inspect for the cap check.
- Prompt caching support means the PLATFORM_SYSTEM block (locked, ~2 KB) is cached on first turn, reducing per-turn token cost — supports SC-003 (keep agent share low even when invoked).
- Claude 4.5/4.6/4.7 models have strong adherence to the "no destructive action under uncertainty" instruction the platform system prompt enforces.
- API key already routes through Vault (`vault read secret/data/llm/anthropic_api_key`); the existing `app/infra/vault.py` resolver accommodates a new key path without code change.

**Alternatives considered:**
- **OpenAI function-calling**: equivalent technical fit, but requires a second SDK dependency for the fallback case. Rejected for simplicity (Principle VII); keep one provider, swap-replaceable behind the loop abstraction if needed later.
- **Local Llama via Ollama**: rejected because it would pull a heavy runtime into the `api` container and breach the spirit of the lean-image principle even though it does not include `torch` / `transformers` literally.
- **Stay deterministic (current stub)**: rejected per blueprint floor ("the agent must genuinely handle multi-tool, ambiguous turns, not just sit behind the router as dead weight"). The current scaffold does not satisfy the user-observable Track-2 success criteria.

**Implementation note:** the loop in `app/agent/agent.py` wraps `client.messages.create(...)` with a hard iteration counter (5) and a running token tally (4000) computed from the response `usage` object. The decision is recorded in `DECISIONS.md` as Decision 19 in the Phase B'3 PR.

## R2 — `ROUTER_CONFIDENCE_THRESHOLD` default value

**Decision:** Default `0.70`, environment-tunable via `ROUTER_CONFIDENCE_THRESHOLD`.

**Rationale:**
- The existing ONNX classifier evaluator (`evals/classifier.py`) reports macro-F1 = 0.9752 with per-class F1s; a 0.70 confidence floor leaves room for the small DL model's known weak spots (`ambiguous` vs `sales_or_contact` boundary) to route to the agent rather than guess.
- 0.70 is the inflection point in the existing eval data where false-positive workflow routes start trending upward — empirically grounded in committed data.
- Env-tunable so an operator can dial up to 0.80 if production telemetry shows the agent share staying under the SC-003 target of ≤ 20 %.

**Alternatives considered:**
- **Fixed 0.50**: rejected — too permissive; would push every uncertain turn through the workflow and re-create the existing stub-router brittleness.
- **Per-label threshold table**: rejected as premature complexity (Principle VII); single threshold is sufficient to satisfy FR-015 and SC-003.

## R3 — LLM SDK and the lean-image audit

**Decision:** The `anthropic` Python SDK is allowed in the `api` container; the lean-image audit's torch/transformers ban is unaffected.

**Rationale:**
- The lean-image audit ([scripts/check_lean_images.sh](../../scripts/check_lean_images.sh)) targets `modelserver` and `guardrails` images only — verified by reading the script.
- The `anthropic` SDK pulls only `httpx`, `pydantic`, and a small set of utilities — no ML framework. `pip show anthropic` confirms a runtime footprint under 2 MB.
- The api container is not part of the "serving" image set the audit polices; the principle V quote — *"Serving containers (`modelserver`, `guardrails`) MUST NOT include `torch` or `transformers`."* — explicitly names the two affected images.

**Alternatives considered:** none — the audit's scope is fixed by spec 008 / Decision 11.

## R4 — Redis memory TTL justification (documenting the existing choice)

**Decision:** Keep TTL at `1800` seconds (30 minutes). Document the justification in the Memory section of DECISIONS.md as part of Phase B'3.

**Rationale (now made explicit):**
- 30 minutes covers a typical browsing session ("read two CMS pages, ask three follow-ups") with margin.
- Shorter than browser session-cookie defaults (typically 60+ min) — anonymous chat memory does not outlive the engagement.
- An anonymous visitor's chat is operational data with a fixed retention window, not durable customer data. Visitor never identified, never retrievable after TTL.

**Alternatives considered:** 600 s (too short for multi-page browse), 3600 s (too close to a "long retention" footing for anonymous data). Both rejected on the privacy-vs-utility tradeoff.

## R5 — Agent-config persona-block trust labeling

**Decision:** At LLM invocation, PLATFORM_SYSTEM is sent as the `system` role; TENANT_PERSONA is appended to the system role but wrapped in an explicit marker (`<tenant_persona owner="tenant_admin">...</tenant_persona>`) so the model is instructed to treat it as configuration, not instructions. Platform refusal patterns are restated within PLATFORM_SYSTEM as inviolable.

**Rationale:** FR-034 requires platform refusals to fire regardless of tenant persona text. The Anthropic-recommended pattern of labelling lower-trust regions inside the system role plus restating inviolable rules is well-attested and matches the way the guardrails sidecar already operates (defense in depth).

**Alternatives considered:**
- **Tenant persona as a user-role message**: rejected — would make the persona look like visitor input and complicate the model's interpretation of the actual visitor turn.
- **Two separate LLM calls (sanitize-then-act)**: rejected as cost-doubling complexity without commensurate safety gain.

## R6 — Per-session capture_lead bucket implementation

**Decision:** Extend `RateLimiterService` with a new bucket type keyed `lead:{tenant_id}:{session_id}`, default 5 writes / hour, configurable via `tenant_settings.rate_limit_lead_per_session` (column added in Phase A3). Bucket backing store: in-memory dict with a 1-hour expiry per key (same backing model as the existing widget-token IP bucket — process-cached, not Redis-shared).

**Rationale:** Matches the existing bucket pattern in [app/services/rate_limiter.py](../../app/services/rate_limiter.py); no new dependency. Per-session granularity is the right unit because the threat model is "an injected prompt within one visitor's session spams `capture_lead`" — cross-session aggregation is not in the threat surface.

**Alternatives considered:**
- **Redis-shared bucket**: rejected as overkill for a per-session check that the api process is the only writer to.
- **Per-tenant aggregate bucket**: rejected — a malicious tenant operator is not the threat model here; visitor-level spam is. Per-session is the correct scope.

## R7 — Migration 0006 + 0007 strategy for `rate_limit_lead_per_session`

**Decision:** Add the `rate_limit_lead_per_session INTEGER NOT NULL DEFAULT 5` column to `tenant_settings` inside migration `0006` itself (bundled). No separate 0007 migration.

**Rationale:** 0006 is already drafted but not yet merged. Adding one column in the same migration avoids a needless second alembic step and keeps the migration history compact. The column is additive with a safe default; existing rows inherit `5`.

**Alternatives considered:** Separate 0007 migration — rejected as unnecessary surface area. Constitutional Principle VII favors the smaller change.

## R8 — Existing service stubs to delete vs keep

**Decision:** During Phase E, delete [app/services/cms_service.py](../../app/services/cms_service.py) and [app/services/admin_settings.py](../../app/services/admin_settings.py); they are unused stubs replaced by `cms_pages.py` and `tenant_settings.py` respectively. Add a ruff rule banning new imports of either module to prevent regression.

**Rationale:** Both files are dead code per [backend-spec.md §6](../../backend-spec.md). Deleting them is one PR; a ruff rule is one line per banned module. Total surface gain: ≤ 5 lines, removes ~200 lines of misleading code.

**Alternatives considered:** Keep the stubs as documentation — rejected; Principle VII requires dead code be removed.

## R9 — Streamlit `st.dialog` confirm pattern for destructive actions

**Decision:** Use Streamlit's native `st.dialog` decorator for the confirm step on CMS delete (#12) and invite revoke (#8). Pattern: the destructive button opens a dialog that renders the consequence summary + two buttons (`Cancel` / `Confirm Delete`); only the confirm button fires the PATCH/DELETE.

**Rationale:** Already in use elsewhere (Decision 15 acknowledges `st.dialog` as the modal mechanism); no new dependency.

**Alternatives considered:** Inline two-step toggle (button-then-confirm) — rejected for accessibility regressions and Decision 15's documented preference for `st.dialog`.

## R10 — Where does the prompt loader cache invalidate?

**Decision:** `app/prompts/loader.py` caches the parsed `{PLATFORM_SYSTEM, TOOL_SCHEMAS}` blocks at module load (they are immutable after process start). The `TENANT_PERSONA` is per-request: fetched fresh from `AgentConfigRepository.get_by_tenant(tenant_id)` inside the request scope. No cross-request persona cache.

**Rationale:** A per-tenant persona update via #1 must reach the next visitor message inside 60 s (SC-009). Caching the persona would either require an invalidation message bus (out of scope) or accept a stale-persona window. Reading once per request is cheap (single row by primary key) and correct.

**Alternatives considered:**
- **In-process LRU with 60 s TTL**: rejected as premature complexity. The single-row read against an indexed table is < 1 ms.
- **Cross-request Redis cache**: rejected for the same reason plus introduces another fail mode.
