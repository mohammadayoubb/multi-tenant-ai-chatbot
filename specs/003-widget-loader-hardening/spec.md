# Feature Specification: Widget Loader Production Hardening

**Feature Branch**: `003-widget-loader-hardening`
**Created**: 2026-05-27
**Status**: Draft
**Input**: User description: "Production-harden the embeddable widget loader. Make the loader script safe to drop into arbitrary tenant pages: configurable backend URL, hardened iframe attributes, idempotent mount, fail-soft on misconfiguration. Add a host test page for local end-to-end sanity-check, and pin the production build to ES2019 single-file output. Backend changes and theme customization are out of scope."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tenant embeds the loader on a production website (Priority: P1)

A tenant pastes the `<script src="…/widget.js" data-widget-id="…" data-backend-url="…"></script>` snippet into their site's HTML. The chat widget mounts in an isolated iframe in the corner of the page, points at the correct backend, and does not interfere with the host page's behavior or appearance.

**Why this priority**: This is the only way Concierge reaches end visitors. Without a loader that works on a real third-party site (not just `localhost`), no tenant can ship the product, regardless of how good the backend is.

**Independent Test**: Open a static HTML page that loads the script with `data-widget-id` and `data-backend-url` pointing at a running backend. Confirm the widget iframe appears, talks to the configured backend, and the host page's console is free of errors thrown by the loader.

**Acceptance Scenarios**:

1. **Given** a host page with the loader script tag carrying `data-widget-id="w_demo"` and `data-backend-url="https://api.example.com"`, **When** the page loads, **Then** exactly one iframe is mounted whose source URL points at `https://api.example.com` and carries the configured widget id.
2. **Given** a host page with the loader script tag carrying `data-widget-id="w_demo"` and no `data-backend-url`, **When** the page loads, **Then** the iframe is mounted against the same origin that served the loader script.
3. **Given** the loader is included on a host page, **When** the page finishes loading, **Then** the iframe carries a sandbox restriction that limits its capabilities, a referrer policy that does not leak full URLs to less-secure origins, and a human-readable accessible name.

---

### User Story 2 - Loader is safe to include twice on the same page (Priority: P2)

A tenant's CMS template or A/B testing tool accidentally injects the loader twice with the same widget id (a common production accident with tag managers and SPA route changes). The loader must mount the widget exactly once.

**Why this priority**: Duplicate mounts produce two overlapping chat panels, duplicate sessions, duplicate token-exchange calls (which inflates cost and rate-limit usage), and visitor confusion. This is high-impact but only triggered by host-page configuration mistakes, not by every user.

**Independent Test**: On a host page, include the same loader script tag twice with identical `data-widget-id`. Inspect the DOM and confirm exactly one widget iframe exists.

**Acceptance Scenarios**:

1. **Given** a host page where the loader script with `data-widget-id="w_demo"` has already mounted an iframe, **When** the loader runs a second time with the same widget id, **Then** no additional iframe is created and no error is thrown.
2. **Given** a host page that loads the script once, **When** the page is dynamically re-rendered such that the loader re-executes, **Then** the existing widget iframe is preserved (not destroyed and remounted).

---

### User Story 3 - Loader fails soft when misconfigured (Priority: P2)

A tenant pastes the loader snippet but omits `data-widget-id`, or pastes a snippet with an empty id, or includes the script in a context where the script tag cannot be located. The host page must keep functioning.

**Why this priority**: The loader runs on third-party sites we do not control. A thrown exception from our script would surface as a JavaScript error on the tenant's site, potentially breaking their analytics, their checkout flow, or their own scripts. Failure must be silent and observable only in the console.

**Independent Test**: Load a host page with a loader tag that has no `data-widget-id`. Confirm (a) no iframe is created, (b) exactly one `console.error` is emitted, and (c) `window.onerror` is not invoked by the loader.

**Acceptance Scenarios**:

1. **Given** a loader script tag with no `data-widget-id` attribute, **When** the script executes, **Then** the loader logs a single error message to the console and returns without mounting an iframe or throwing.
2. **Given** a loader script tag with `data-widget-id=""` (empty string), **When** the script executes, **Then** the loader behaves the same as the missing-attribute case (one console error, no iframe, no throw).
3. **Given** the loader cannot determine its own script element, **When** the script executes, **Then** the loader aborts silently without throwing.

---

### User Story 4 - Developer sanity-checks the loader on localhost (Priority: P3)

A developer working on the widget or its backend wants to confirm end-to-end that the production loader script, served from the production build output, embeds correctly into a third-party-style HTML page. They open a checked-in host test page in their browser and see the widget mount.

**Why this priority**: Improves developer feedback loop and catches loader regressions before they reach a tenant site, but is not part of the runtime product surface. Without it the team can still ship, just more slowly and with less confidence.

**Independent Test**: After running the production build, open the host test page from the repo in a browser pointed at a running backend. Confirm the widget appears.

**Acceptance Scenarios**:

1. **Given** the production widget build has been produced, **When** a developer opens the host test page in a browser, **Then** the page loads the loader via a `<script>` tag with a sample `data-widget-id` and the widget iframe mounts.
2. **Given** the host test page is checked into the repo, **When** another developer pulls the branch, **Then** they can reproduce the local sanity check without writing additional HTML.

---

### User Story 5 - Loader runs on legacy browsers tenants still support (Priority: P3)

A tenant's customer base includes visitors on older browsers (typical for B2C sites with long-tail device support). The compiled loader script must parse and execute on those browsers without syntax errors.

**Why this priority**: A syntax error on an old browser breaks the loader for that visitor segment silently. The fix is a build-time decision, so it must be locked in before any tenant ships.

**Independent Test**: Inspect the built loader artifact and confirm it does not emit syntax constructs newer than the agreed language baseline. Optionally load it in a browser that only supports that baseline.

**Acceptance Scenarios**:

1. **Given** the production build of the widget loader, **When** the artifact is parsed by a JavaScript engine that supports only the agreed legacy baseline, **Then** parsing succeeds and the loader executes without `SyntaxError`.
2. **Given** the production build, **When** the build output is inspected, **Then** the loader ships as a single self-contained file with no external runtime imports required at load time.

---

### Edge Cases

- The host page loads the script before `document.body` exists (e.g., script in `<head>` without `defer`). The loader must either wait for the body or abort fail-soft; it must not throw.
- The host page's Content Security Policy forbids inline styles or framed origins. The loader's failure to mount must remain silent on the host page (any browser-level CSP violation is the browser's output, not the loader's).
- The script tag's `src` is a protocol-relative URL or a relative path. The same-origin default for the backend URL must still resolve to an absolute origin without throwing.
- The tenant supplies a `data-backend-url` value that is not a valid URL. The loader still attempts to use it as-is and must not throw before reaching the network; any error becomes a network-layer failure inside the iframe.
- Two loader script tags exist on the same page with *different* `data-widget-id` values. Both widgets should mount (idempotency is scoped per widget id, not per page).
- The loader runs inside an iframe itself (a tenant tests by embedding their own site in a preview tool). The loader must not assume top-level browsing context.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The loader MUST read the backend base URL from the `data-backend-url` attribute on its own script tag when the attribute is present and non-empty.
- **FR-002**: The loader MUST default the backend base URL to the origin of the script tag's own `src` when `data-backend-url` is absent or empty.
- **FR-003**: The loader MUST NOT contain any hardcoded backend host, port, or origin.
- **FR-004**: The loader MUST mount the widget inside an iframe whose sandbox restrictions limit it to scripts, same-origin requests to the platform, and form submission, and no other capabilities.
- **FR-005**: The loader MUST set the iframe's referrer policy such that the full host-page URL is not sent to less-secure (HTTP) destinations.
- **FR-006**: The loader MUST set a human-readable accessible title on the iframe so assistive technology announces it as a chat widget.
- **FR-007**: The loader MUST mount at most one iframe per `data-widget-id` per page. A second invocation with the same widget id MUST be a silent no-op.
- **FR-008**: If `data-widget-id` is missing, empty, or unreadable, the loader MUST log exactly one error to the browser console and return without mounting an iframe.
- **FR-009**: The loader MUST NOT throw any exception that propagates to the host page's global error handler under any input condition, including missing script element, missing attributes, and malformed attribute values.
- **FR-010**: A host test page MUST be checked into the repository that embeds the loader via a `<script>` tag with a known sample `data-widget-id`, suitable for opening directly in a browser against a locally running backend.
- **FR-011**: The production build of the loader MUST target a JavaScript language baseline compatible with browsers released no later than 2019, so that parse-time syntax errors do not occur on long-tail tenant audiences.
- **FR-012**: The production build of the loader MUST be a single self-contained file with no runtime-imported chunks, so a tenant only needs one `<script>` tag.
- **FR-013**: Idempotency MUST be scoped per widget id: two loader tags with different widget ids on the same page MUST each mount their own iframe.
- **FR-014**: The loader MUST NOT access the host page's `localStorage`, `sessionStorage`, or `document.cookie` (consistent with the widget auth rules — tokens stay inside the iframe). "Access" covers both reads and writes.

### Key Entities *(include if feature involves data)*

- **Loader script tag**: The `<script>` element on the tenant's host page. Carries the configuration attributes (`data-widget-id`, `data-backend-url`) that the loader reads. Its `src` origin is the implicit backend default.
- **Widget iframe**: The DOM element the loader creates. Carries a data attribute identifying which widget id it belongs to, so the loader can detect duplicates. Its `src` points at the backend origin with the widget id in the query string.
- **Host test page**: A checked-in HTML file that simulates a tenant's site for local end-to-end sanity checks. Not shipped to tenants.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tenant can take the production loader snippet, paste it into any HTML page, and see the widget mount against the backend they configured — with zero code edits to the loader.
- **SC-002**: When the loader is included twice with the same widget id on the same page, exactly one widget iframe exists in the DOM.
- **SC-003**: When the loader is included with a missing or empty widget id, exactly zero widget iframes are created, exactly one console error is emitted, and no exception reaches the host page's global error handler.
- **SC-004**: The production loader artifact ships as a single file and parses successfully on browsers conforming to the 2019 JavaScript language baseline.
- **SC-005**: A new developer pulling the branch can perform an end-to-end local sanity check (host page → loader → widget mounted → backend reached) without writing any HTML of their own.
- **SC-006**: The loader contains no hardcoded backend hostname or port — verifiable by static inspection of the source and the built artifact.

## Assumptions

- The widget runtime that the iframe loads (the React app served by the backend) is unchanged by this feature. Only the loader script, the host test page, and the build config are affected.
- The backend already serves the widget runtime at the path the loader uses (established in features 001 and 002). No backend route changes are needed.
- "ES2019 language baseline" is interpreted as the agreed cutoff for tenant audiences; if a specific tenant later requires older support, that becomes a follow-up.
- Theme customization (colors, position, size, copy) is explicitly deferred to a later phase. The loader continues to use fixed, sensible defaults for now.
- The loader is delivered to tenants by referencing it directly from the platform's origin (the same origin that serves the backend in default deployments). Tenants do not self-host the loader file.
- The host test page is for developer use only and is not part of any deployed artifact.
- The loader does not normalize the `data-backend-url` value (e.g., does not strip a trailing slash). A tenant who supplies `https://api.example.com/` will produce an iframe `src` containing `//?widget_id=…`. This is accepted by every conformant web server and is preferable to defensive normalization, which would add code without removing any failure mode (per the Clean & Simple Code principle).
