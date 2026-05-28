# Feature Specification: Widget Chat UI

**Feature Branch**: `002-widget-chat-ui`
**Created**: 2026-05-26
**Status**: Draft
**Input**: User description: "Build a real chat UI inside the embedded widget iframe. Scrollable history, Enter-to-send / Shift+Enter newline, loading indicator, error banner with retry, defensive parsing of /chat responses, escalate-route ticket pill, 401-triggered 'Session expired, please reload', token in module memory only, all fetch logic in api.ts."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Visitor sends a message and gets an answer (Priority: P1)

A visitor on an allowlisted host page sees the widget reach its chat-ready state (from feature 001). They type a question, press Enter (or click Send), and within a moment see the agent's reply appear below their message. They can ask follow-up questions; the conversation scrolls and the most recent exchange is always visible without manual scrolling.

**Why this priority**: This is the entire purpose of the widget from a visitor's perspective. Feature 001 proved the platform can authorize the visitor; this story turns that capability into an actual chat experience. Without this, every prior phase delivers no end-user value.

**Independent Test**: Embed the widget on an allowlisted host page, wait for it to reach chat-ready, type "what are your hours?", press Enter. Within a few seconds the agent's reply appears in the conversation pane, and the input clears for the next message. Repeat — the second exchange appears below the first, and the pane auto-scrolls so the latest exchange is in view.

**Acceptance Scenarios**:

1. **Given** the widget is in chat-ready state, **When** the visitor types text and presses Enter, **Then** the message appears immediately in the conversation, the input clears, a loading indicator shows, and an agent reply appears below it once the platform responds.
2. **Given** the conversation has more messages than fit in the visible pane, **When** a new message arrives, **Then** the pane scrolls so the new message is visible.
3. **Given** the input is empty (or only whitespace), **When** the visitor presses Enter, **Then** nothing is sent and no entry is added to the conversation.
4. **Given** the visitor presses Shift+Enter, **When** the input has focus, **Then** a newline is inserted in the input rather than sending.
5. **Given** a previous request is still pending, **When** the visitor presses Enter again, **Then** the second request is not dispatched until the first completes (no duplicate sends).

---

### User Story 2 — Conversation handles platform failures gracefully (Priority: P1)

When the platform returns an error, a visitor sees a clear, non-technical indication of what's wrong and what to do next — never a blank pane, a raw HTTP code, or a JavaScript stack trace. If their session has expired, they're told to reload; if the platform is unreachable or returned a server error, they can retry the last message with one click. The conversation history they've already had remains visible while they decide what to do.

**Why this priority**: Without graceful failure handling, the first time anything goes wrong the widget looks broken — and "looks broken" on a tenant's customer-facing site is worse than not shipping the widget at all.

**Independent Test**: Force the platform to return three failure shapes — 401, 500, and a network drop — between successful exchanges. After each failure, the conversation history remains visible; the appropriate user-facing message appears (reload prompt for 401, retry button for 500/network); the visitor can click retry and the failed message goes through.

**Acceptance Scenarios**:

1. **Given** the visitor sends a message, **When** the platform replies with an authentication failure, **Then** the conversation pane shows "Session expired, please reload" and the input is disabled. No automatic retry occurs.
2. **Given** the visitor sends a message, **When** the platform replies with a server error OR the network call fails, **Then** an error banner appears with a "Retry" affordance; clicking Retry re-sends the last message.
3. **Given** the platform replies but the response is missing optional fields (e.g., no citations, no ticket_id, no used_tools), **When** the widget renders the reply, **Then** the reply text is shown normally and no error indicator appears.
4. **Given** a successful exchange follows a failed-then-retried exchange, **When** the conversation pane is reviewed, **Then** failed-and-retried exchanges show as a single successful exchange (no duplicated user message).
5. **Given** the platform reply indicates the conversation has been routed to a human, **When** the reply renders, **Then** a small pill at the bottom of the conversation displays the human-follow-up reference (e.g., "Ticket #abc123").

---

### User Story 3 — Visitor's session is private and ephemeral (Priority: P2)

A visitor's chat conversation never lives anywhere they didn't intend. When they close the tab, the conversation is gone — no record is left in browser storage, no cookie carries any of it to other sites, and reloading the page starts a fresh conversation. A visitor browsing in private/incognito mode sees no difference from regular browsing.

**Why this priority**: Tenants embed the widget on pages where visitor privacy matters (purchase pages, support pages, account pages). A widget that secretly leaves traces in browser storage is a compliance and trust failure even if it never leaks across tenants.

**Independent Test**: Have a multi-message conversation in the widget. Open browser dev tools and inspect cookies, localStorage, sessionStorage, and IndexedDB for both the host page's origin and the widget's origin — none of the chat content, token, or session identifier should be visible. Reload the page. The conversation pane is empty and a fresh token exchange runs (per feature 001).

**Acceptance Scenarios**:

1. **Given** the visitor has exchanged multiple messages, **When** browser storage is inspected (cookies, localStorage, sessionStorage, IndexedDB), **Then** no chat message text, no token, and no session identifier are persisted in any storage that survives page reload.
2. **Given** the visitor reloads the page, **When** the widget re-mounts, **Then** the conversation pane is empty and the widget re-runs the boot-time token exchange (no carryover from the prior conversation).

---

### Edge Cases

- **Empty or whitespace-only input**: ignored on send.
- **Maximum message length**: messages above an agreed character cap (default 4000) are rejected client-side with an inline indicator rather than truncated silently.
- **Rapid send (user mashes the send button)**: only one request is in flight at a time. The Send affordance is disabled while a reply is pending.
- **Reply containing route value the widget doesn't recognize**: the reply text is shown normally; no pill, no special UI; the unknown route is treated as a generic agent response.
- **Reply containing route `escalate` but no `ticket_id`**: the reply text is shown, and the pill is suppressed (or shown as "Ticket pending") — never crashes the UI.
- **Reply containing route `blocked`**: the reply text is shown (the platform-side guardrail will have already produced a safe refusal message); no error banner.
- **Token expires mid-conversation**: covered by US2's 401 path.
- **First message of the session fails with 401**: same "Session expired" prompt as mid-conversation; the visitor has not yet entered anything irreplaceable.
- **Visitor types while a reply is rendering**: input accepts characters but Send remains disabled until the prior reply completes.
- **Visitor's browser tab is backgrounded during a pending reply**: when refocused, the reply is rendered if it arrived during the background, or the loading indicator continues if it has not.
- **Replies arrive out of order** (a stale slow reply lands after a newer one): out of scope — the widget enforces single-in-flight (see "rapid send" above), so this cannot happen in this phase.

## Requirements *(mandatory)*

### Functional Requirements

**Composing and sending**

- **FR-001**: The widget MUST present a text input affordance in the chat-ready state.
- **FR-002**: Pressing Enter (without modifiers) MUST submit the message; Shift+Enter MUST insert a line break in the input rather than submitting.
- **FR-003**: The widget MUST NOT submit a message whose content is empty after trimming surrounding whitespace.
- **FR-004**: The widget MUST submit each message with the visitor's bearer session credential (obtained per feature 001) and the visitor's session identifier so the platform can correlate the conversation.
- **FR-005**: The widget MUST permit at most one in-flight message request at a time; the Send affordance MUST remain disabled until the pending reply has resolved or failed.

**Displaying the conversation**

- **FR-006**: The widget MUST display every user-sent message in the conversation pane immediately on send (before the platform reply arrives).
- **FR-007**: The widget MUST display every assistant reply in the conversation pane upon arrival.
- **FR-008**: The conversation pane MUST scroll so the most recent message is visible whenever a new message (user or assistant) is added.
- **FR-009**: While awaiting an assistant reply, the widget MUST show a visible loading indicator in the conversation pane.
- **FR-010**: When the assistant reply's route value indicates the conversation has been routed to a human, the widget MUST surface the human-follow-up reference (e.g., a small "Ticket #…" pill) at the bottom of the conversation pane.

**Defensive parsing**

- **FR-011**: The widget MUST treat the assistant reply's required fields (the reply text and the routing label) as mandatory and treat all other fields (citations, used tools, ticket reference) as optional with safe defaults.
- **FR-012**: The widget MUST NOT crash or display an error state if optional reply fields are missing, null, or unexpectedly typed.

**Failure handling**

- **FR-013**: When the platform refuses the message with an authentication failure (HTTP 401), the widget MUST display "Session expired, please reload" and MUST disable the input. The widget MUST NOT attempt to re-acquire a session credential automatically.
- **FR-014**: When the platform returns any other error response or the network call fails outright, the widget MUST display an error banner with a "Retry" affordance.
- **FR-015**: Clicking Retry MUST re-send the most recently failed message exactly once (per click); a successful retry MUST result in a single user message and a single assistant reply in the conversation pane (no duplicated user message from the failed attempt).
- **FR-016**: A retried-then-succeeded message MUST appear in the conversation history as one user-message + one assistant-reply pair, not as two attempts.
- **FR-017**: Failure indicators MUST never expose raw HTTP codes, raw response bodies, stack traces, or platform identifiers to the visitor.

**Privacy and storage**

- **FR-018**: The widget MUST hold all conversation content (sent messages, received replies) in volatile memory only; no chat content MUST be written to cookies, localStorage, sessionStorage, IndexedDB, or any other browser-persisted store.
- **FR-019**: Reloading the host page MUST reset the conversation to empty and re-trigger a fresh session-credential exchange.

**Scope guards**

- **FR-020**: The widget MUST NOT accept file attachments, audio uploads, or any input other than plain text in this phase.
- **FR-021**: The widget MUST NOT apply tenant-specified theming, colors, or branding in this phase; styling is fixed for v1 of the chat UI.

### Key Entities

- **Conversation Message**: an exchange entry shown in the conversation pane. Either a user-sent message (text only) or an assistant reply (text + optional routing metadata such as a human-follow-up reference). Lives only in browser memory; never persisted.
- **Visitor Session**: the chat-scope correlation between the widget and the platform for this page-load. Identified by the session credential obtained at widget boot (feature 001). Ends when the page unloads.
- **Failure Indicator**: a visible UI element shown when the platform request fails. Two flavors: a session-expired prompt (terminal — no retry) and an error banner (retryable). Both are non-technical and visitor-safe.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When the platform reply is ready, the visitor sees the reply in the conversation pane within 200 milliseconds of the network response arriving (i.e., rendering overhead is bounded; not a constraint on platform latency).
- **SC-002**: Across a sample of 100 synthetic platform replies in which one or more optional fields (citations, used tools, ticket reference) are missing, null, or of unexpected type, the widget renders the reply text without showing any error indicator in 100% of cases (verifies FR-011/FR-012).
- **SC-003**: Across a sample of 50 simulated platform errors (mix of 401, 500, network-drop), the widget surfaces the correct visitor-facing affordance (reload prompt for 401, retry banner for the rest) in 100% of cases, and never exposes a raw HTTP code, stack trace, or response body (verifies FR-013/FR-014/FR-017).
- **SC-004**: A visitor whose retry succeeds sees exactly one user message and one assistant reply for the retried exchange — never duplicates (verifies FR-015/FR-016).
- **SC-005**: Browser dev-tools inspection after any conversation of any length shows zero chat-content, session-credential, or session-identifier values in cookies, localStorage, sessionStorage, or IndexedDB at any point during or after the session (verifies FR-018, satisfies Constitution Principle IV defense-in-depth).
- **SC-006**: When a new message is added to the conversation pane, the pane auto-scrolls so the message is fully in view within 200 milliseconds (verifies FR-008).
- **SC-007**: A visitor can read every prior message in the current session by scrolling within the conversation pane (the pane retains a complete in-session history until reload).

## Assumptions

- **Builds directly on feature 001 (Widget Token Exchange).** The widget is mounted, has reached chat-ready state, and holds a valid bearer session credential before any user story in this feature begins. Acquisition failures are feature 001's responsibility, not this feature's.
- **The platform's chat endpoint exists** and accepts a JSON body with the visitor's message and session correlation, and returns a reply payload whose required fields (the reply text and a routing label) are stable per the team contract. Other fields may be added later without breaking the widget (FR-011 covers this).
- **Maximum message length is 4000 characters.** Standard chat-input convention; configurable later if a tenant requests larger.
- **The widget does not stream replies in this phase.** Each reply arrives as one complete payload. Streaming is a separate, future feature.
- **Conversation history is per-page-load, not per-visitor.** A visitor who reloads, navigates away, or reopens the page starts fresh. Persistence across page-loads is a deliberate non-feature for the privacy posture in US3.
- **No tenant-controlled theming in v1.** The chat UI uses a single fixed visual style; FR-021 makes this explicit, and theme controls land alongside the admin UI work (Phase 4 in Amer's plan).
- **No multi-language UI in v1.** Static UI strings ("Send", "Session expired, please reload", "Retry", "Ticket #…") are in English; localization is a later concern.
- **Single visitor session per iframe.** The widget does not multiplex multiple visitor sessions; each iframe instance is one conversation.

## Out of Scope (mirrored from input)

- Tenant-controlled theme / colors / branding (Phase 4 once admin UI lets tenants set them).
- File uploads, voice messages, image attachments — never, not in MVP.
- Streamed (token-by-token) reply rendering.
- Cross-page-load conversation persistence.
- Localization / RTL / accessibility audit beyond keyboard-baseline.
- Per-message reactions, edits, deletes, copy-link affordances.
