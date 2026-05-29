# New audit-log vocabulary

16 new action strings introduced by this feature. All metadata fields pass through `app/infra/redaction.py` before persist. None contain message content.

## Track 1 (8 entries)

| action | Emitter | Metadata fields |
|---|---|---|
| `tenant.agent_config_updated` | service `AgentConfigService.put` | `actor_id`, `changed_fields` (names only) |
| `tenant.settings_updated` | service `TenantSettingsService.upsert` | `actor_id`, `changed_fields` |
| `cms.page_published` | service `CmsPageService.set_status` (target=`published`) | `actor_id`, `page_id`, `slug` |
| `cms.page_unpublished` | same (target=`draft` or `archived`) | `actor_id`, `page_id`, `slug` |
| `escalation.status_changed` | service `EscalationService.patch` (per delta) | `actor_id`, `ticket_id`, `from_status`, `to_status` |
| `escalation.assignee_changed` | same | `actor_id`, `ticket_id`, `from_assignee_id`, `to_assignee_id` |
| `admin.invite_revoked` | service `AdminInviteService.revoke` | `actor_id`, `invite_token_hash` (sha256 first 16 hex chars; raw token never stored) |
| `admin.invite_resent` | service `AdminInviteService.resend` | `actor_id`, `invite_token_hash`, `new_expires_at` |

## Track 2 (8 entries)

| action | Emitter | Metadata fields |
|---|---|---|
| `escalation.created` | repo `EscalationRepository.create` (called by `escalate` tool) | `session_id`, `ticket_id`, `reason_excerpt` (≤ 80 chars, redacted) |
| `lead.rate_limited` | tool `capture_lead` on bucket cap | `session_id`, `count_in_window`, `window_seconds: 3600` |
| `memory.unavailable` | service `ChatService` on Redis error (once per session) | `session_id`, `error_kind` |
| `agent.turn_started` | agent loop entry | `session_id`, `route_reason` (e.g., `"ambiguous_label"`, `"low_confidence"`, `"modelserver_unavailable"`) |
| `agent.tool_called` | agent loop per tool invocation | `session_id`, `tool_name`, `iteration` |
| `agent.turn_completed` | agent loop normal exit | `session_id`, `iterations`, `total_tokens` |
| `agent.iteration_cap_hit` | agent loop cap-hit path (iterations) | `session_id`, `iterations`, `total_tokens` |
| `agent.token_cap_hit` | agent loop cap-hit path (tokens) | `session_id`, `iterations`, `total_tokens` |

## Conventions (preserved from existing vocabulary)

- Action strings are dot-separated, lowercase, snake_case after the dot.
- `actor_id` field present iff there is a human or admin actor — absent for Track-2 agent events whose actor is the system itself.
- `tenant_id` is set at the audit row level (column on `audit_logs`), never in metadata.
- No raw PII, no raw tokens, no full prompt strings, no message content in any metadata field. Excerpts ≤ 80 chars and redacted.

## CONTRACT.md update

This vocabulary lands in [CONTRACT.md](../../../CONTRACT.md) §730–743 in the same PR that emits each action. Adding a row to the table is part of the per-endpoint task triplet in `tasks.md`.
