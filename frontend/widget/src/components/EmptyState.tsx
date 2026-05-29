// Owner: Amer
// First-open greeting card. Phase 2 keeps the visual identical to today's
// always-open empty card; US1 (T047) will pass a tenant-specific greeting.

import React from "react";

interface EmptyStateProps {
  title?: string;
  subtitle?: string;
  placeholder?: boolean;
}

export function EmptyState({
  title = "How can we help?",
  subtitle = "Ask anything about our products, pricing, or account.",
  placeholder = false,
}: EmptyStateProps): JSX.Element {
  return (
    <div className="empty-state" data-testid="empty-state">
      <div className="empty-state__icon" aria-hidden="true">
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </div>
      <div className="empty-state__title">{title}</div>
      <div className="empty-state__sub">{subtitle}</div>
      {placeholder && (
        <div
          className="empty-state__placeholder-note"
          data-testid="empty-state-placeholder-note"
        >
          (sample greeting)
        </div>
      )}
    </div>
  );
}
