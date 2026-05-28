# Implementation Plan: Widget Loader Production Hardening

**Branch**: `003-widget-loader-hardening` | **Date**: 2026-05-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-widget-loader-hardening/spec.md`

## Summary

Production-harden the embeddable widget loader so a tenant can paste a single `<script>` tag onto an arbitrary site and have the chat widget mount safely. Concretely: the loader at [frontend/widget/public/widget.js](../../frontend/widget/public/widget.js) must read its backend origin from a `data-backend-url` attribute (defaulting to the loader's own origin, never a hardcoded host); mount the iframe with hardened `sandbox`/`referrerpolicy`/`title` attributes; mount at most once per widget id; and fail soft (single `console.error`, no host-page exception) when misconfigured. Add a checked-in `host-test.html` so the local embed flow is one-click testable, and pin the Vite production build to an ES2019 target with single-file loader output.

The current [frontend/widget/public/widget.js](../../frontend/widget/public/widget.js) already implements most of these behaviors (read during feature 001 — see commit `d53268f`). This feature **locks them in** with vitest coverage, removes the gap (no `vite.config.ts` exists yet, no host-test page exists yet), and validates the contract against jsdom so future edits cannot regress silently.

## Technical Context

**Language/Version**: TypeScript 5.5 for the iframe React app; plain JavaScript at ES2019 syntax for the loader itself (no transpile — copied verbatim by Vite's `public/` mechanism).
**Primary Dependencies**: Vite 5.4 (build), Vitest 1.6 + jsdom 24 (test). No new runtime dependencies. No backend changes.
**Storage**: N/A — loader is a pure DOM client; FR-014 explicitly forbids `localStorage`/`sessionStorage`/`document.cookie` access on the host page.
**Testing**: Vitest with jsdom environment (existing setup at [frontend/widget/vitest.config.ts](../../frontend/widget/vitest.config.ts)). New tests live under `frontend/widget/src/__tests__/loader.test.ts` and instantiate the loader by `<script>`-injecting `public/widget.js` into a jsdom document.
**Target Platform**: Tenant browsers (evergreen + long-tail down to ES2019-compliant engines). Loader executes on third-party origins; iframe loads from the platform origin.
**Project Type**: Frontend slice — Amer-owned. No backend, no DB, no migrations.
**Performance Goals**: Loader must parse and mount in under 50 ms on a cold page so it does not delay tenant page interaction. Bundle size for the loader file stays under 4 KB minified (currently ~2 KB hand-authored).
**Constraints**:
  - Zero runtime dependencies (loader is dependency-free; cannot import npm packages because it ships as `/public/widget.js`).
  - No hardcoded hostnames or ports anywhere in the loader (SC-006).
  - Must not throw to the host page under any input (FR-009).
  - Phase 7 (Widget) work only — no backend, agent, RLS, or modelserver touches.
**Scale/Scope**: One loader file, one host-test HTML, one Vite config. Roughly 80 LOC of production code already mostly written; ~150 LOC of new vitest coverage.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Principle I (Tenant Isolation):** No new tables, no DB queries, no pgvector access. The loader passes the tenant-supplied `widget_id` through to the iframe URL; `tenant_id` resolution stays server-side (origin-validated in `POST /widgets/token`, established in feature 001). The loader never claims to derive `tenant_id` and the iframe sandbox attributes (`allow-same-origin` is for the platform origin, not the host origin) preserve the existing isolation boundary.
- [x] **Principle II (Layered Architecture):** N/A — frontend-only change. No routes, services, or repositories touched.
- [x] **Principle III (Bounded Agent):** N/A — no agent tool added, removed, or modified. Loader does not call the agent.
- [x] **Principle IV (Defense-in-Depth Auth):** FR-014 codifies the existing rule that the loader does not touch host-page `localStorage`/`sessionStorage`/`cookies`. The token exchange remains inside the iframe (per feature 001). Sandbox `allow-same-origin` applies to the platform origin the iframe loads from — required so the iframe can call the platform API with credentials it owns, not the host's. No secrets in the loader source; no `.env` reads. Origin validation remains server-side at `POST /widgets/token`.
- [x] **Principle V (Lean Serving & Redaction):** N/A — no serving container, no model artifacts, no logs persisted (the single `console.error` on misconfiguration is a host-page console message, not a server log).
- [x] **Principle VI (Phased Build):** Phase 7 (Widget, widget auth, origin allowlist, public chat — Amer-owned). This work hardens the Phase 7 loader and the Phase 10 (CI/CD) prerequisite of a buildable widget. No phase boundaries crossed.
- [x] **Principle VII (Clean & Simple Code):** Smallest change that satisfies the spec. The loader is hand-authored at ES2019 syntax (no class fields, no optional chaining, no nullish coalescing) — already simpler than relying on a transpiler. No speculative abstractions. One vite.config.ts that does one thing (set `build.target: 'es2019'` and lock the public copy passthrough).

All seven gates pass. No entries needed in **Complexity Tracking**.

## Project Structure

### Documentation (this feature)

```text
specs/003-widget-loader-hardening/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (loader contract entities)
├── quickstart.md        # Phase 1 output (one-command local sanity check)
├── contracts/
│   └── widget-loader.md # Phase 1 output: loader DOM contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (already created)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
frontend/widget/
├── public/
│   ├── widget.js              # MODIFIED — production-hardened loader (mostly already correct from feat 001)
│   └── host-test.html         # NEW — one-click local embed sanity-check page
├── src/
│   ├── __tests__/
│   │   └── loader.test.ts     # NEW — jsdom tests for loader behavior
│   └── ...                    # (unchanged React iframe app)
├── vite.config.ts             # NEW — ES2019 target, public-asset passthrough verified
├── vitest.config.ts           # UNCHANGED — already picks up src/__tests__/**.test.ts
├── package.json               # UNCHANGED — no new deps
└── ...
```

**Structure Decision**: Frontend-only slice under [frontend/widget/](../../frontend/widget/). The loader stays at `public/widget.js` (Vite copies `public/` verbatim, so the loader is its own single-file artifact at `dist/widget.js` after build — satisfying FR-012 with zero bundling). The new `vite.config.ts` sets `build.target: 'es2019'` for the React iframe app and acts as a load-bearing assertion: the build target is committed, not implicit. Tests live alongside the existing widget tests under `src/__tests__/`. The host-test page lives in `public/` so the same Vite dev server that serves the iframe app also serves it (one origin, one command, no extra HTTP server).

## Complexity Tracking

> No entries — all constitution gates pass without waivers.
