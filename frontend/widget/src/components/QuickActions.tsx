// Owner: Amer
// Quick-action chip row. Renders nothing when the chip list is empty so
// callers can pass `agentConfig.chips` directly without guarding.

import React from "react";

interface QuickActionsProps {
  chips: string[];
  onPick: (text: string) => void;
  disabled?: boolean;
}

export function QuickActions({
  chips,
  onPick,
  disabled = false,
}: QuickActionsProps): JSX.Element | null {
  if (chips.length === 0) return null;
  return (
    <div
      className="quick-actions"
      data-testid="quick-actions"
      role="group"
      aria-label="Quick actions"
    >
      {chips.map((chip) => (
        <button
          key={chip}
          type="button"
          className="quick-action-chip"
          data-testid="quick-action-chip"
          disabled={disabled}
          onClick={() => onPick(chip)}
        >
          {chip}
        </button>
      ))}
    </div>
  );
}
