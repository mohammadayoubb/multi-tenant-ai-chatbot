# Quickstart: Widget Loader Production Hardening

**Feature**: 003-widget-loader-hardening
**Audience**: Anyone on the team pulling this branch who wants to (a) run the tests, (b) sanity-check the loader in a real browser, or (c) inspect the production build output.

---

## Prerequisites

- Node 20+ and npm (the rest of the widget tooling already assumes this).
- `frontend/widget/node_modules` installed (`npm install` from `frontend/widget/` if missing).

No backend services are required for the automated tests. The browser sanity-check uses only the Vite dev server.

---

## 1. Run the loader tests

```sh
cd frontend/widget
npm test -- src/__tests__/loader.test.ts
```

Expected: all cases pass, including the contract clauses C1–C8 (see [contracts/widget-loader.md](./contracts/widget-loader.md)).

To run the full widget test suite:

```sh
cd frontend/widget
npm test
```

---

## 2. One-click local sanity check (US4)

This is the human-in-the-loop check that the production loader script embeds correctly into a third-party-style HTML page.

> ⚠ **Stop the docker widget container first.** The repo's [docker-compose.yml](../../docker-compose.yml) publishes the `widget` container on host port 5173. If that container is running, it shadows the local `npm run dev` server — Windows/WSL forwards localhost:5173 into the container's stale built copy, and your fresh edits silently never reach the browser. Symptom: `http://localhost:5173/host-test.html` returns a white page with "Loading…" top-left (the container falls back to its index.html because it has no host-test.html). Fix: `docker stop multi-tenant-ai-chatbot-widget-1` before `npm run dev`. Reverse with `docker start ...` later.

```sh
docker stop multi-tenant-ai-chatbot-widget-1   # if your stack is up
cd frontend/widget
npm run dev
```

Then open in a browser:

```
http://localhost:5173/host-test.html
```

What you should see:
- A blank page with a short heading and a chat-widget iframe pinned to the bottom-right corner.
- DevTools → Elements: exactly one `<iframe data-concierge-widget-id="w_demo" ...>` under `<body>`.
- DevTools → Network: one request for `widget.js` (the loader), then one request for `/?widget_id=w_demo` (the iframe runtime).
- DevTools → Console: no errors from the loader.

What you should **not** see:
- Multiple iframes (would indicate idempotency regression).
- A loader exception on the host page (would indicate fail-soft regression).
- A request to `localhost:5173` hardcoded anywhere in the loader source (would indicate FR-003 regression).

---

## 3. Build the production loader artifact

```sh
cd frontend/widget
npm run build
```

Inspect the output:

```sh
ls frontend/widget/dist/
```

You should see:
- `widget.js` — byte-identical to `frontend/widget/public/widget.js` (the Vite `public/` passthrough).
- `host-test.html` — also passthrough; safe to delete from a real deployment but harmless.
- `index.html`, `assets/...` — the iframe runtime.

To confirm the byte-identity invariant (C8):

```sh
git diff --no-index frontend/widget/public/widget.js frontend/widget/dist/widget.js
```

(No diff expected.)

---

## 4. Verify the ES2019 lock

Two checks:

(a) The build target is committed in source. Open [frontend/widget/vite.config.ts](../../frontend/widget/vite.config.ts) and confirm `build.target` is `'es2019'`.

(b) The loader source contains no post-ES2019 syntax tokens. The vitest case `loader source contains no post-ES2019 syntax tokens` enforces this, but you can also eyeball it:

```sh
grep -nE '(\?\?|\?\.|^\s*#|\\bawait\\s+)' frontend/widget/public/widget.js
```

(Nothing should match.)

---

## 5. Embed snippet for tenants (reference)

The production embed snippet a tenant will paste onto their site:

```html
<script
  src="https://<platform-host>/widget.js"
  data-widget-id="<the tenant's widget id>"
  data-backend-url="https://<platform-host>"
></script>
```

- `data-backend-url` is optional. If omitted, the loader uses the script's own origin (the platform-host above) as the backend, which is the common case.
- `data-widget-id` is required. If missing or empty, the loader fails soft (one `console.error`, no iframe).
- Multiple snippets with the same `data-widget-id` on one page are safe — the loader mounts at most one iframe per widget id.
- **Do not use `async`.** `document.currentScript` is `null` inside async classic scripts, which makes the loader fail-soft exit before mounting the iframe. `defer` is fine (currentScript is still set for deferred classic scripts); plain (no attribute) is also fine — the loader is small enough that blocking parse for its download is negligible.

---

## Troubleshooting

**Iframe doesn't appear locally.**
Check `http://localhost:5173/` opens directly first. If the iframe runtime fails to load on its own, the loader is fine — the iframe is.

**`console.error` says `data-widget-id is required` and you set it.**
You probably set `data-widget-id=""` (empty string). Empty after `trim()` counts as missing.

**Two iframes appear.**
Either two script tags with **different** widget ids (which is correct behavior, FR-013), or an idempotency regression. Check the `data-concierge-widget-id` attribute on each iframe.

**Loader build target seems to revert.**
`vite.config.ts` is a protected file in spirit (build config). Any PR that changes `build.target` away from `'es2019'` must justify the change in `DECISIONS.md`.
