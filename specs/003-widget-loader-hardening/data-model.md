# Data Model: Widget Loader Production Hardening

**Feature**: 003-widget-loader-hardening
**Date**: 2026-05-27

This feature has **no persistent data**. Nothing is stored on disk, in a database, in `localStorage`, in `sessionStorage`, or in `document.cookie` (FR-014). The "entities" below are DOM-level structures the loader creates or reads at runtime. They are documented here to make the loader's runtime contract auditable.

---

## Entity: LoaderScriptTag

The `<script>` element on the tenant's host page that loaded `widget.js`. The loader reads its own script element via `document.currentScript`.

| Field | Type | Source | Validation | Notes |
|-------|------|--------|------------|-------|
| `src` | string (URL) | Set by the tenant | Must be a parseable URL. If `new URL(src).origin` throws, the loader fails soft. | Used to derive the default backend origin when `data-backend-url` is absent. |
| `data-widget-id` | string | Set by the tenant | Required, non-empty. Missing or empty → single `console.error`, no mount. | Opaque to the loader; passed through to the iframe URL query string. |
| `data-backend-url` | string \| undefined | Set by the tenant (optional) | When present and non-empty, used as the iframe's backend origin. When absent or empty, the loader falls back to the script's own origin. | The loader does not validate the URL syntax — an invalid value becomes a network-layer error inside the iframe (per spec edge case). |

**Lifecycle**: read once at IIFE entry. Never mutated by the loader.

---

## Entity: WidgetIframe

The DOM element the loader creates and appends to `document.body`.

| Field | Type | Value | Source | Notes |
|-------|------|-------|--------|-------|
| `tagName` | string | `IFRAME` | Constant | — |
| `src` | string | `<backendUrl>/?widget_id=<encodeURIComponent(widgetId)>` | Computed from `LoaderScriptTag` | The query-string encoding is the contract with the iframe runtime (feature 002). |
| `data-concierge-widget-id` | string | The `widgetId` value read from `LoaderScriptTag.data-widget-id` | Mirror of input | Idempotency marker. The loader queries for this attribute to detect a prior mount. |
| `title` | string | `"Concierge chat widget"` | Constant | Accessibility (FR-006). |
| `sandbox` | string | `"allow-scripts allow-same-origin allow-forms"` | Constant | Three flags exactly (FR-004, R6). |
| `referrerpolicy` | string | `"no-referrer-when-downgrade"` | Constant | FR-005. |
| `style.position` | string | `"fixed"` | Constant | Pins to viewport corner. |
| `style.right` | string | `"24px"` | Constant | Visual placement (carried from feature 001). |
| `style.bottom` | string | `"24px"` | Constant | Visual placement. |
| `style.width` | string | `"360px"` | Constant | Visual placement. |
| `style.height` | string | `"520px"` | Constant | Visual placement. |
| `style.border` | string | `"0"` | Constant | No browser default border. |
| `style.borderRadius` | string | `"0.6rem"` | Constant | — |
| `style.boxShadow` | string | `"0 10px 30px rgba(0,0,0,0.15)"` | Constant | — |

**Lifecycle**:
1. The loader checks for an existing `iframe[data-concierge-widget-id="<widgetId>"]`. If found, the loader returns (idempotent no-op, FR-007).
2. Otherwise the loader creates the element, sets every field above in one synchronous tick, and appends to `document.body`.
3. On the iframe's `load` event, the loader posts the host-page origin to the iframe via `postMessage` (contract carried forward from feature 001; see [specs/001-widget-token-exchange/contracts/widget-loader-postmessage.md](../001-widget-token-exchange/contracts/widget-loader-postmessage.md)).

---

## Entity: PostedHostOrigin

The single `postMessage` payload the loader sends to the iframe after mount. **Unchanged** from feature 001 — listed here only to make the full contract explicit.

| Field | Type | Value | Notes |
|-------|------|-------|-------|
| `type` | string | `"concierge.widget.host_origin"` | Constant; the iframe filters incoming messages on this discriminator. |
| `origin` | string | `window.location.origin` of the host page | The iframe uses this only for UX display; the platform authoritatively reads `Origin` from the HTTP request header on `/widgets/token` (server-side trust boundary). |

**Lifecycle**: posted once per iframe, in the iframe's `load` event handler.

---

## Validation rules summary

- `data-widget-id` present and non-empty after `trim()` — required (FR-008).
- `document.currentScript` not null — required (FR-009 / R7).
- All other inputs are pass-through; the loader does not validate URL syntax or sandbox flag spelling (the spec edge case explicitly allows malformed backend URLs to become iframe-side network failures).

## State transitions

```text
loader IIFE start
  ├── try:
  │     ├── read currentScript           → if null, fail-soft exit
  │     ├── read data-widget-id          → if missing/empty, console.error + exit
  │     ├── check iframe[data-concierge-widget-id="<id>"] in DOM
  │     │      └── if present, exit silently (idempotent no-op)
  │     ├── compute backendUrl           = data-backend-url ?? origin(src)
  │     ├── if (!document.body) → DOMContentLoaded → mount
  │     │   else                          → mount
  │     └── mount:
  │            ├── create iframe with all attributes/styles
  │            ├── attach load handler   (postMessage host_origin)
  │            └── document.body.appendChild(iframe)
  └── catch (any): console.error once, exit. No re-throw.
```
