# Owner: Hiba
# Week 8 Project Plan — Concierge

## Team Ownership

| Member | Name | Primary Ownership |
|---|---|---|
| Member A | Hiba | Platform, tenancy, isolation, provisioning |
| Member B | Nasser | Agent, RAG, router, tools, memory |
| Member C | Ayoub | Classifier, model server, guardrails, security |
| Member D | Amer | Widget, admin UX, CI/CD |

## Goal

Build Concierge: a multi-tenant AI SaaS where businesses manage CMS content, configure an AI agent, and embed a secure widget on their public website.

The main grading point is tenant isolation. Tenant A must never access Tenant B's data.

## Five-Day Plan

### Monday — Specs and Skeleton

- Hiba: tenant model, RLS plan, roles, provisioning flow.
- Nasser: agent tool contracts, RAG contract, memory contract.
- Ayoub: classifier plan, modelserver shell, guardrails shell.
- Amer: Docker Compose, widget hello-world, GitHub Actions skeleton.

### Tuesday — Models, CMS, and RAG

- Hiba: tenant tables, RLS, auth roles.
- Nasser: CMS embeddings, pgvector retrieval, RAG golden set.
- Ayoub: train/evaluate classifier baselines, export artifact.
- Amer: admin UI pages and widget loader shell.

### Wednesday — Router and Agent

- Hiba: tenant-scoped repositories and provisioning API.
- Nasser: classifier router + bounded tool-calling agent.
- Ayoub: guardrails sidecar and redaction.
- Amer: widget token exchange and allowed origin checks.

### Thursday — Eval Gates and Erasure

- Hiba: tenant erasure path.
- Nasser: agent tool-selection eval and RAG eval.
- Ayoub: red-team eval and classifier CI gate.
- Amer: smoke test and full GitHub Actions pipeline.

### Friday — Polish and Demo

- Everyone: final integration, CI green, demo practice, documentation review.
