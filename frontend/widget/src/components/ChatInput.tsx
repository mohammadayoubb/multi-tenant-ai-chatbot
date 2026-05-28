// Owner: Amer
// Controlled textarea with Enter-to-send / Shift+Enter newline.

import React, { useState } from "react";

const MAX_LENGTH = 4000;

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
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    tryDispatch();
  }

  return (
    <div className="chat-input">
      <div className="chat-input__panel">
        <textarea
          className="chat-input__field"
          data-testid="chat-input-textarea"
          placeholder="Ask about pricing, product fit, or next steps"
          maxLength={MAX_LENGTH}
          rows={3}
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        <div className="chat-input__footer">
          <div className="chat-input__meta">
            <span className="chat-input__hint">
              Enter to send. Shift+Enter for a new line.
            </span>
            <span className="chat-input__count">{value.length}/{MAX_LENGTH}</span>
          </div>

          <button
            type="button"
            className="chat-input__send"
            data-testid="chat-input-send"
            disabled={disabled || value.trim().length === 0}
            onClick={tryDispatch}
          >
            <span>Send</span>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M22 2 11 13" />
              <path d="m22 2-7 20-4-9-9-4Z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
