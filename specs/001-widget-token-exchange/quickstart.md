# Quickstart: Verify Widget Token Exchange Locally

End-to-end verification path for Amer after `/speckit-implement` finishes. Walks through (1) starting the stack, (2) seeding a test widget config, (3) exchanging a token via curl, (4) verifying the JWT decodes correctly, (5) loading a test host page and confirming the widget reaches "chat-ready" without putting anything in browser storage. Total time: < 5 minutes once the implementation is in place.

## Prerequisites

- Docker Desktop running.
- Repo cloned at `g:\multi-tenant-ai-chatbot`.
- `.venv` activated (already created via `uv venv --python 3.11`).
- `.env` file derived from `.env.example` with these added entries (placeholders only — never real production secrets):

  ```
  WIDGET_JWT_SECRET=dev-only-secret-do-not-ship-32bytes-min-aaaaaaaaaa
  WIDGET_LOG_SALT=dev-only-salt-32-bytes-base64-yyyyyyyyyyyyyyyyyy
  WIDGET_TOKEN_TTL_SECONDS=900
  WIDGET_RATE_PER_IP=10
  WIDGET_RATE_PER_WIDGET=60
  WIDGET_REPO_BACKEND=memory       # use the in-memory adapter while Hiba's migration is pending
  ```

## Step 1 — Bring up the stack

```powershell
docker compose up --build api
```

Wait until you see `Uvicorn running on http://0.0.0.0:8000`. (The other services aren't required for this feature.)

## Step 2 — Seed a test widget config

Because `WIDGET_REPO_BACKEND=memory`, the seed runs in-process via a one-shot script that talks to a not-yet-implemented admin endpoint. For Phase 1 verification, the in-memory adapter ships with a hard-coded test fixture:

| Widget ID | Tenant ID | Allowed origins | Enabled |
|---|---|---|---|
| `9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d` | `11111111-1111-1111-1111-111111111111` | `["https://customer-site.example", "http://localhost:5500"]` | `true` |

(This fixture lives inside `app/repositories/widget_repo.py` behind an `if backend == "memory":` branch and is removed the same PR that introduces the SQL adapter.)

## Step 3 — Exchange a token via curl

### Happy path

```powershell
curl.exe -X POST http://localhost:8000/widgets/token `
  -H "Content-Type: application/json" `
  -H "Origin: http://localhost:5500" `
  -d '{\"widget_id\":\"9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d\"}'
```

Expected:
```http
HTTP/1.1 200 OK
{"token":"eyJ...","expires_in":900,"session_id":"<uuid>"}
```

### Refusal — wrong origin (should be byte-identical to the next case)

```powershell
curl.exe -X POST http://localhost:8000/widgets/token `
  -H "Content-Type: application/json" `
  -H "Origin: https://attacker.example" `
  -d '{\"widget_id\":\"9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d\"}'
```

Expected:
```http
HTTP/1.1 403 Forbidden
{"error":"widget_unavailable"}
```

### Refusal — unknown widget (must match the previous response BYTE-FOR-BYTE)

```powershell
curl.exe -X POST http://localhost:8000/widgets/token `
  -H "Content-Type: application/json" `
  -H "Origin: http://localhost:5500" `
  -d '{\"widget_id\":\"00000000-0000-0000-0000-000000000000\"}'
```

Expected: same 403 with `{"error":"widget_unavailable"}`. Diff the two responses with `diff` or `Compare-Object` — they should differ only in `Date` header.

## Step 4 — Decode the JWT and verify claims

Use any JWT decoder (or [https://jwt.io](https://jwt.io), pasting the token in — note this is a dev token only, never paste production tokens into web tools).

Expected claim shape (per [data-model.md §2](data-model.md#2-widget-session-token-transient--jwt-not-persisted)):

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "widget_id": "9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d",
  "origin":    "http://localhost:5500",
  "session_id": "<uuid>",
  "iat": <unix-timestamp>,
  "exp": <iat + 900>
}
```

Signature must verify against `WIDGET_JWT_SECRET` using HS256.

## Step 5 — Load a test host page

Serve a simple host page from `http://localhost:5500` so its origin matches the allowlist:

```powershell
python -m http.server 5500 --directory frontend/widget/public
```

Then open `http://localhost:5500/host-test.html` in a browser (this file is a Phase 3 deliverable; for Phase 1 the test is curl-only).

### Browser-storage check

In Chrome DevTools → Application tab:

| Storage | Expected after token exchange |
|---|---|
| **Cookies** for `localhost:5500` and `localhost:8000` | empty of any token-shaped value |
| **Local Storage** for `localhost:8000` (iframe origin) | empty |
| **Session Storage** for `localhost:8000` | empty |
| **IndexedDB** | no Concierge database |

This is the visual confirmation of SC-004. The token should exist only in the iframe's JavaScript heap (visible in the Sources tab if you set a breakpoint in `api.ts`).

## Automated equivalent

Once `/speckit-implement` finishes, all of the above is covered by:

```powershell
pytest tests/security/test_widget_token.py -v
pytest tests/security/test_widget_token_redaction.py -v
pytest tests/unit/test_widget_service.py -v
```

Frontend storage check:

```powershell
cd frontend/widget
npm test -- --run
```

(The vitest suite uses jsdom; it asserts that `localStorage`, `sessionStorage`, and `document.cookie` are empty of any token-shaped value after a mocked successful exchange.)

## What "ready to merge" looks like

- All 3 backend test files green.
- Frontend storage-discipline test green.
- `ruff check .`, `mypy app/`, `docker compose build` all green.
- Manual curl walkthrough produces byte-identical 403 bodies across all refusal causes (the SC-002 manual sanity check).
- PR description tags @Hiba for `widget_configs` schema review and @Ayoub for the JWT-secret-from-env decision (so he knows to wire Vault later).
