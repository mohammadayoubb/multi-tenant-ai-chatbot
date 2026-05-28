# Implementation Plan: Widget Chat UI

**Branch**: `002-widget-chat-ui` | **Date**: 2026-05-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-widget-chat-ui/spec.md`

## Summary

Replace the chat-ready boot shell from feature 001 with a real chat interface inside the iframe: scrollable message list, Enter-to-send input (Shift+Enter newline), loading indicator, error banner with retry, and a "Session expired, please reload" terminal state. All fetch logic moves into the existing `api.ts` module; chat state lives in React component state and never reaches browser storage. Technical approach: one container component (`ChatPane`) owning state + render, one input subcomponent (`ChatInput`) owning the Enter/Shift+Enter keyboard logic, an extended `api.ts` with `sendChatMessage()`. No new persistence, no new backend code — every requirement is frontend-only.

## Technical Context

**Language/Version**: TypeScript 5.5 (per pinned `frontend/widget/package.json`).
**Primary Dependencies**: React 18.3, Vite 5.4 (build), vitest 1.6 + jsdom 24 + `@testing-library/react` (tests). No new runtime deps.
**Storage**: None. Conversation history lives in React component state and is garbage-collected when the iframe unloads (FR-018, FR-019).
**Testing**: vitest with `environment: jsdom` (per [vitest.config.ts](../../frontend/widget/vitest.config.ts)). Mocked `fetch` for unit tests. Add `@testing-library/react` as a devDep.
**Target Platform**: Modern evergreen browsers (ES2019 target, matches feature 001's loader hardening).
**Project Type**: Embedded browser widget (frontend slice of the multi-service monorepo).
**Performance Goals**: SC-001 reply renders within 200 ms of network arrival; SC-006 auto-scroll completes within 200 ms of new message. Both are local-render budgets, not network-latency commitments.
**Constraints**: Token in volatile memory only (feature 001's discipline carries forward); no persistence of chat content (FR-018); no tenant theming (FR-021); no file/voice/attachment input (FR-020); single in-flight request (FR-005); message max 4000 chars (per Assumptions).
**Scale/Scope**: One iframe = one visitor session. No multiplexing. Session history capped only by browser memory (not enforced — visitors don't have million-message sessions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The plan MUST pass each gate before Phase 0 research and again after Phase 1 design. Cite the constitution principle by number in any waiver.

- [x] **Principle I (Tenant Isolation):** N/A in the widget layer. The `tenant_id` lives in the JWT issued by feature 001; this feature never re-resolves, re-derives, or re-decodes it. Every `/chat` request carries the unmodified bearer token; the server-side auth dep validates and extracts `tenant_id`. The widget itself does not decode the JWT.
- [x] **Principle II (Layered Architecture):** N/A on the backend (no backend changes). Frontend layering: `main.tsx` (entry) → `ChatPane` (state owner + render) → `ChatInput` (keyboard handling, controlled input) → `api.ts` (all HTTP). UI components never call `fetch` directly; all network goes through `api.ts`. No SQL anywhere — the frontend has no DB access by construction.
- [x] **Principle III (Bounded Agent):** N/A. This feature adds zero agent tools, does not modify the agent loop, and does not change tool-selection behavior. It is a consumer of the `/chat` contract.
- [x] **Principle IV (Defense-in-Depth Auth):** The bearer token continues to live in `api.ts`'s module-scope variable (feature 001). Chat messages are sent with `Authorization: Bearer <token>` derived from `getToken()` — the component layer never sees the raw token. A 401 response triggers the terminal "Session expired" state (FR-013) — no automatic refresh, no retry, no token re-acquisition. The visitor must reload the host page (which triggers a fresh exchange per feature 001).
- [x] **Principle V (Lean Serving & Redaction):** N/A — no backend logs change, no model artifacts touched, no new container code. Frontend `console.error` calls only fire on fail-soft paths and never include the bearer token or message content.
- [x] **Principle VI (Phased Build):** Continuation of the parallel-track build documented in DECISIONS.md Decision 5. Phase 2 of Amer's playbook; constitution Phase 7 (Widget). Builds entirely inside Amer's owned files. Consumes Nasser's `POST /chat` via the contract in CONTRACT.md §2.9 — no edit to Nasser's route, no edit to Hiba's auth dep.
- [x] **Principle VII (Clean & Simple Code):** Two new component files (`ChatPane.tsx`, `ChatInput.tsx`), one new test file (`__tests__/chat.test.tsx`), one extension each to `api.ts`, `types.ts`, and `styles.css`. No state-management library, no reducer machinery — plain `useState` is sufficient for the four-state machine (idle / sending / error / expired). No speculative abstractions for "future tenant theming" — FR-021 forbids it. Canonical naming throughout (`session_id`, never `chatId`).

All seven gates ticked. No Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/002-widget-chat-ui/
├── plan.md                         # This file (/speckit-plan output)
├── spec.md                         # Feature specification (/speckit-specify output)
├── research.md                     # Phase 0 output (this command)
├── data-model.md                   # Phase 1 output (this command)
├── quickstart.md                   # Phase 1 output (this command)
├── contracts/
│   └── chat-endpoint-consumer.md   # Phase 1 — how the widget calls /chat (consumer side)
├── checklists/
│   └── requirements.md             # Quality checklist (/speckit-specify output)
└── tasks.md                        # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root — files this feature touches)

```text
frontend/widget/
├── src/
│   ├── main.tsx                    # MODIFY (Amer) — boot shell becomes a thin entry that mounts <ChatPane>
│   ├── api.ts                      # EXTEND (Amer) — add sendChatMessage(); reuse getToken/getSessionId from feature 001
│   ├── types.ts                    # EXTEND (Amer) — add ChatMessage, ChatStatus, ChatResponse types
│   ├── styles.css                  # EXTEND (Amer) — chat-pane / message-bubble / status-banner styles
│   ├── components/
│   │   ├── ChatPane.tsx            # NEW (Amer) — owns state machine + message list + auto-scroll
│   │   └── ChatInput.tsx           # NEW (Amer) — Enter/Shift+Enter keyboard handling
│   └── __tests__/
│       └── chat.test.tsx           # NEW (Amer) — component tests with mocked fetch
└── package.json                    # MODIFY (Amer) — add @testing-library/react devDep
```

**Structure Decision**: Frontend-only feature. The `ChatPane` + `ChatInput` split is the minimum useful decomposition: `ChatPane` owns the four-state machine and the auto-scroll, `ChatInput` owns the non-trivial Enter/Shift+Enter keyboard behavior. A single-file implementation would muddle event handling with state-machine logic; further splitting (separate `MessageBubble`, separate `StatusBanner`) would create files whose entire contents are one `<div>` each — pure Principle-VII waste. The stop point is deliberate.

## Phase 0: Research

See [research.md](research.md). Resolves three small decisions: (1) state-management approach (`useState` vs `useReducer`), (2) auto-scroll mechanism (scroll-to-bottom ref vs `IntersectionObserver`), (3) test library choice (`@testing-library/react` vs raw DOM assertions). All resolve to the simplest plausible option.

## Phase 1: Design & Contracts

- **Data model**: [data-model.md](data-model.md) — `ChatMessage` (transient, in-memory), `ChatStatus` enum (the state machine), `ChatResponse` consumer shape (defensive parse of what Nasser returns).
- **Contracts**: [contracts/chat-endpoint-consumer.md](contracts/chat-endpoint-consumer.md) — exact request shape the widget sends; defensive treatment of every response field; mapping of `route` values to UI behavior.
- **Quickstart**: [quickstart.md](quickstart.md) — local-dev steps to mount the widget, exchange a token, send a message, force a 401, force a 500 + retry, and verify no chat content lands in browser storage.

## Complexity Tracking

> No violations. No entries required.

## Post-Design Constitution Re-Evaluation

After Phase 1 artifacts were written:

- **Principle II**: Re-confirmed. `ChatPane` and `ChatInput` do not call `fetch` directly; all network goes through `api.ts` per the contracts doc.
- **Principle IV**: Re-confirmed. The data-model.md state machine has no path that writes the token to anywhere except the existing `api.ts` module-scope variable. The 401 state is terminal — no automatic re-acquisition.
- **Principle VII**: Re-confirmed. Two new components, two file extensions, one test file. No reducer, no context provider, no state-management library, no theme system.

All gates remain ticked. Ready for `/speckit-tasks`.
