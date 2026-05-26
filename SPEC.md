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

## Using Spec Kit

This repo uses [GitHub Spec Kit](https://github.com/github/spec-kit) for feature work. The project constitution lives at [.specify/memory/constitution.md](.specify/memory/constitution.md) — read it before opening a feature.

### Install (one time)

```bash
uv tool install specify-cli
```

### Standard flow (most features)

```
/speckit-specify    # write the feature spec
/speckit-plan       # produce the implementation plan; Constitution Check gates here
/speckit-tasks      # break the plan into tasks
/speckit-implement  # execute
```

### Risky flow

Use the risky flow for: auth, tenant isolation, RLS, widget token, service-to-service auth, guardrails, tenant erasure, CI eval gates, or any repository function touching a tenant-owned table.

```
/speckit-specify
/speckit-clarify    # surface ambiguity before planning
/speckit-plan
/speckit-tasks
/speckit-analyze    # cross-artifact consistency check
/speckit-implement
```

Each teammate runs these for their own feature; per-feature artifacts land under `.specify/specs/<feature-slug>/`. Templates under `.specify/templates/` are shared scaffolds — propose changes via PR.
