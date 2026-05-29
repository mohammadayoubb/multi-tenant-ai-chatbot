# Track-2 internal contracts — agent + tools + memory + prompts

These contracts are internal to `app/agent/` and `app/prompts/`. They are not HTTP routes, but they are the seams the rest of the system depends on.

## C-T2-1 — `RouteDecision` (router output)

```python
@dataclass(frozen=True)
class RouteDecision:
    route: Literal["blocked", "rag_search", "capture_lead", "escalate", "agent"]
    reason: str               # human-readable, never shown to visitor; for audit
    confidence: float         # NEW in this feature; 0.0..1.0
```

Producer: `app/agent/router.py::route_message_decision(message: str) -> RouteDecision`.
Consumer: `app/services/chat_service.py::_execute_decision(...)`.

**Decision rule** (FR-014, FR-015, FR-016, FR-017):

| Classifier output | RouteDecision |
|---|---|
| `label = "spam"`, any confidence | `route = "blocked"` |
| `label ∈ {"faq","sales_or_contact","human_request"}` and `confidence ≥ ROUTER_CONFIDENCE_THRESHOLD` | `route = label` (workflow path) |
| `label = "ambiguous"`, any confidence | `route = "agent"` |
| any label, `confidence < ROUTER_CONFIDENCE_THRESHOLD` | `route = "agent"` |
| modelserver 5xx / timeout | `route = "agent"`, reason includes `"modelserver_unavailable"` |

`ROUTER_CONFIDENCE_THRESHOLD` default `0.70`, override via env var.

## C-T2-2 — Tool argument schemas (Pydantic)

Module: `app/agent/tools.py`. All schemas use `model_config = ConfigDict(extra="forbid")`.

```python
class RagSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)

class CaptureLeadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None    = Field(default=None, min_length=1, max_length=200)
    contact: str | None = Field(default=None, pattern=r"^([\w\.\-+]+@[\w\-]+\.[\w\.\-]+|[\+\d][\d\s\-\(\)]{6,})$")
    intent: str         = Field(min_length=1, max_length=1000)

class EscalateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=280)
```

Tool function signatures (unchanged from current):

```python
async def rag_search(*, tenant_id: UUID, query: str, top_k: int, session) -> dict
async def capture_lead(*, tenant_id: UUID, session_id: str, name, contact, intent, session) -> dict
async def escalate(*, tenant_id: UUID, conversation_id: str, reason: str) -> dict
```

`tenant_id`, `session_id`, `conversation_id` are passed by the **caller** (`ChatService` / agent loop) from trusted context. No tool argument exists for any of these — the Pydantic schema makes that physically impossible.

## C-T2-3 — Agent loop bounds

Module: `app/agent/agent.py`.

```python
MAX_AGENT_ITERATIONS = 5
MAX_AGENT_TOKENS_PER_TURN = 4000
```

Loop contract:

1. On entry: emit `agent.turn_started` audit (metadata: `{session_id, route_reason}`).
2. Per iteration:
   - Call LLM with current message history + tool schemas.
   - If LLM returns text only → return as final answer, emit `agent.turn_completed`, done.
   - If LLM returns tool_use → validate args with the Pydantic schema (T2-2), execute the tool, append tool result to history, emit `agent.tool_called` (metadata: `{tool_name, iteration}`).
   - Tally tokens from `response.usage`. If `iterations >= 5` OR `cumulative_tokens >= 4000`: break with cap-hit path.
3. Cap-hit path:
   - Call `escalate(reason="agent_cap_hit")` once.
   - Return safe message `"I'm not able to help with that right now — I've escalated this so a human can follow up."`.
   - Emit `agent.iteration_cap_hit` or `agent.token_cap_hit` (whichever fired) with metadata `{iteration_count, token_total}`.

The loop MUST NEVER call `capture_lead` on the cap-hit path. Escalate is the only safe-default destructive action under uncertainty.

## C-T2-4 — `capture_lead` rate limit

Bucket key: `lead:{tenant_id}:{session_id}`. Window: 1 hour rolling. Cap: `tenant_settings.rate_limit_lead_per_session` (default 5).

On cap-hit, the tool returns:

```python
{"status": "rate_limited", "tenant_id": str(tenant_id), "session_id": session_id}
```

The agent, on seeing `rate_limited`, surfaces the visitor-facing message:

> "I've already captured your details — the team will reach out shortly."

And emits `lead.rate_limited` audit (metadata: `{session_id, count_in_window: 5}`).

## C-T2-5 — `escalate` real INSERT

`EscalationRepository.create()` is added in Phase B2 (Track 2 prerequisite). Signature:

```python
async def create(
    self, *,
    tenant_id: UUID,
    conversation_id: str,
    reason: str,
    last_message_excerpt: str | None,
) -> EscalationTicket
```

Cross-tenant assertion: the repo MUST set `app.tenant_id` via `TenantRepository._tenant_context()` AND verify the inserted row's `tenant_id` matches the parameter — both checks.

`escalate` tool: on first call within a session, INSERT and emit `escalation.created` audit. On subsequent calls within the same session, fetch and return the existing ticket_id (no second INSERT). One escalation per session is the rule.

## C-T2-6 — Prompt loader

Module: `app/prompts/loader.py` (new, ≤ 80 lines).

Parses `app/prompts/system_prompt.md` (file format updated in Phase B'3) into three named sections delimited by HTML-comment markers:

```markdown
<!-- PLATFORM_SYSTEM:start -->
You are the Concierge platform assistant. ...
[locked platform refusals, tool-use guidance, output format]
<!-- PLATFORM_SYSTEM:end -->

<!-- TENANT_PERSONA:placeholder -->
{{TENANT_PERSONA}}
<!-- TENANT_PERSONA:end -->

<!-- TOOL_SCHEMAS:placeholder -->
{{TOOL_SCHEMAS}}
<!-- TOOL_SCHEMAS:end -->
```

At process start: parse the file once; cache PLATFORM_SYSTEM string and TOOL_SCHEMAS-rendered JSON (generated from Pydantic models).

Per request: fetch the tenant agent_config via `AgentConfigRepository.get_by_tenant(tenant_id)`; render the TENANT_PERSONA block as:

```text
<tenant_persona owner="tenant_admin" trust="lower-than-platform">
Persona name: {persona_name}
Tone: {tone}
Business rules: {business_rules}
</tenant_persona>
```

Final prompt sent to LLM has `system = PLATFORM_SYSTEM + "\n\n" + rendered_persona + "\n\n" + TOOL_SCHEMAS`.

Cache invalidation: the per-tenant persona is read fresh on every request — no cross-request cache (research §R10).

## C-T2-7 — Memory contract

Key format: `session:{tenant_id}:{session_id}`. TTL 1800 s. Max 12 messages. Redacted before write (already in `ChatService`).

On Redis unavailable: continue without memory; emit `memory.unavailable` once per session (tracked via a per-process set of seen session_ids that resets on process restart).

## C-T2-8 — Out-of-scope guards (binding negative contracts)

The following are explicitly **forbidden** by this feature:

- No write to `rag_chunks` (N1 follow-on).
- No write to `messages` table (N2 follow-on). Redis is the only memory layer.
- No write to `traces` table (observability follow-on).
- No new bucket type in `RateLimiterService` beyond the `lead:{tenant_id}:{session_id}` one.
- No WebSocket / SSE endpoint.
- No new Compose service.
- No new dev-header surface.

If a Phase 2 task in `tasks.md` would violate one of these, the planner has erred — refuse the task.
