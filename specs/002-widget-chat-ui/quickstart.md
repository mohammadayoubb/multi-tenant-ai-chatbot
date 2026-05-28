# Quickstart: Verify Widget Chat UI Locally

End-to-end verification path for Amer after `/speckit-implement` finishes. Walks through (1) starting the stack, (2) mounting the widget on a local host page, (3) sending messages, (4) forcing a 401, (5) forcing a 500 + retry, (6) confirming no chat content lands in browser storage. Total time: < 5 minutes.

## Prerequisites

- Feature 001 (Widget Token Exchange) is implemented and its tests are green (already done).
- The `.venv` is set up with backend deps installed.
- `node_modules` are installed in `frontend/widget/` (`npm install` already ran).
- An `.env` file derived from `.env.example` plus the widget-specific entries documented in `app/services/widget_settings.py`.

## Step 1 — Bring up the stack

```powershell
docker compose up --build api
```

Wait for `Uvicorn running on http://0.0.0.0:8000`.

In a second terminal, start the widget dev server:

```powershell
cd frontend/widget
npm run dev
```

Wait for `Local: http://localhost:5173/`.

## Step 2 — Open the host test page

Serve a host page from a different port so its origin matches the allowlist:

```powershell
python -m http.server 5500 --directory frontend/widget/public
```

Open `http://localhost:5500/host-test.html` (created in feature 001 Phase 3 work; if absent, write a minimal page that embeds `widget.js`).

The widget mounts in the corner, runs the token exchange, and shows the chat input.

## Step 3 — Send a message (happy path)

Type "What are your hours?" and press Enter.

Expected:
- The user bubble appears immediately in the conversation pane.
- A loading indicator shows below it.
- Within a second or two, an assistant bubble appears with the reply.
- The pane has auto-scrolled to keep the latest message in view.
- Send button is re-enabled.

Open browser dev tools → Network. Inspect the `/chat` request:
- Method: `POST`
- Headers include `Authorization: Bearer eyJ…`
- Request body: `{"message":"What are your hours?","session_id":"<uuid>"}`
- Response: 200 with `{"answer":"…","route":"agent",…}`

## Step 4 — Force a 401 (terminal state)

In the dev tools console, deliberately corrupt the token to force the next `/chat` call to fail with 401:

```js
// Don't do this in production. This is a manual test affordance.
// Use the dev-tools "Sources" tab to break in api.ts and overwrite the _token variable.
```

Easier alternative: stop the API container (`docker compose stop api`), wait 60s for the token to actually expire, restart. Even easier: temporarily set `WIDGET_TOKEN_TTL_SECONDS=5` in `.env`, reload the host page, wait 6 seconds, then send a message.

Expected when the next `/chat` returns 401:
- The loading indicator is replaced by "Session expired, please reload" in the conversation pane.
- The input field is disabled (visually grayed; keyboard input has no effect).
- No automatic retry happens — no further `/chat` requests are visible in the Network tab.
- The visitor must reload the host page; that triggers a fresh `/widgets/token` exchange (feature 001).

## Step 5 — Force a 500 + retry (recoverable state)

With the host page open and the widget in `idle` state, stop the API container in another terminal:

```powershell
docker compose stop api
```

In the widget, send a message ("test 500").

Expected:
- The user bubble appears in the conversation pane.
- After the request fails, an error banner appears: "Couldn't reach the assistant. **Retry**."
- The banner does NOT show "500", "Internal Server Error", or any stack trace (FR-017).
- The user message "test 500" remains visible in the pane.

Restart the API:

```powershell
docker compose start api
```

Click **Retry** in the banner.

Expected:
- The retry sends the same message.
- The pane now shows exactly ONE "test 500" user bubble (not two — FR-016) followed by one assistant bubble.
- The error banner is gone.

## Step 6 — Browser storage check (privacy guarantee)

Open dev tools → Application:

| Storage | Expected after any chat session |
|---|---|
| **Cookies** for both `localhost:5500` and `localhost:8000` | empty of any chat content, token, or `session_id` value |
| **Local Storage** for `localhost:8000` (iframe origin) | empty |
| **Session Storage** | empty |
| **IndexedDB** | no Concierge database |

This is the visual confirmation of SC-005.

Reload the host page.

Expected:
- The conversation pane is empty (FR-019).
- The widget runs a fresh `/widgets/token` exchange — visible as a new `POST /widgets/token` in the Network tab.
- Sending "What are your hours?" again returns a fresh `session_id` (different from the previous session).

## Automated equivalent

Once `/speckit-implement` finishes, all of the above is covered by:

```powershell
cd frontend/widget
npm test
```

The new `src/__tests__/chat.test.tsx` exercises:
- Happy-path send → fetch invoked with correct `Authorization` header and body
- 401 response → `"expired"` state, input disabled, no retry attempted
- 500 response → error banner with retry → retry succeeds → exactly one user bubble + one assistant bubble
- Missing optional fields (`citations`, `ticket_id`, `used_tools`) → no crash, no error indicator
- Unknown `route` value → assistant message renders, no pill
- Empty/whitespace input → no fetch
- Rapid Enter presses → only one fetch (single-in-flight guard)
- Browser storage discipline (extending the feature-001 storage test)

## What "ready to merge" looks like

- `npm test` green in `frontend/widget/`.
- Manual Steps 3-6 above all work as described on the dev box.
- `git diff --name-only` lists only Amer-owned paths under `frontend/widget/`.
- No new backend code, no changes to `app/` whatsoever.
- PR description references this quickstart for the manual sign-off.
