# Phase 1: Data Model

Two transient data shapes and one state-machine enum. Nothing is persisted; nothing touches a database. The widget's entire data lifecycle is bounded by the iframe's window.

## 1. `ChatMessage` (transient — React state)

A single entry in the conversation pane.

```ts
interface ChatMessage {
  id: string;                       // client-side UUID; for React keys only
  role: "user" | "assistant";
  content: string;
  ticket_id?: string | null;        // present only on assistant messages with route === "escalate"
}
```

**Lifecycle**:
- Created in component state when the visitor sends (`role: "user"`) or when the platform replies (`role: "assistant"`).
- Lives in the `ChatPane` `useState<ChatMessage[]>` array.
- Discarded when the iframe unmounts (page reload, tab close) — never persisted.

**Validation rules (client-side)**:

| Rule | Source |
|---|---|
| `content` for outgoing user messages must be non-empty after `.trim()`. | FR-003 |
| `content` for outgoing user messages must be ≤ 4000 characters. | Assumptions |
| `role` is exactly `"user"` or `"assistant"`. | Internal — no other roles exist in v1. |
| `ticket_id` is only set when the assistant reply's `route === "escalate"` AND the response includes a non-empty `ticket_id`. | FR-010, edge case "Reply containing route `escalate` but no `ticket_id`" |

## 2. `ChatResponse` consumer shape (defensive parse of Nasser's `POST /chat` reply)

The widget's view of what comes back from `/chat`. The platform contract (CONTRACT.md §2.9) lets fields evolve; the widget locks in safe defaults so future field additions don't break it.

```ts
interface ChatResponse {
  // Required — widget shows an error indicator if either is missing.
  answer: string;
  route: string;                    // "workflow" | "agent" | "blocked" | "escalate" — widget treats unknowns as "agent" rendering.

  // Optional — widget defaults to safe values per FR-011 / FR-012.
  used_tools?: string[];
  citations?: unknown[];
  ticket_id?: string | null;
}
```

**Defensive-parse rules** (executed in `api.ts` `sendChatMessage`):

| Field | If missing / wrong type | Source |
|---|---|---|
| `answer` (string) | Treat the whole response as malformed → throw → triggers retry banner. | FR-007 + FR-011 |
| `route` (string) | Treat as malformed (same as above). | FR-011 |
| `used_tools` | Default `[]`. | FR-011, FR-012 |
| `citations` | Default `[]`. (Field is intentionally `unknown[]` — we don't render citations in v1, just pass them through unchanged.) | FR-011, FR-012 |
| `ticket_id` | Default `null`. Pill suppressed if `null` or empty string even when `route === "escalate"`. | Edge case "Reply containing route `escalate` but no `ticket_id`" |
| Unknown extra fields | Ignored. | Forward-compat by Principle VII. |

## 3. `ChatStatus` state machine

The four states `ChatPane` cycles through. The state name is the React `useState<ChatStatus>` value.

```ts
type ChatStatus = "idle" | "sending" | "error" | "expired";
```

### State transitions

```
                  ┌──────────────────────────────────┐
                  │                                  ▼
   [idle] ─send─▶ [sending] ─reply ok──▶ [idle] (history grows)
                     │
                     ├─401──────────────▶ [expired]   (terminal)
                     │
                     └─other failure────▶ [error]
                                            │
                                            └─retry──▶ [sending] (loops back)
```

**Per-state invariants**:

| State | Send affordance | Retry affordance | Input enabled | Banner |
|---|---|---|---|---|
| `idle` | enabled | n/a | yes | none |
| `sending` | disabled (FR-005) | n/a | yes (visitor may type next message) | loading indicator in pane |
| `error` | disabled until retry resolves | visible (FR-014) | yes | retry banner |
| `expired` | disabled (FR-013) | NOT shown | NO (FR-013) | "Session expired, please reload" |

**State invariants the implementation MUST preserve**:

- `expired` is terminal. The only exit is page reload (which re-runs feature 001 and re-mounts the iframe). No code path transitions out of `expired`.
- At most one in-flight request at a time (FR-005). The `sending` state is mutually exclusive — `ChatPane` MUST guard against entering `sending` again while already in it (e.g., rapid Enter presses).
- The retry flow restores the last failed user message exactly once per click (FR-015). After a successful retry, the conversation pane contains one user-message + one assistant-reply — never two user-messages from the same logical send (FR-016).

## 4. Side data carried in `ChatPane` state

Beyond `messages: ChatMessage[]` and `status: ChatStatus`, the component holds:

| Field | Type | Purpose |
|---|---|---|
| `pendingPrompt` | `string \| null` | The text of the message currently in flight or queued for retry. Cleared on successful reply. |
| `errorInfo` | `{ kind: "network" \| "server" } \| null` | Used only to format the retry banner; never shown to the visitor with raw codes (FR-017). |

That is the entire data model.

## Cross-references

| Reference | Where |
|---|---|
| `POST /chat` contract | CONTRACT.md §2.9 |
| Token storage discipline (token in module-scope memory only) | feature 001 spec.md FR-011, FR-012; this feature inherits |
| Canonical ID names (`session_id`, never `chatId`) | CONTRACT.md §6 |
