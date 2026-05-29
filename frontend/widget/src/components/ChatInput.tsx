// Owner: Amer
// Chat input — controlled textarea with Enter-to-send / Shift+Enter newline.
//
// Per spec.md FR-002 / FR-003 / FR-018:
//   - Enter submits (no modifiers); Shift+Enter inserts a newline.
//   - Empty / whitespace-only input is ignored.
//   - Value lives in component state only — never written to browser storage.

import React, { useState } from "react";

// US1 / T050: hard cap on outgoing visitor input. The counter appears once
// the visitor is within COUNTER_VISIBLE_AT chars of the cap; sends above the
// cap are rejected client-side.
const MAX_LENGTH = 2000;
const COUNTER_VISIBLE_AT = MAX_LENGTH - 200;

interface ChatInputProps {
  disabled: boolean;
  onSubmit: (text: string) => void;
}

export function ChatInput({ disabled, onSubmit }: ChatInputProps): JSX.Element {
  const [value, setValue] = useState<string>("");
  const length = value.length;
  const overCap = length > MAX_LENGTH;
  const showCounter = length >= COUNTER_VISIBLE_AT;

  function tryDispatch(): void {
    if (disabled) return;
    const trimmed = value.trim();
    if (trimmed.length === 0) return;
    if (trimmed.length > MAX_LENGTH) return;
    onSubmit(trimmed);
    setValue("");
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>): void {
    // Shift+Enter = newline (default browser behavior — do nothing).
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    tryDispatch();
  }

  return (
    <div className="chat-input">
      <textarea
        className="chat-input__field"
        data-testid="chat-input-textarea"
        placeholder="Ask a question..."
        rows={2}
        value={value}
        disabled={disabled}
        aria-invalid={overCap || undefined}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      {showCounter && (
        <div
          className={`chat-input__counter${overCap ? " chat-input__counter--over" : ""}`}
          data-testid="chat-input-counter"
          aria-live="polite"
        >
          {length} / {MAX_LENGTH}
        </div>
      )}
      <button
        type="button"
        className="chat-input__send"
        data-testid="chat-input-send"
        disabled={disabled || value.trim().length === 0 || overCap}
        onClick={tryDispatch}
      >
        Send
      </button>
    </div>
  );
}
