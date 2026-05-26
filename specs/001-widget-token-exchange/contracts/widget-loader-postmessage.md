# Contract: Widget Loader ↔ Iframe `postMessage` Protocol

The host page loads `widget.js`, which inserts an `<iframe>` pointing at the widget bundle. The iframe runs on the platform's origin (e.g., `https://app.concierge.example`), not on the tenant's origin. That same-origin policy means the iframe's JavaScript cannot directly read `window.location.href` of the host page — it has to be told. This contract defines the two `postMessage` exchanges needed to (a) tell the iframe its true host origin, and (b) signal that the widget is ready to chat.

This is the contract between **[frontend/widget/public/widget.js](../../../frontend/widget/public/widget.js)** (runs on the host page, owner Amer) and **[frontend/widget/src/main.tsx](../../../frontend/widget/src/main.tsx)** (runs inside the iframe, owner Amer). Both files are Amer's, but the contract is documented here so the wire format survives later refactors.

## Message: `concierge.widget.host_origin` — loader → iframe

The host-page loader announces its origin to the iframe as soon as the iframe's `load` event fires.

### Sender (loader on host page)

```js
iframe.addEventListener("load", () => {
  iframe.contentWindow.postMessage(
    { type: "concierge.widget.host_origin", origin: window.location.origin },
    iframe.src  // restrict delivery to the iframe's own origin (platform origin)
  );
});
```

### Payload shape

```json
{
  "type": "concierge.widget.host_origin",
  "origin": "https://customer-site.example"
}
```

| Field | Type | Notes |
|---|---|---|
| `type` | const string | Distinguishes this message from any other messages the page might emit. |
| `origin` | string | `window.location.origin` of the host page. The iframe MUST use this as the `Origin` header value in the body of its `POST /widgets/token` request. (The browser will also send the actual `Origin` request header to the platform; the platform reads that, not this field — but the iframe needs this value to display in any user-facing failure message and to log internally.) |

### Receiver (iframe)

```ts
window.addEventListener("message", (event) => {
  // Defense: only accept the loader announcement from the parent window.
  if (event.source !== window.parent) return;
  if (typeof event.data !== "object" || event.data === null) return;
  if (event.data.type !== "concierge.widget.host_origin") return;
  // Now have the host origin. Kick off token exchange.
  bootstrapWithHostOrigin(event.data.origin);
});
```

### Security notes

- The loader uses `iframe.src` as the second `postMessage` argument, restricting delivery to the iframe's own origin. The browser will refuse to deliver the message to any other origin if the iframe is later moved.
- The iframe filters incoming messages by `event.source === window.parent`. A nested iframe or sibling frame on the same page cannot impersonate the loader.
- The host-origin field is **advisory** for the iframe's internal use. The platform's authoritative origin source is the HTTP `Origin` header on the `/widgets/token` request, which the browser controls. A malicious loader could send a fake `origin` in this message, but the platform would still reject the token request because the browser-supplied `Origin` header would not match the allowlist. This message exists for UX (showing the visitor the correct origin in error messages), not for security.

## Message: `concierge.widget.ready` — iframe → loader

The iframe announces it has successfully obtained a session credential and is ready to render the chat UI. The loader can use this to remove a loading skeleton on the host page if one exists (none does in Phase 1; this message is for Phase 2 onward).

### Sender (iframe)

```ts
window.parent.postMessage(
  { type: "concierge.widget.ready" },
  hostOrigin  // the value received in the earlier host_origin message
);
```

### Payload shape

```json
{
  "type": "concierge.widget.ready"
}
```

No data fields beyond `type`. The fact of readiness is the entire message.

### Receiver (loader)

```js
window.addEventListener("message", (event) => {
  if (event.source !== iframe.contentWindow) return;
  if (typeof event.data !== "object" || event.data === null) return;
  if (event.data.type === "concierge.widget.ready") {
    // optional: remove loading skeleton, fade in iframe, etc.
  }
});
```

## Failure signaling

If credential acquisition fails, the iframe MUST NOT send the `ready` message. Instead, it renders "Widget unavailable" inside itself (FR-013). The loader can detect the absence of readiness with a timeout (e.g., 3 s) and, optionally, hide the iframe on the host page — but that loader-side behavior is in scope for Phase 3 (loader hardening), not Phase 1.

## Versioning

The `type` field is the protocol version. If the protocol changes (e.g., the iframe needs to accept additional fields), bump the type string: `concierge.widget.host_origin.v2`. The iframe MUST continue to accept the older type for one release after the change, to allow the loader to be updated independently.

## Out of scope for this contract

- Chat-message protocol between iframe and any chat UI in the host page (irrelevant in Phase 1; the chat happens entirely inside the iframe). If a tenant later asks for the chat UI to be embedded directly in the host page (no iframe), a separate protocol document will define that.
- Resize / theme propagation messages (Phase 4 admin UI work).
- Cross-tab synchronization (out of scope — visitor sessions are per-tab by design).
