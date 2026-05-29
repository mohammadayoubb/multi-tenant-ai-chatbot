// Owner: Amer
// Inline status banner for the four ChatStatus values. The error banner is
// the only one that surfaces an action (retry); main.tsx wires it.

import React from "react";
import type { ChatStatus } from "../types";

interface StatusBannerProps {
  status: ChatStatus;
  onRetry?: () => void;
}

export function StatusBanner({
  status,
  onRetry,
}: StatusBannerProps): JSX.Element | null {
  if (status === "expired") {
    return (
      <div
        className="status-banner status-banner--expired"
        role="status"
        data-testid="status-banner-expired"
      >
        Session expired, please reload
      </div>
    );
  }
  if (status === "error") {
    return (
      <div
        className="status-banner status-banner--error"
        role="alert"
        data-testid="status-banner-error"
      >
        <span>Couldn&apos;t reach the assistant.</span>
        {onRetry && (
          <button
            type="button"
            data-testid="retry-button"
            onClick={onRetry}
          >
            Retry
          </button>
        )}
      </div>
    );
  }
  return null;
}
