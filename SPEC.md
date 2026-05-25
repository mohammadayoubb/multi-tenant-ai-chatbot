# Owner: Nasser
# SPEC.md — Component Contracts

## Tenant Contract

Every tenant-owned table must include:

- `tenant_id`
- `created_at`
- `updated_at`

No request may accept `tenant_id` from the body as trusted input.

## Widget Token Contract

The widget token must contain:

- `tenant_id`
- `widget_id`
- `origin`
- `session_id`
- `exp`

## Agent Tool Contracts

### rag_search

Input: tenant_id, query, top_k.

Output: answer, cited chunks, retrieval scores.

### capture_lead

Input: tenant_id, conversation_id, name, contact, intent.

Output: lead_id, status.

### escalate

Input: tenant_id, conversation_id, reason.

Output: ticket_id, status.
