# Contract: Widget Loader DOM Behavior

**Feature**: 003-widget-loader-hardening
**File under contract**: [frontend/widget/public/widget.js](../../../frontend/widget/public/widget.js)
**Owner**: Amer
**Consumers**: tenant host pages (production), the host-test page (local dev), the iframe runtime (`frontend/widget/src/main.tsx`, feature 002).

This contract is the testable surface of the loader. Each clause maps to a vitest assertion in `frontend/widget/src/__tests__/loader.test.ts`.

---

## C1. Input attributes on the loader script tag

The loader reads, and ONLY reads, the following attributes from `document.currentScript`:

| Attribute | Required? | Type | Used for |
|-----------|-----------|------|----------|
| `src`           | Yes (set by the browser when the script tag has a `src`) | URL | Compute the default backend origin via `new URL(src).origin`. |
| `data-widget-id`  | Yes | string | Identifies the widget; passed to the iframe URL; used as the idempotency key. |
| `data-backend-url` | No | string | When present and non-empty, overrides the backend origin. |

The loader MUST NOT read any other attribute from the script tag.
The loader MUST NOT read or write any other DOM element on the host page besides `document.body` (and only to `appendChild` the iframe it creates).

## C2. Output: exactly one iframe per widget id per page

After the loader runs to completion successfully:

- Exactly one iframe element exists in `document.body` with `data-concierge-widget-id="<widgetId>"`.
- The iframe's `src` equals `<backendUrl>/?widget_id=<encodeURIComponent(widgetId)>`.
- `backendUrl` equals the value of `data-backend-url` when present and non-empty; otherwise it equals `new URL(currentScript.src).origin`.

If a second `<script>` element with the same `data-widget-id` executes the loader again, the DOM state MUST be unchanged. No new iframe MUST be created.

If two `<script>` elements with **different** `data-widget-id` values execute the loader, **two** iframes MUST exist, each with the appropriate `data-concierge-widget-id`.

## C3. Iframe attributes (hardened)

The created iframe MUST carry exactly these attribute values:

| Attribute | Value |
|-----------|-------|
| `title` | `Concierge chat widget` |
| `sandbox` | `allow-scripts allow-same-origin allow-forms` |
| `referrerpolicy` | `no-referrer-when-downgrade` |
| `data-concierge-widget-id` | `<widgetId>` |

The `sandbox` attribute MUST contain those three tokens in any order and MUST NOT contain any other `allow-*` flag.

## C4. Fail-soft on misconfiguration

If `document.currentScript` is `null`:
- The loader logs nothing and creates no iframe. No exception propagates. (Rationale: cannot tell what to log about without knowing the script tag.)

If `data-widget-id` is missing, empty after `trim()`, or unreadable:
- The loader emits **exactly one** call to `console.error(...)`.
- The loader creates no iframe.
- No exception propagates to the host page.

If any unexpected exception is thrown during loader execution (e.g. DOM API misuse, host-page CSP blocks an action):
- The exception is caught by the loader's top-level `try/catch`.
- The loader emits **exactly one** `console.error(...)`.
- No exception propagates to the host page.

## C5. Late-mount safety

If `document.body` does not exist when the loader runs:
- The loader MUST register a `DOMContentLoaded` listener that performs the mount, then return immediately.
- The loader MUST NOT throw because of a missing body.
- After `DOMContentLoaded` fires, all the post-mount invariants (C2, C3, C6) MUST hold.

## C6. Iframe load handshake (carried over from feature 001)

After the iframe fires its `load` event, the loader MUST `postMessage` the following payload to the iframe, targeted at the iframe's own origin:

```json
{
  "type": "concierge.widget.host_origin",
  "origin": "<window.location.origin of the host page>"
}
```

The iframe uses this payload for display only. **Tenant identity is never derived from this value.** The platform reads the HTTP `Origin` header server-side on `/widgets/token` (the authoritative trust boundary).

## C7. Storage abstinence

The loader MUST NOT access:
- `localStorage`, `sessionStorage`
- `document.cookie`
- IndexedDB, Cache API, any storage API

Verifiable by static inspection (`grep`) and by a vitest case that spies on `localStorage.setItem`, `sessionStorage.setItem`, and `document.cookie`'s setter.

## C8. Build target

The shipped artifact at `dist/widget.js` MUST be byte-identical to `public/widget.js` (Vite `public/` passthrough). The source MUST NOT contain any of the following ES2020+ syntax tokens:

- `?.`  (optional chaining)
- `??`  (nullish coalescing)
- `#`-prefixed private class fields
- top-level `await`

The loader MUST be a single file with no `import` statements.

---

## Contract test mapping

| Contract clause | Test name (in `loader.test.ts`) |
|-----------------|-------------------------------|
| C1 attribute reads | `reads data-backend-url`, `defaults backend to script origin` |
| C2 single iframe per widget id | `mounts exactly one iframe`, `is idempotent for same widget id`, `mounts two iframes for two different widget ids` |
| C3 iframe attributes | `applies hardened iframe attributes` |
| C4 fail-soft | `logs one console.error and does not throw when data-widget-id is missing`, `logs one console.error and does not throw when data-widget-id is empty`, `does not throw when currentScript is null` |
| C5 late-mount | `defers mount when document.body is not yet present` |
| C6 postMessage | covered by feature 001 tests — referenced, not duplicated |
| C7 no storage | `does not touch localStorage, sessionStorage, or document.cookie` |
| C8 syntax baseline | `loader source contains no post-ES2019 syntax tokens` |
