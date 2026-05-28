# Phase 0: Research

Three small technical choices were open at the start of planning. All resolve to the simplest plausible option consistent with Constitution Principle VII (Clean & Simple Code). None are blockers; none change the spec.

## Research 1 — State management: `useState` vs `useReducer`

**Decision**: `useState` in `ChatPane`. No reducer.

**Rationale**:
- The state machine has four states (`idle` / `sending` / `error` / `expired`) and three small pieces of side data (the messages array, the in-flight prompt for retry, the error info). Plain `useState` calls express this directly.
- `useReducer` would be appropriate if there were many cross-state transitions with shared invariants, but every transition here is initiated by a single user action or HTTP response — no complex orchestration.
- Principle VII rejects adding machinery for hypothetical complexity. If the state machine grows past 5–6 transitions later, refactor to `useReducer` then.

**Alternatives considered**:
- `useReducer` with explicit action types — neat but over-engineered for this state count.
- A third-party state library (Zustand, Jotai) — flatly rejected; adds a dependency for zero functional value.
- Class components — rejected as anachronistic; React 18 hooks are the idiom.

## Research 2 — Auto-scroll mechanism

**Decision**: `ref` on the message-list container + `scrollTop = scrollHeight` in a `useEffect` keyed on the messages array length.

**Rationale**:
- The behavior is "after a new message renders, scroll the container to the bottom" — exactly what the effect-on-length pattern expresses.
- Sub-200ms (SC-006) is trivially met because the scroll is synchronous in the same paint pass.
- No need to observe visibility — the spec doesn't require "scroll only if the user was already near the bottom"; FR-008 just says "auto-scroll on new message".

**Alternatives considered**:
- `scrollIntoView({ behavior: "smooth" })` on a sentinel `<div>` at the bottom — slightly fancier; the smooth animation adds time that risks overshooting the 200ms budget on slower devices. Rejected.
- `IntersectionObserver` to detect whether the user has scrolled up — adds "don't yank the view if the user is reading earlier messages" UX. Out of scope for v1; can be added later behind a flag if a tenant complains.
- A timer-based scroll — rejected; React effects already give the right hook.

## Research 3 — Component test library

**Decision**: `@testing-library/react` (RTL) + vitest. Add `@testing-library/react` and `@testing-library/jest-dom` as devDeps.

**Rationale**:
- RTL is the de facto standard for React component testing in 2025; it encourages testing behavior over implementation details, which matches the spec's user-story-driven acceptance scenarios.
- Already integrates cleanly with vitest's jsdom environment (set up in feature 001).
- Bundle size impact: zero (devDep only, never shipped to visitors).

**Alternatives considered**:
- Raw DOM assertions (`document.querySelector`) — works but verbose and brittle; couples tests to DOM structure.
- Enzyme — deprecated for React 18.
- Playwright component testing — out of scope; we don't need a full browser for unit tests, and the e2e test runs at Phase 7 in amer-works.md.

## Items deliberately not researched

- **Message rendering library** (markdown, syntax highlighting, link parsing) — out of scope. v1 renders plain text. If a tenant later needs markdown, that's a separate feature.
- **Streaming reply support** — explicit Assumption in spec.md (replies arrive as one complete payload).
- **Conversation persistence across reloads** — explicit Assumption + FR-018/FR-019 forbid it.
- **Optimistic update conflict resolution** — single-in-flight (FR-005) makes this impossible by design.
- **Internationalization** — out of scope; UI strings are English (spec Assumptions).
