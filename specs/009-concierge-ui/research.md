# Phase 0 — Research: Concierge UI

Resolves every `NEEDS CLARIFICATION` item from [plan.md](plan.md) and records the technical decisions that anchor Phase 1 design.

---

## R1 — Streamlit accessibility & responsiveness ceiling

**Decision:** Accept the Streamlit UX ceiling for admin surfaces. Target ≥1024 px viewports (laptop / tablet-landscape) and rely on Streamlit's default WCAG-AA-conformant defaults plus our own label/contrast discipline. No Next.js or alternate framework in this plan.

**Rationale:** The admin surface is already partially shipped in Streamlit (12 page modules, two flows live). Switching frameworks would re-derive the auth/router/page conventions and triple the work without changing the demo story. The spec out-of-scopes mobile admin (SC-006 covers ≥1280 px, ≥1024 px tablet-landscape only). Tenant admins do their work on a laptop, not a phone.

**Alternatives considered:**
- Migrate to Next.js — rejected: 3–4× LOC for no demo value; introduces a second auth flow (NextAuth vs. our JWT) that complicates Principle IV.
- Use a Streamlit components extension for richer UI — rejected: each component adds a third-party JS dependency, weakening Principle V (lean serving) and complicating the deploy.

---

## R2 — Focus trap implementation: build vs. buy

**Decision:** Build a ~30-line `FocusTrap.tsx` helper. No `focus-trap-react` or similar dependency.

**Rationale:** The widget panel has exactly one focusable region. A focus trap with two-element wraparound (find first / last focusable child, send `Tab` past last to first and `Shift+Tab` past first to last) is a small, well-understood pattern. Importing `focus-trap-react` (~3 KB gzipped + transitive deps) is a constitution-V concern (bundle bloat) for code we can audit ourselves.

**Alternatives considered:**
- `focus-trap-react` — rejected on bundle-size and audit-surface grounds.
- Use `inert` attribute on siblings — rejected: poor support in older Safari; we cannot rely on it given the widget is embedded on arbitrary host pages.

**Implementation notes:** Helper exposes `<FocusTrap initialFocusRef onEscape>`. On mount, snapshots active element; on unmount, restores it. ESC handler bound at the trap level (not document level) to avoid stealing host-page ESCs.

---

## R3 — Streamlit AppTest patterns for placeholder fallback pages

**Decision:** Each placeholder-fallback page (tenant_page, cms_page, leads_page, usage_page, plus new agent_settings, guardrails, escalations, tenants, invites, audit, settings) gets two AppTest cases: (a) backend returns real shape → page renders rows + no badge; (b) backend returns 404/501 → page renders `_SAMPLE_*` rows + visible `(placeholder)` badge.

**Rationale:** The existing tenant/cms/leads/usage pages already implement the pattern with `_SAMPLE_*` dicts; the AppTest harness is already used. Extending the pattern keeps the demo unbreakable during Phase 2A development and after merge serves as graceful degradation if any one endpoint is down.

**Mock transport:** `httpx.MockTransport(handler)` swapped via a `monkeypatch` of `_admin_http.http_client`. One `handler` per case, returning the response under test. Tests live in `tests/integration/test_admin_<page>.py`.

**Alternatives considered:**
- Real backend in a test container — rejected: slow, and the AppTest+MockTransport path is the documented pattern for the placeholder fallback rendering, which we still want to assert.
- VCR cassettes — rejected: brittle when contracts evolve; AppTest + MockTransport is more readable.

---

## R4 — Theme JSON sandbox

**Decision:** Parse theme JSON with `json.loads` (admin) or `JSON.parse` (widget); validate against an allow-list of keys (`primary_color`, `text_color`, `bubble_color`, `border_radius`); reject anything else with a 422-style inline error. The widget never `eval`s, never `dangerouslySetInnerHTML`s, never injects into a `<style>` tag from raw text.

**Rationale:** Tenant-supplied JSON is untrusted by Principle I (it crosses tenant boundary into the widget at render time). Allow-listing keys, validating each as a hex string / pixel count / known token, and writing into CSS custom properties only after validation eliminates injection.

**Contrast fallback:** When the chosen `primary_color` cannot meet 4.5:1 contrast against the panel background (computed at runtime with a 20-line WCAG ratio function), the widget falls back to a built-in accessible default and emits a `theme_contrast_fallback` telemetry event.

**Alternatives considered:**
- Allow arbitrary CSS — rejected on Principle I + Principle VII grounds.
- Server-side validation only — rejected: the widget renders before the round-trip, so client-side validation is required regardless.

---

## R5 — Mobile sheet mode implementation

**Decision:** Single CSS media query (`@media (max-width: 639px)`) inside `Panel.tsx`'s scoped styles toggles between fixed-size sheet (380×560) and full-viewport mode (`inset: 0`, safe-area inset padding). No JS-driven viewport detection; CSS handles it.

**Rationale:** Pure-CSS responsiveness is the simplest path (Principle VII) and avoids the JS resize-listener bookkeeping that produces flicker on orientation change. Safe-area insets via `env(safe-area-inset-*)`.

**Alternatives considered:**
- `matchMedia` + React state — rejected: more code, more re-renders, no benefit.
- Two separate components — rejected: doubles the test surface for no gain.

---

## R6 — Vitest reshape strategy: keep tests green while extracting components

**Decision:** Phase E PR1 extracts components in a single PR but preserves the test surface: existing `chat.test.tsx` continues to drive the panel through public selectors (`data-testid`s on the rendered output), so a renaming refactor that doesn't change observable behavior keeps the file green. New tests for `Bubble`, `Panel`, and `useChatReducer` ship alongside the extraction.

**Rationale:** The existing 442-line test suite is the regression net for the reshape. If it stays green, the user-visible behavior is preserved. Extracting components without changing the `data-testid` taxonomy is the safe path.

**Implementation notes:** `useChatReducer` becomes a pure function (`state, action → state`) so its tests run without React. `Bubble` and `Panel` tests use `@testing-library/react` with mocked fetch.

**Alternatives considered:**
- Rewrite tests first, then components — rejected: temporarily breaks the regression net.
- Ship Bubble first, then everything else in a follow-up — rejected: a half-extracted ChatPane is harder to read than either the current monolith or the fully split form.

---

## R7 — Axe-core wiring in CI

**Decision:** Add `@axe-core/react` to vitest dev-deps and a single `axe.test.tsx` that mounts `<App>` in the open state and asserts zero `serious` or `critical` violations. Run in the existing vitest job — no new CI job needed.

**Rationale:** One axe assertion in vitest is enough for SC-005; we don't need a separate CI step. Cheap to maintain, hard to regress without noticing.

**Threshold:** Block on `serious` and `critical` only. `minor` / `moderate` violations get logged but don't fail CI — Streamlit-y a11y patterns (Streamlit's own DOM has many `moderate` warnings) would otherwise drown the signal.

**Alternatives considered:**
- Lighthouse-CI — rejected: too heavy for a per-PR check, and overlaps axe.
- Manual audit only — rejected: SC-005 demands automated coverage.

---

## R8 — Bubble launcher: where the open/closed state lives

**Decision:** The open/closed state lives in `main.tsx` (the orchestrator), not in `widget.js` (the loader). The loader still injects the iframe at boot; the iframe's initial render shows `<Bubble>` and only renders `<Panel>` once the user clicks. The widget host page sees only the bubble until interaction.

**Rationale:** Keeping all UI state inside the iframe respects the existing security boundary (host page CSP can be strict; iframe is sandboxed). Driving open/closed from the loader would require `postMessage` plumbing that adds complexity for no benefit.

**Iframe sizing:** Iframe stays at fixed dimensions on desktop (~80×80 px around the bubble; expands when open). Avoiding `iframe { width: 100vw; height: 100vh }` is critical so the bubble doesn't eat page clicks. Trick: when closed, iframe is sized to the bubble; when open, iframe expands. Implemented via `postMessage` from inside out announcing desired iframe dimensions; loader resizes.

**Alternatives considered:**
- Render bubble in the host page directly (no iframe when closed) — rejected: re-introduces XSS surface on the host page; defeats the sandbox model.
- Always-large iframe with `pointer-events: none` on bubble area — rejected: breaks page scroll on mobile.

---

## R9 — Quick-action chip storage shape

**Decision:** Per the spec clarification, chips are persisted in the existing `tenant_agent_configs` row (which the new `PUT /tenants/{tid}/agent-config` endpoint surfaces — Phase 2A). Storage column: a JSON array of strings, max length 6. The widget reads chips from the paired `GET /tenants/{tid}/agent-config` (also Phase 2A) at boot.

**Rationale:** The chip list is part of the tenant's agent personality (greeting, tone, language, rules). Co-locating it with the rest avoids inventing a second persistence surface (Principle VII).

**Defaults:** On tenant creation, the seed migration writes `["View services", "Pricing", "Book appointment", "Talk to human"]`. Tenants override or empty.

**Alternatives considered:**
- Separate `tenant_widget_chips` table — rejected: a single-column edit doesn't justify a table.
- Hard-code in widget bundle — rejected: spec FR-026 places it under tenant control.

---

## R10 — Tenant-admin Audit tab vs. tenant-manager Audit Logs tab

**Decision:** Both tabs share `admin/audit_page.py`. Same module, two render paths gated by `role`:
- Tenant admin → reads `GET /tenants/{tid}/audit-logs` (existing) with `tid` from session.
- Tenant manager → reads `GET /tenants/{tid}/audit-logs` for any tenant via a tenant-picker dropdown, plus the platform-scope `GET /audit-logs` feed delivered in Phase 2A (T039v).

**Rationale:** Two pages with 90% overlap would violate Principle VII; one page with a role branch is simpler and cleaner.

**Alternatives considered:**
- Two separate modules — rejected: duplication.
- Manager view eats tenant view — rejected: tenant scope must always be visually obvious.

---

## Post-Phase-0 Constitution Recheck

All seven principles remain satisfied. No `NEEDS CLARIFICATION` items remain. Phase 1 design can proceed without further blocking research.
