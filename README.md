# Owner: Hiba
# Week 8 — Concierge

Concierge is a multi-tenant AI SaaS platform where businesses can sign up, manage website content in a CMS, configure their AI agent, and embed a public chat widget on their website.

The most important requirement is tenant isolation: a visitor chatting with Tenant A must never access Tenant B's content, conversations, leads, vectors, prompts, or configuration.

## Team

| Member | Name | Main Ownership |
|---|---|---|
| Member A | Hiba | Platform, tenancy, isolation, provisioning |
| Member B | Nasser | Agent, RAG, router, tools, memory |
| Member C | Ayoub | Classifier, model server, guardrails, security |
| Member D | Amer | Widget, admin UX, CI/CD |

## Main Stack

- FastAPI backend
- PostgreSQL + pgvector
- Redis
- MinIO
- Vault
- Streamlit admin panel
- React/Vite embeddable widget
- Lean model server using ONNXRuntime / scikit-learn
- Guardrails sidecar
- GitHub Actions CI/CD

## Run Locally

```bash
cp .env.example .env
docker compose up --build
```

## Embed the widget

Drop this on any page served from an origin in your tenant's allowlist:

```html
<script
  src="https://YOUR-CONCIERGE-HOST/widget.js"
  data-widget-id="YOUR_WIDGET_ID"
  data-backend-url="https://YOUR-CONCIERGE-HOST"
></script>
```

`YOUR_WIDGET_ID` comes from the admin UI's widget configuration page for the tenant. The page that loads this snippet must be served from an origin on the tenant's allowlist — the server validates the request `Origin` against that list before issuing a session token, so a snippet on a non-allowlisted page will silently fail to start a session.

## Required Docs

- `PROJECT_PLAN.md`
- `CLAUDE.md`
- `DESIGN.md`
- `SPEC.md`
- `DECISIONS.md`
- `RUNBOOK.md`
- `EVALS.md`
- `SECURITY.md`


