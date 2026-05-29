// Owner: Amer
// Floating chat-bubble launcher. Pure presentation — main.tsx wires the
// click handler. US4 (T105) will flip the orchestrator to render this
// when state.open === false; Phase 2 doesn't mount it yet.

import React from "react";

interface BubbleProps {
  onClick: () => void;
  label?: string;
  themeColor?: string;
}

export function Bubble({
  onClick,
  label = "Open chat",
  themeColor,
}: BubbleProps): JSX.Element {
  return (
    <button
      type="button"
      className="widget-bubble"
      data-testid="widget-bubble"
      aria-label={label}
      onClick={onClick}
      style={themeColor ? { background: themeColor } : undefined}
    >
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    </button>
  );
}
