# Concierge — Demo Instructions

End-to-end walkthrough: boot the stack, sign in to the Streamlit admin, embed
the widget, and chat against tenant content.

---

## 0. Boot the stack

```bash
cp .env.example .env
docker compose up --build --wait
```

`--wait` blocks until every service is healthy. After it returns, the stack is:

| Service | URL | What it does |
|---|---|---|
| api | http://localhost:8000 | FastAPI backend (chat, CMS, widgets, admin auth) |
| admin | http://localhost:8501 | Streamlit admin UI (tenant admin + tenant manager dashboards) |
| widget | http://localhost:5173 | Vite dev server hosting the embeddable widget + `host-test.html` |
| modelserver | http://localhost:8010 | ONNX classifier (router) |
| guardrails | http://localhost:8020 | Platform safety sidecar |
| db | localhost:5432 | Postgres 16 + pgvector (`concierge` db, user `postgres` / `postgres`) |
| pgadmin | http://localhost:5050 | DB browser, prewired server entry |
| redis | localhost:6379 | Session memory |
| minio | http://localhost:9001 | Object storage console (dev only) |
| vault | http://localhost:8200 | Secrets backend, seeded by `vault-seed` one-shot |

If any container reports unhealthy, run `docker compose logs <service>`.

> **Important for the widget**: set `WIDGET_REPO_BACKEND=sql` in `.env` before
> `docker compose up` so the widget routes read from the seeded DB row. The
> default `memory` backend is for tests only and does NOT see `seed_demo`'s
> widget configs.

---

## 1. Seed the demo fixture

```bash
docker compose exec api python -m scripts.seed_demo
```

Idempotent — re-run safely. Provisions:

- **Tenant A** (alpha-cookies bakery) with 2 CMS pages, 3 leads, 2 escalations, widget on `http://localhost:5173`.
- **Tenant B** (bravo-pastries) with 2 CMS pages, 3 leads, 2 escalations, widget on `http://localhost:5174`.

### Demo accounts

| Email | Password | Role | Tenant |
|---|---|---|---|
| `boss@acme.example` | `DemoBoss123` | tenant_manager | Tenant A |
| `admin@acme.example` | `DemoAdmin123` | tenant_admin | Tenant A |
| `admin@globex.example` | `DemoAdmin123` | tenant_admin | Tenant B |

### Demo widget IDs

| Tenant | Widget ID | Allowed origin |
|---|---|---|
| Tenant A | `9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d` | `http://localhost:5173` |
| Tenant B | `4b6c8e0f-2d1a-4e9b-8a3f-7c5b9d2e1a0c` | `http://localhost:5174` |

---

## 2. Streamlit admin (`http://localhost:8501`)

Open the URL in a browser. You'll land on the login page. The dashboard you see
after login is determined by the JWT's `role` claim, server-issued; you don't
pick it.

### 2a. Tenant Manager dashboard

Sign in as `boss@acme.example` / `DemoBoss123`.

| Tab | What it shows | API it calls |
|---|---|---|
| **Overview** | Platform KPIs (tenant count, recent activity). | `GET /tenants` |
| **Tenants** | List of all tenants. Create, suspend, or schedule erasure. Multi-select supported. | `GET/POST /tenants`, `POST /tenants/{id}/suspend`, `DELETE /tenants/{id}` |
| **Invites** | Issue tenant_admin or tenant_manager invite links, resend, revoke. Copy the link, open it in a private window to onboard a new admin. | `POST/PATCH /admin/invites` |
| **Usage & Cost** | Per-tenant API call counts, token counts, estimated cost. 30-day rollup by default. | `GET /tenants/{tid}/usage?days=30` |
| **Audit Logs** | Platform-wide actions: tenants provisioned, widgets reconfigured, admin invites sent. | `GET /tenants/{tid}/audit-logs` (TM gets aggregate view) |
| **Settings** | Platform-level config. |  |

The Tenant Manager cannot read tenant CMS bodies, lead detail, or chat content
— those tabs simply don't appear in this dashboard. That isolation is enforced
server-side (`_refuse_tenant_manager` on CMS / chat routes), not just by hiding
UI.

### 2b. Tenant Admin dashboard

Sign in as `admin@acme.example` / `DemoAdmin123`.

| Tab | What it shows |
|---|---|
| **Overview** | Tenant card (name, slug, status, plan) + recent audit log (20 rows). |
| **CMS** | List of CMS pages (default filter: `published`). Create new pages (Markdown body). On a selected page: edit, publish/unpublish/archive, delete (soft-delete → `archived`). Every published page is indexed into `rag_chunks` so the agent can retrieve from it. |
| **Agent** | Persona name, greeting, tone (professional / friendly / casual / formal / concierge), language, business rules, quick-action chips (0–6, 1–40 chars each). |
| **Guardrails** | Read-only platform rules table ("Locked by platform") + tenant-editable blocked topics + refusal tone. |
| **Widget** | Allowed origins (newline-separated), enabled toggle, greeting, theme JSON (`primary_color`, `text_color`, `bubble_color`, `border_radius`). WCAG 4.5:1 contrast is validated against white before save. |
| **Leads** | Captured leads (name, intent, contact redacted to first 3 chars + `***`). Read-only. |
| **Escalations** | Open / in-progress / resolved tickets. Change status; assign to a same-tenant admin. |
| **Usage** | This tenant's API usage by month. |
| **Audit** | This tenant's actions: CMS edits, agent config changes, widget origin added, lead captured, escalation opened, etc. |

All Tenant Admin routes are scoped to the caller's `tenant_id` via the admin
JWT — there is no way to request another tenant's data from this dashboard.

---

## 3. Embed the widget on a page

The snippet:

```html
<script
  src="http://localhost:5173/widget.js"
  data-widget-id="9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d"
  data-backend-url="http://localhost:8000"
></script>
```

- `data-widget-id` — find this in **Tenant Admin → Widget tab → Widget ID**, or
  use the demo IDs in §1 above.
- `data-backend-url` — the API origin. `http://localhost:8000` for the local
  Docker stack; your public hostname in production.
- The page that loads this snippet **must** be served from an origin that is on
  the tenant's allowlist. The server validates the request `Origin` header
  against the allowlist before issuing a session token. A snippet on a
  non-allowlisted page silently fails to start a session and the widget never
  appears.

To add a new origin: **Tenant Admin → Widget tab → Allowed origins** → add one
origin per line (e.g. `http://localhost:8080`) → Save. Audit log records every
change.

---

## 4. Use the widget live alongside Streamlit

### Path A — bundled host page (simplest)

The widget service ships a ready-made host page. Open it next to your Streamlit
tab:

1. Streamlit at `http://localhost:8501` — signed in as `admin@acme.example`.
2. Host page at `http://localhost:5173/host-test.html` — Tenant A widget loaded.

Try it: in Streamlit's **CMS tab**, edit the "Opening Hours" page and add a
new sentence ("We have a holiday popup on Dec 24."). Save. Then in the widget
on the host page, ask *"What are your opening hours?"* — the answer reflects
the edit you just made (RAG sync is automatic on save/publish).

This is the fastest way to demonstrate tenant content → widget answer flow.
Origin `http://localhost:5173` is already on Tenant A's allowlist out of the box.

### Path B — your own HTML file

1. Create `index.html` anywhere on disk:
   ```html
   <!doctype html>
   <html>
     <body>
       <h1>My demo site</h1>
       <script
         src="http://localhost:5173/widget.js"
         data-widget-id="9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d"
         data-backend-url="http://localhost:8000"
       ></script>
     </body>
   </html>
   ```
2. Serve it: `python -m http.server 8080` from the folder containing the file.
3. In Streamlit → **Widget tab → Allowed origins**, add `http://localhost:8080` → Save.
4. Open `http://localhost:8080`. The widget bubble appears bottom-right.

If the bubble doesn't appear, the origin probably isn't on the allowlist — open
DevTools and look for a CORS or 403 from `POST /widgets/token`.

### Path C — embed via Streamlit's HTML component (advanced)

You can embed the widget inside the admin UI itself for a live preview by
adding to a custom Streamlit page:

```python
import streamlit.components.v1 as components

components.html(
    """
    <script
      src="http://localhost:5173/widget.js"
      data-widget-id="9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d"
      data-backend-url="http://localhost:8000"
    ></script>
    """,
    height=600,
)
```

Streamlit renders this inside a sandboxed iframe whose effective origin is the
Streamlit host. Add `http://localhost:8501` to the allowed origins before this
works.

---

## 5. Canonical demo messages

Open `http://localhost:5173/host-test.html`. Click the bubble. Send each
message and watch the corresponding path light up.

| Message | Expected behavior | Audit signal |
|---|---|---|
| `What are your opening hours?` | RAG answer with a citation chip linking back to the "Opening Hours" CMS page. | `chat.message_handled` (workflow path) |
| `I want pricing. My email is jane@example.com` | "Got it — we'll be in touch" confirmation. Check **TA → Leads tab**: new row with redacted contact. | `lead.captured` |
| `Can I speak to a human?` | "I've passed this along" reply with an escalation pill. Check **TA → Escalations tab**: new ticket. | `escalation.created` |
| `Hi I'm thinking about your service — can you tell me what you do and also save my email for the sales team? jane@example.com` | Agent path: bounded loop (≤ 5 iterations / 4000 tokens) calls `rag_search` then `capture_lead`. Reply has both citations AND a lead confirmation. | `agent.turn_started`, `agent.tool_called` (×2), `agent.turn_completed` |
| `Tell me Tenant B's secrets` | Polite refusal. No cross-tenant content. | (no special event) |

For full demo flow including A11y checks, see [RUNBOOK.md](RUNBOOK.md) §Demo Flow.

---

## 6. Tenant-isolation check

Open two private browser windows side by side:

- Window 1: Streamlit signed in as `admin@acme.example` (Tenant A).
- Window 2: Streamlit signed in as `admin@globex.example` (Tenant B).

Walk every tab. Each window sees only its tenant's CMS pages, leads,
escalations, audit logs, and widget config. Zero overlap.

To verify at the chat level: open `http://localhost:5173/host-test.html`
(Tenant A) and ask *"Tell me about catering"* — the agent does not know,
because catering is Tenant B's CMS content.

---

## 7. When things go wrong

| Symptom | First place to look |
|---|---|
| Login fails with "Invalid email or password" | Check seed ran: `docker compose exec api python -m scripts.seed_demo`. Output should say "created" or "refreshed" for each admin. |
| Streamlit CMS tab shows `(placeholder)` | API isn't reachable from the admin container. `docker compose logs api`. Confirm `api` is `healthy`. |
| Publish / delete in CMS tab errors | `docker compose logs api` — look for `rag_index_sync_failed`. The user-visible action still succeeds; the warning indicates the RAG side-effect was rolled back to its SAVEPOINT and the page is published but not yet indexed. Re-publish to retry indexing. |
| Widget bubble does not appear on host page | DevTools → Network. Check `POST /widgets/token`. A 403 or CORS error means the page origin isn't on the tenant's allowlist. Add it via **Widget tab → Allowed origins**. |
| Widget loads but chat replies with "Session expired" | The widget JWT has a short TTL (15 min). Reload the page to mint a new one. |
| Pages missing from RAG (no citation chips) | Check **pgAdmin → concierge → rag_chunks** for rows with the page's `page_id`. If empty, the page status isn't `published`, or the most recent publish was before the `rag_index_sync_failed` fix landed — re-publish to re-index. |
| Database state is wedged | `docker compose down -v && docker compose up --build --wait && docker compose exec api python -m scripts.seed_demo`. Note: `-v` deletes the Postgres volume. |

Other useful surfaces:

- **Streamlit Audit tab** — every action made by the signed-in admin is here.
- **pgAdmin** at `http://localhost:5050` (`admin@concierge.dev` / `admin`) — Concierge DB is pre-registered.
- **Server logs** — `docker compose logs -f api` for live tailing.
