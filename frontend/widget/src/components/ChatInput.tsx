// Owner: Amer
// Chat input — controlled textarea with Enter-to-send / Shift+Enter newline.
//
// Per spec.md FR-002 / FR-003 / FR-018:
//   - Enter submits (no modifiers); Shift+Enter inserts a newline.
//   - Empty / whitespace-only input is ignored.
//   - Value lives in component state only — never written to browser storage.

import React, { useState } from "react";

const MAX_LENGTH = 4000; // per spec Assumptions.

interface ChatInputProps {
  disabled: boolean;
  onSubmit: (text: string) => void;
}

export function ChatInput({ disabled, onSubmit }: ChatInputProps): JSX.Element {
  const [value, setValue] = useState<string>("");

  function tryDispatch(): void {
    if (disabled) return;
    const trimmed = value.trim();
    if (trimmed.length === 0) return;
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
        maxLength={MAX_LENGTH}
        rows={2}
        value={value}
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button
        type="button"
        className="chat-input__send"
        data-testid="chat-input-send"
        disabled={disabled || value.trim().length === 0}
        onClick={tryDispatch}
      >
        Send
      </button>
    </div>
  );
}
