# Phase 0 Research: Widget Loader Production Hardening

**Feature**: 003-widget-loader-hardening
**Date**: 2026-05-27
**Status**: Complete — no NEEDS CLARIFICATION markers remain in [spec.md](./spec.md).

This document records the design decisions whose alternatives were considered and rejected during planning. Each section follows the **Decision / Rationale / Alternatives considered** format from the plan template.

---

## R1. Where does the loader live in the repo, and how is it built?

**Decision**: Keep [frontend/widget/public/widget.js](../../frontend/widget/public/widget.js) hand-authored at ES2019 syntax and let Vite's `public/` mechanism copy it verbatim to `dist/widget.js`. Do not route the loader through the Vite bundler.

**Rationale**:
- The loader is one file with zero npm dependencies. Bundling it would add JS-runtime helpers (e.g. `__defProp`, IIFE wrappers, source-map comments) without any gain. Hand-authored is smaller, more auditable, and trivially "single-file" (FR-012).
- Hand-authored at ES2019 syntax means a human-readable diff in PRs touches the actual shipping artifact, not a generated one. Reviewers who own widget security (Amer) can read the diff directly. Bundled output forces reviewers to read a generated artifact or trust the build.
- `vite build` already copies `public/*` to `dist/*` unchanged. The output path stays predictable for the platform's static-serving route.

**Alternatives considered**:
- *Build the loader as a Vite library entry with `format: 'iife'` and `target: 'es2019'`.* Rejected: adds build complexity (a separate `lib.entry`, separate output name) for a file that has no imports. The output would be larger than the hand-written source because of bundler boilerplate.
- *Author the loader in TypeScript and emit JS.* Rejected: introduces a type-check step for ~80 lines of DOM glue that has no business types. The JS we'd write is already type-trivial.

---

## R2. How is the ES2019 target locked in?

**Decision**: Add [frontend/widget/vite.config.ts](../../frontend/widget/vite.config.ts) with `build.target: 'es2019'`. The loader itself stays plain JS at ES2019 syntax; the React iframe app (which *is* bundled) gets the ES2019 target.

**Rationale**:
- `build.target` governs the bundled iframe app. Pinning it locks the iframe runtime to the same baseline the loader assumes, so a tenant's old browser doesn't load the loader successfully only to fail when the iframe tries to run an ES2020 construct.
- The loader itself does not pass through any bundler, so we cannot rely on a transpile step to enforce its syntax. Instead, [research item R3](#r3-how-do-we-prove-the-loader-stays-at-es2019-syntax) describes how a static-check test catches forbidden syntax.

**Alternatives considered**:
- *Use a `browserslist` config in package.json.* Rejected: Vite reads `build.target` directly; adding `browserslist` introduces a second source of truth.
- *Use `esbuild.target` directly.* Rejected: `build.target` is the public-facing Vite option and resolves to esbuild under the hood. Same effect, less coupling to Vite internals.

---

## R3. How do we prove the loader stays at ES2019 syntax?

**Decision**: A vitest case in `frontend/widget/src/__tests__/loader.test.ts` reads `public/widget.js` from disk and parses it with the `Function` constructor inside a jsdom global. If the parser accepts the file under default settings (which target current Node's ES baseline) we know it's syntactically valid. For the legacy guarantee, the same test asserts the file does **not** contain a small set of forbidden tokens that are syntactic markers for post-2019 features: `??`, `?.`, `#`-prefixed class fields, and `\bawait\s+` at top level. This catches the realistic regressions a developer could introduce by hand without requiring a full parser-per-engine simulation.

**Rationale**:
- Realistic threat model: a developer edits the loader and accidentally uses `?.` (optional chaining, ES2020). A token scan catches the common cases.
- A full multi-target parse is overkill for an 80-LOC file. The forbidden-token list is a checklist that mirrors what the developer is most likely to type by accident.
- The check lives next to the behavior tests, so it runs in the same CI step (smoke test gate).

**Alternatives considered**:
- *Run the loader through a real ES2019 parser (e.g. acorn with `ecmaVersion: 2019`).* Rejected: adds a parser dependency for marginal gain; acorn's accepted grammar can drift from real browser support anyway.
- *Trust the developer to remember.* Rejected: SC-004 requires the property to be verifiable, not aspirational.

---

## R4. How does the host-test page reach the iframe runtime locally?

**Decision**: [frontend/widget/public/host-test.html](../../frontend/widget/public/host-test.html) embeds the loader with `<script src="/widget.js" data-widget-id="w_demo" data-backend-url="http://localhost:5173"></script>`. The developer runs `npm run dev` from `frontend/widget/`; Vite serves both the host page (at `/host-test.html`) and the iframe runtime (at `/`) on `:5173`. The loader mounts an iframe pointing at `http://localhost:5173/?widget_id=w_demo`, which is the same Vite dev server, so React loads and the loader contract is exercised end-to-end.

**Rationale**:
- One process, one port, one command — matches FR-010 and SC-005 ("without writing additional HTML").
- The `data-backend-url` is set explicitly to `http://localhost:5173` so the test page also exercises the **explicit override** code path (FR-001), not just the default-to-same-origin path. The default path is covered by the vitest cases.
- Using the literal `w_demo` widget id keeps the test page self-documenting; the platform's eventual response to that id is out of scope (this feature is loader-only — the iframe-side behavior is governed by feature 002).

**Alternatives considered**:
- *Serve the host page from a separate origin to better simulate a tenant site.* Rejected for now: would require running two HTTP servers locally. The same-origin local test still exercises every loader code path (attribute reads, iframe attribute application, idempotency, fail-soft); cross-origin behavior is browser-enforced and not something the loader code itself decides.
- *Use a static fixture in `src/__tests__/fixtures/`.* Rejected: a fixture is for automated tests, not for the human one-click sanity check this story (US4) asks for.

---

## R5. How is idempotency detected?

**Decision**: The loader scopes its idempotency check to a CSS selector on a custom data attribute the loader itself sets on the iframe: `iframe[data-concierge-widget-id="<widgetId>"]`. If `document.querySelector(...)` returns an existing element, the loader returns immediately. The attribute is set as part of the iframe creation in the same synchronous tick, so a second script execution in the same task queue still sees the first iframe.

**Rationale**:
- A data attribute is reliable across SPA route changes (the DOM persists), survives stylesheet changes, and is invisible to the host page's own CSS.
- Scoping by widget id (not just "any iframe") satisfies FR-013: two different widget ids on the same page each mount their own iframe.
- The attribute name `data-concierge-widget-id` is namespaced with the product name to avoid colliding with a tenant's own data attributes.

**Alternatives considered**:
- *Use a module-level `Set` of seen widget ids.* Rejected: the loader is an IIFE in `<script>` form, not a module — each `<script>` tag execution runs in its own closure. A DOM marker is the only state that survives across executions.
- *Use `window.__concierge_widgets__`.* Rejected: pollutes a host-page global, which conflicts with the principle that the loader leaves no visible trace on the host page beyond the iframe itself.

---

## R6. What sandbox flags are required, and why these specifically?

**Decision**: `sandbox="allow-scripts allow-same-origin allow-forms"`. No other flags.

**Rationale**:
- `allow-scripts`: required for the React iframe app to execute. Without it nothing runs.
- `allow-same-origin`: required so the iframe (which loads from the platform origin) can make credentialed `fetch` calls back to the platform origin and read its own cookies/storage for the widget token (per feature 001's auth flow). Note: this allows same-origin behavior **relative to the iframe's own origin (the platform)**, not the host page's origin. The host page remains cross-origin to the iframe.
- `allow-forms`: required so the chat input's `<form>` element can submit normally (defense against accidental enter-key swallowing); also lets us keep the React form semantics simple.
- **Not included**: `allow-popups`, `allow-top-navigation`, `allow-modals`, `allow-pointer-lock`, `allow-storage-access-by-user-activation`, `allow-downloads`. The widget has no legitimate reason to navigate the top frame, open popups, lock the pointer, or download files.

**Alternatives considered**:
- *Omit `allow-same-origin`.* Rejected: would break the iframe's ability to call the platform API with its own credentials — the entire token exchange would fail. The sandbox must be permissive *for the iframe's relationship to the platform origin* while remaining a hard wall to the host page.
- *Add `allow-top-navigation`.* Rejected: gives the iframe (and any script that can inject into the iframe runtime) the ability to redirect the host page. High blast radius, no use case.

---

## R7. What does "fail-soft" mean operationally?

**Decision**: On any input the loader cannot process — missing `document.currentScript`, missing/empty `data-widget-id`, attribute read throws — the loader (a) emits exactly one `console.error` describing the problem, (b) returns from the IIFE without creating an iframe, and (c) does so without re-throwing. The loader is wrapped in a single top-level `try/catch` (no per-line catches) so any unexpected exception is contained.

**Rationale**:
- "Exactly one" `console.error` keeps tenant logs uncluttered; FR-008 phrases this as a hard requirement testable in jsdom.
- A single top-level catch is preferable to defensive `if`-checks at every step because (1) it covers unexpected exceptions, (2) it keeps the code short enough to audit, and (3) it makes the failure shape uniform (one log line, no iframe).
- The browser still surfaces CSP violations (e.g. `frame-ancestors` denial) on its own — these are not the loader's responsibility to silence (edge case in spec).

**Alternatives considered**:
- *Per-step defensive checks with bespoke error messages.* Rejected: bloats the loader, increases the chance of a missed case, and violates Principle VII (Clean & Simple Code — "do not add error handling for cases that cannot happen").
- *`window.addEventListener('error', ...)` to swallow errors.* Rejected: would suppress unrelated host-page errors. Scope must stay narrow.

---

## R8. Should the loader wait for `document.body`?

**Decision**: Yes — but with a check, not a polyfill. If `document.body` is missing at the time the loader runs (script in `<head>` without `defer`), the loader registers a `DOMContentLoaded` listener and mounts the iframe from there. The check is cheap (`if (!document.body) { document.addEventListener('DOMContentLoaded', mount); return; }`).

**Rationale**:
- Edge case in spec: "The host page loads the script before `document.body` exists." Without this guard the `document.body.appendChild(iframe)` call throws, which violates FR-009.
- A single `DOMContentLoaded` listener is allowed (FR-009 only forbids exceptions propagating to the host page; it does not forbid `addEventListener`).
- The listener runs once and is not re-registered on duplicate script loads because the idempotency check (R5) executes inside the mount function — both paths converge.

**Alternatives considered**:
- *Document the requirement that tenants must place the script with `defer` or at the bottom of `<body>`.* Rejected: real tenants will paste the snippet wherever a tag manager puts it. The loader has to be robust to that.
- *MutationObserver on `document.documentElement`.* Rejected: heavyweight, observable side effects, and unnecessary given `DOMContentLoaded` exists.

---

## R9. Test environment for the loader

**Decision**: jsdom via vitest. The loader source is read with Node's `fs.readFileSync`, evaluated inside a freshly-constructed jsdom document via a dynamically-created `<script>` element whose `textContent` is the source. The `document.currentScript` reference is patched via `Object.defineProperty` on the document before evaluation so the loader can find its own script. Each test case constructs a fresh DOM.

**Rationale**:
- The loader's contract is entirely a DOM contract (read attributes, create iframe, set attributes, append to body, log to console). jsdom covers all four.
- Reading the source at runtime guarantees the test exercises the **actual shipping file**, not a copy. A regression in `public/widget.js` cannot pass the test by mistake.
- A real browser test (Playwright) would be more authoritative but introduces a new tool to the repo. The host-test.html (R4) is the human-in-the-loop browser check; the automated layer stays on jsdom.

**Alternatives considered**:
- *Playwright against a Vite dev server.* Rejected as a follow-up for Phase 10 (CI/CD) — out of scope here.
- *Mock the DOM by hand.* Rejected: jsdom is already a dev dependency and is exactly what it's built for.
