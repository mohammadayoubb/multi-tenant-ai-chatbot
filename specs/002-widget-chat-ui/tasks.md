---

description: "Tasks for the Widget Chat UI feature"
---

# Tasks: Widget Chat UI

**Input**: Design documents from `specs/002-widget-chat-ui/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Test tasks INCLUDED because the spec explicitly requests component tests (the "Tests:" block in the feature description) and SC-002/SC-003/SC-005 require automated verification.

**Organization**: Tasks grouped by user story. The three stories: US1 (P1) visitor sends a message and gets an answer, US2 (P1) graceful failure handling, US3 (P2) session privacy + ephemerality.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, or US3 (omitted for Setup, Foundational, and Polish phases)
- Every task description includes the exact file path

## Path Conventions

Frontend-only feature. All paths under `frontend/widget/src/`. No backend changes, no new tables, no `app/` edits.

Amer-owned files only. Confirmed against `# Owner: Amer` headers and CONTRACT.md §3.

---

## Phase 1: Setup

**Purpose**: Add the one new devDep we need; no other project-level changes.

- [X] T001 [P] Add `@testing-library/react` (^16.0.0) and `@testing-library/jest-dom` (^6.4.0) to `devDependencies` in [frontend/widget/package.json](../../frontend/widget/package.json). Run `npm install` afterwards to update the lockfile.
- [X] T002 [P] Verify [frontend/widget/vitest.config.ts](../../frontend/widget/vitest.config.ts)'s `include` glob still matches the test files this feature adds (`src/**/__tests__/**/*.test.{ts,tsx}`). Add `setupFiles: ["./src/__tests__/setup.ts"]` if `@testing-library/jest-dom` matchers need to be wired up.

**Checkpoint**: `npm install` clean; `npx vitest --run` finds zero tests but exits 0.

---

## Phase 2: Foundational

**Purpose**: Domain types and the `api.ts` extension. Both user-story phases consume them.

**⚠️ CRITICAL**: No user-story work starts until this phase completes.

- [X] T003 Extend [frontend/widget/src/types.ts](../../frontend/widget/src/types.ts) with the three transient shapes from [data-model.md](data-model.md): `ChatMessage`, `ChatResponse` (defensive-parse shape — `answer` + `route` required, the rest optional), `ChatStatus` union (`"idle" | "sending" | "error" | "expired"`). Export `ChatErrorKind = "network" | "server"` for `errorInfo`.
- [X] T004 Extend [frontend/widget/src/api.ts](../../frontend/widget/src/api.ts) with `sendChatMessage(message: string): Promise<ChatResponse>`. Reads the bearer token via the existing `getToken()` and the session id via `getSessionId()`. POSTs `/widgets/chat` with `Authorization: Bearer <token>` and body `{ message, session_id }` per [contracts/chat-endpoint-consumer.md](contracts/chat-endpoint-consumer.md). On HTTP 401 throw `new ApiError("expired")`; on any other non-2xx or network failure throw `new ApiError("server")` or `new ApiError("network")` respectively. On 2xx, run the defensive parser (data-model.md §2): require `answer` and `route`, default `used_tools=[]`, `citations=[]`, `ticket_id=null`; if `answer` or `route` is missing/wrong type, throw `new ApiError("server")`.
- [X] T005 [P] Add a tiny `ApiError` class (extends `Error`) in [frontend/widget/src/api.ts](../../frontend/widget/src/api.ts) with a `kind: "expired" | "server" | "network"` discriminator. Export it. Used by `ChatPane` to route into the correct state.

**Checkpoint**: `types.ts` and `api.ts` typecheck (`npx tsc --noEmit`). No tests run yet.

---

## Phase 3: User Story 1 — Visitor sends a message and gets an answer (P1) 🎯 MVP

**Goal**: A visitor in chat-ready state types a question, presses Enter, and sees their message + the assistant's reply in the conversation pane. The pane auto-scrolls.

**Independent Test**: From [quickstart.md](quickstart.md) Step 3, send "What are your hours?" → user bubble appears immediately, loading indicator shows, assistant reply renders, pane scrolls to keep it in view.

### Tests for User Story 1 (write first, must fail before implementation)

- [X] T006 [P] [US1] Create [frontend/widget/src/__tests__/chat.test.tsx](../../frontend/widget/src/__tests__/chat.test.tsx) with the happy-path component test: mount `<ChatPane>` with a pre-populated token, type "What are your hours?", press Enter; assert `fetch` was called once with URL `/widgets/chat` (or the configured backend URL), method `POST`, `Authorization: Bearer …` header, JSON body `{message: "What are your hours?", session_id: "<known>"}`; after the mock resolves with `{answer:"We're open 9-5", route:"agent"}`, assert both bubbles are in the DOM (use `findByText`).
- [X] T007 [P] [US1] Extend `chat.test.tsx` with the keyboard test: typing into the input then pressing Enter (no modifiers) submits; Shift+Enter inserts a newline (assert input value contains "\n", no fetch fired); whitespace-only input + Enter does nothing (no fetch).
- [X] T008 [P] [US1] Extend `chat.test.tsx` with the single-in-flight test: rapid-fire three Enter presses with the fetch mock returning a never-resolving promise; assert exactly one `fetch` call.
- [X] T009 [P] [US1] Extend `chat.test.tsx` with the auto-scroll test: mount with 20 pre-existing messages in the pane (use a test-only prop or simulate by sending many), assert the container's `scrollTop` equals `scrollHeight - clientHeight` after the latest message renders.

### Implementation for User Story 1

- [X] T010 [US1] Create [frontend/widget/src/components/ChatInput.tsx](../../frontend/widget/src/components/ChatInput.tsx) — a controlled `<textarea>` that emits `onSubmit(text)` when Enter (no modifiers) is pressed AND the trimmed value is non-empty. Shift+Enter inserts a newline (default browser behavior — don't preventDefault). Props: `disabled: boolean`, `onSubmit: (text: string) => void`. Maintain internal state for the textarea value; clear on submit. Max-length attribute 4000 per spec Assumptions.
- [X] T011 [US1] Create [frontend/widget/src/components/ChatPane.tsx](../../frontend/widget/src/components/ChatPane.tsx) — owns `messages: ChatMessage[]`, `status: ChatStatus`, `pendingPrompt: string | null`, `errorInfo: ChatErrorKind | null` via `useState`. On `ChatInput.onSubmit`, append a user `ChatMessage`, set `status="sending"`, call `sendChatMessage()` (from `api.ts`), on success append an assistant `ChatMessage` and set `status="idle"`. Render `<ChatInput disabled={status === "sending" || status === "expired"} onSubmit={…} />` at the bottom. Render the message list above using a `ref` on the scroll container; in a `useEffect` keyed on `messages.length`, set `container.scrollTop = container.scrollHeight`.
- [X] T012 [US1] Inline-render assistant and user bubbles inside `ChatPane.tsx` (do NOT extract a `MessageBubble` component — plan.md Project Structure Decision keeps it inline). Style with two CSS classes (`message-bubble--user`, `message-bubble--assistant`) added in T013.
- [X] T013 [US1] Extend [frontend/widget/src/styles.css](../../frontend/widget/src/styles.css) with `.chat-pane`, `.message-list`, `.message-bubble`, `.message-bubble--user`, `.message-bubble--assistant`, `.chat-input`, `.status-banner`, `.ticket-pill` styles. Keep it minimal — no theme variables (FR-021). Single fixed visual style.
- [X] T014 [US1] Modify [frontend/widget/src/main.tsx](../../frontend/widget/src/main.tsx) to mount `<ChatPane />` once the existing `status === "ready"` branch fires (replace the chat-ready shell from feature 001 with `<ChatPane />`). The "Widget unavailable" branch and "Loading…" branch from feature 001 stay unchanged.
- [X] T015 [US1] Add a loading indicator inside the message list while `status === "sending"` (a small "…" or three-dot animation rendered as a non-message DOM element). Visible only during in-flight; gone the moment the assistant bubble renders.

**Checkpoint**: T006-T009 green. Manual happy-path send works in a browser per quickstart.md Step 3. **Refusals not handled yet** — a /chat 500 will crash the UI; US2 fixes that.

---

## Phase 4: User Story 2 — Conversation handles platform failures gracefully (P1)

**Goal**: 401 → terminal "Session expired" prompt, input disabled, no retry. 5xx / network failure → error banner with Retry that re-sends the last message. Missing optional response fields don't crash the UI. Unknown `route` values render as normal replies. `route === "escalate"` shows a ticket pill only when `ticket_id` is non-empty.

**Independent Test**: From quickstart.md Steps 4-5, force a 401 → see terminal prompt + disabled input; force a 500, click Retry → exactly one user bubble + one assistant bubble; throw a stack of malformed-response shapes at the parser → no error indicator and the reply text renders.

### Tests for User Story 2 (write first, must fail before implementation)

- [X] T016 [P] [US2] Extend [chat.test.tsx](../../frontend/widget/src/__tests__/chat.test.tsx) with the 401 test: mock `sendChatMessage` to throw `ApiError("expired")` once; assert the conversation pane shows the text "Session expired, please reload", the input is `disabled`, and no second fetch is ever attempted (even if the user tries to type).
- [X] T017 [P] [US2] Extend `chat.test.tsx` with the 500 + retry test: mock the first `sendChatMessage` to throw `ApiError("server")`, the second to resolve with a happy reply; assert the banner appears with a "Retry" button; click Retry; assert the conversation pane ends with exactly ONE user bubble for the retried message and ONE assistant bubble (use `getAllByTestId("message-bubble--user")` length === 1).
- [X] T018 [P] [US2] Extend `chat.test.tsx` with the network-error test: same as T017 but mock the first call to reject with `ApiError("network")`; assert the same banner shape; verify the banner copy contains no HTTP codes, no stack frames, no raw response body (regex assertion: no `/\b\d{3}\b/` matches in the banner text other than 4000 from the input maxlength which isn't in the banner anyway).
- [X] T019 [P] [US2] Extend `chat.test.tsx` with a defensive-parse sweep: build an array of 20 malformed-response shapes (missing `citations`, missing `ticket_id`, `used_tools: null`, `citations: "string-not-array"`, extra unknown keys, etc.); for each, mock `sendChatMessage` to resolve with that shape; assert the assistant bubble renders the `answer` text and NO error indicator appears in the DOM (`queryByRole("alert")` is null). Tests SC-002.
- [X] T020 [P] [US2] Extend `chat.test.tsx` with the `route` mapping test: parametrize over `["workflow", "agent", "blocked", "escalate", "made-up-value"]`; for `escalate` with a non-empty `ticket_id` assert the pill renders with `"Ticket #<id>"`; for `escalate` with `ticket_id: null` assert NO pill renders; for every other route assert NO pill renders.
- [X] T021 [P] [US2] Extend `chat.test.tsx` with a paranoia test: across all the error scenarios in T016-T018, assert that nowhere in the rendered DOM is an HTTP code (`404`, `500`, etc.), a stack-trace token (`at `, `.js:`), or the raw bearer token visible. Tests FR-017.

### Implementation for User Story 2

- [X] T022 [US2] Extend `ChatPane.tsx` state machine: on `ApiError("expired")`, set `status="expired"` and never transition out. On `ApiError("server")` or `ApiError("network")`, set `status="error"` and capture `errorInfo`. Both happy-path and error returns keep the user bubble visible (it was appended at submit time before the call started).
- [X] T023 [US2] In `ChatPane.tsx`, render the terminal expired banner (text + disabled input) when `status === "expired"`. Use a `<div role="status">` for accessibility; the text is hard-coded "Session expired, please reload".
- [X] T024 [US2] In `ChatPane.tsx`, render the retry banner when `status === "error"`. Banner contains the text "Couldn't reach the assistant." and a `<button>Retry</button>`. Use `<div role="alert">`. Clicking Retry calls a private `retryLast()` method that re-invokes `sendChatMessage(pendingPrompt)` and removes the just-appended-but-failed user message from the list IF the spec requires no-duplicate (FR-016) — actually re-reading: keep the user bubble, just dispatch the request again and append the assistant reply on success. The "no duplicate" guarantee means we do NOT append a second user bubble on retry.
- [X] T025 [US2] In `ChatPane.tsx`, after a successful retry, clear the banner (`status` returns to `idle`), clear `errorInfo`, and append the assistant bubble — leaving the conversation pane with exactly ONE user bubble + ONE assistant bubble for the logical exchange (FR-015, FR-016).
- [X] T026 [US2] In `ChatPane.tsx`, render the ticket pill at the bottom of the message list when the LAST assistant message in `messages` has `route === "escalate"` AND a non-empty `ticket_id`. Use a small `<span className="ticket-pill" data-testid="ticket-pill">Ticket #{id}</span>`. Suppress entirely otherwise.
- [X] T027 [US2] In `ChatPane.tsx`, when an assistant message has an unknown `route` value, log via `console.warn("[concierge.widget] unknown route value", routeValue)` and render the assistant bubble normally — no pill, no error indicator. (Matches contracts/chat-endpoint-consumer.md §`route` field handling.)
- [X] T028 [US2] Confirm `api.ts` `sendChatMessage` already enforces the defensive parse (T004 covered the implementation); verify it returns the response object with safe defaults applied, never a raw `await res.json()`.

**Checkpoint**: T006-T021 green. Manual quickstart Steps 4-5 work: 401 produces terminal prompt; 500 produces banner with Retry; retry produces single user+assistant pair; malformed responses render normally.

---

## Phase 5: User Story 3 — Visitor's session is private and ephemeral (P2)

**Goal**: After any conversation length, no chat content / token / session-id is visible in cookies, localStorage, sessionStorage, or IndexedDB at any point. Reload clears state (component remount = fresh session).

**Independent Test**: From quickstart.md Step 6, have a multi-message conversation, inspect every browser storage, see nothing chat-related. Reload, see empty pane and new token exchange.

### Tests for User Story 3 (write first, must fail before implementation)

- [X] T029 [P] [US3] Extend [chat.test.tsx](../../frontend/widget/src/__tests__/chat.test.tsx) with a storage-discipline sweep: send 10 messages with mocked replies (mix of plain + escalate + unknown route); after every send, iterate `localStorage`, `sessionStorage`, and `document.cookie` and assert NO key/value contains any of (a) the bearer token, (b) any `session_id`, (c) any rendered assistant reply text, (d) any user-message text. Tests SC-005.
- [X] T030 [P] [US3] Extend `chat.test.tsx` with the unmount/remount test: mount `<ChatPane>`, send messages, unmount via `rerender(<></>)`; remount `<ChatPane>` and assert it starts with an empty `messages` array (no leakage between component lifetimes — covers FR-019 at the component level; actual page-reload behavior is covered by feature 001 retesting at the host level).

### Implementation for User Story 3

- [X] T031 [US3] Audit `ChatPane.tsx`: confirm `messages`, `status`, `pendingPrompt`, `errorInfo` are all `useState` values (component-local, no `useRef` to module scope, no global stores, no `window.*` assignments). Add a top-of-file comment block citing FR-018 / FR-019 / Constitution Principle IV.
- [X] T032 [US3] Audit `ChatInput.tsx`: confirm its internal textarea value is `useState`, never written to `localStorage` for "draft preservation" or similar UX gimmicks. Same top-of-file comment block.
- [X] T033 [US3] Audit `api.ts` (already done in feature 001 — re-verify): confirm `getToken` / `getSessionId` still read only the module-scope variable; no new code path writes them anywhere else.

**Checkpoint**: T006-T030 green. Manual quickstart Step 6 shows zero token/chat content in any browser storage; reload starts fresh.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: Final verification, build sanity, PR prep.

- [X] T034 Run `npm test` in `frontend/widget/`. Assert all tests green; zero skipped (unless intentionally documented).
- [X] T035 [P] Run `npm run build` in `frontend/widget/` and assert the production bundle still builds. Bundle size sanity check: gzipped output should remain in the small-KB range (no accidental dependency bloat).
- [ ] T036 [P] Walk [quickstart.md](quickstart.md) Steps 1-6 manually against `docker compose up --build api`; capture the output in the PR description. T040-equivalent for Phase 2.
- [X] T037 [P] Confirm `git diff --name-only` lists ONLY paths under `frontend/widget/`. No `app/`, no `tests/security/`, no Hiba/Nasser/Ayoub files. Tag @Hiba and @Ayoub only if a teammate's contract interpretation comes up in review; otherwise this PR is single-reviewer (Amer + one teammate of choice for code review).
- [ ] T038 Update [amer-works.md](../../amer-works.md) Phase 2 — mark the "Done when" criteria as ticked, link the PR.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies. Start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 (`@testing-library/react` installed before any test runs). **Blocks all user-story phases.**
- **Phase 3 (US1)**: Depends on Phase 2 (types + `sendChatMessage`). Independent of US2 and US3 from a code standpoint.
- **Phase 4 (US2)**: Depends on Phase 2 AND on the US1 component skeleton (`ChatPane` exists, `ChatInput` exists). Extends the state machine — must come after US1's `idle`/`sending` paths land.
- **Phase 5 (US3)**: Depends on Phase 2 AND the existing US1/US2 components (verification + audit work, not new code).
- **Phase 6 (Polish)**: Depends on US1+US2+US3 being green.

### Task Dependencies Within Each Story

**US1**:
- T006-T009 (tests) before T010-T015 (implementation).
- T010 (`ChatInput.tsx`) and T011 (`ChatPane.tsx`) can be authored in parallel since they're separate files; but `ChatPane` imports `ChatInput`, so finalize `ChatInput`'s props first.
- T013 (styles) is parallel with the components.
- T014 (`main.tsx`) depends on T011.
- T015 (loading indicator) modifies `ChatPane.tsx` — sequential after T011.

**US2**:
- T016-T021 (tests) before T022-T028 (implementation).
- T022-T028 all modify `ChatPane.tsx` — sequential within the file.

**US3**:
- T029, T030 (tests) before T031-T033 (audits).
- T031-T033 are read-only audits on existing files — can run in parallel.

### Parallel Opportunities

- **Phase 1**: T001 + T002 in parallel.
- **Phase 2**: T003 (types) + T005 (ApiError class in api.ts) can land first; T004 (sendChatMessage) depends on both.
- **Phase 3**: All four tests (T006, T007, T008, T009) in parallel (same file, different `describe` blocks). Implementation tasks T010, T011, T013 can be authored in parallel; T014/T015 sequential.
- **Phase 4**: Six test tasks (T016-T021) in parallel.
- **Phase 5**: T029 + T030 in parallel; T031-T033 in parallel.
- **Phase 6**: T035-T037 in parallel.

---

## Parallel Example: User Story 1

```text
# After Phase 2 is green, fire these in parallel:

Task: T006 [P] [US1] Happy-path send test in src/__tests__/chat.test.tsx
Task: T007 [P] [US1] Keyboard handling test in same file (different describe)
Task: T008 [P] [US1] Single-in-flight test
Task: T009 [P] [US1] Auto-scroll test

# Then implementation:
Task: T010 [US1] ChatInput.tsx
Task: T011 [US1] ChatPane.tsx        (depends on T010 props finalized)
Task: T013 [US1] styles.css           (parallel with components)
Task: T012 [US1] Inline bubbles in ChatPane (sequential after T011)
Task: T014 [US1] Wire main.tsx       (sequential after T011)
Task: T015 [US1] Loading indicator    (sequential after T011)
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1: Setup (3 min — npm install).
2. Phase 2: Foundational types + `sendChatMessage` (~30 min).
3. Phase 3: US1 — chat-ready happy path lights up.
4. **STOP and VALIDATE**: Run T006-T009; quickstart.md Step 3 in a browser.
5. ⚠️ **Not shippable yet** — at this stage, any `/chat` failure crashes the UI. US2 must follow before merge.

### Incremental Delivery (recommended)

1. Setup + Foundational → foundation ready.
2. US1 → happy-path demo works (testable, NOT shippable for the reason above).
3. US2 → failure handling. **First shippable point.** PR can open here.
4. US3 → privacy verification. Audits and tests, very little new code.
5. Polish → quickstart walk, build sanity, PR prep.

### Solo Developer Strategy (Amer)

- Phase 2: T003 + T005 first (separate files), then T004.
- Phase 3: write all four tests (one file, separate describe blocks) before implementation.
- Phase 4: same pattern — six tests up top, then walk implementation sequentially in `ChatPane.tsx`.
- Phase 5: write the two storage tests, then audit (mostly comment additions).

---

## Format Validation

Every task above conforms to: `- [ ] TXXX [P?] [Story?] description with file path`.
- Setup (T001-T002): no `[Story]` label ✓
- Foundational (T003-T005): no `[Story]` label ✓
- US1 (T006-T015): all carry `[US1]` ✓
- US2 (T016-T028): all carry `[US2]` ✓
- US3 (T029-T033): all carry `[US3]` ✓
- Polish (T034-T038): no `[Story]` label ✓

## Task Count Summary

| Phase | Count | Story |
|---|---|---|
| Setup | 2 | — |
| Foundational | 3 | — |
| US1 — Visitor sends and gets reply | 10 | US1 |
| US2 — Graceful failure | 13 | US2 |
| US3 — Privacy + ephemerality | 5 | US3 |
| Polish | 5 | — |
| **Total** | **38** | |

Parallelizable tasks (marked `[P]`): 19.
Tasks blocked on teammates: 0 (this feature is consumer-only of Nasser's `/chat`; no new dependency on Hiba or Ayoub).
