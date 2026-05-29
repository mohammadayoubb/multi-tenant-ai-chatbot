// Owner: Amer
// Scrollable panel shell. US4 (T108) wraps children in a FocusTrap and
// presents the dialog semantics: role="dialog", aria-modal="true",
// aria-labelledby pointing at the header title. The message-list slot
// is a polite live region (T112) so assistive tech announces new
// assistant messages without stealing focus.

import React from "react";
import { FocusTrap } from "../a11y/FocusTrap";

interface PanelProps {
  onClose?: () => void;
  themeColor?: string;
  children: React.ReactNode;
}

const TITLE_ID = "concierge-widget-title";

export function Panel({
  onClose,
  themeColor,
  children,
}: PanelProps): JSX.Element {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={TITLE_ID}
      className="widget-panel"
      data-testid="widget-panel"
    >
      <FocusTrap onEscape={onClose}>
        <header
          className="chat-header"
          style={themeColor ? { background: themeColor } : undefined}
        >
          <div className="chat-header__avatar" aria-hidden="true">
            C
          </div>
          <div className="chat-header__meta">
            <span className="chat-header__title" id={TITLE_ID}>
              Concierge
            </span>
            <span className="chat-header__status">
              <span className="chat-header__dot" aria-hidden="true" />
              Online — typically replies instantly
            </span>
          </div>
          {onClose && (
            <button
              type="button"
              className="chat-header__close"
              data-testid="widget-close"
              aria-label="Close chat"
              onClick={onClose}
            >
              ×
            </button>
          )}
        </header>
        <div className="chat-pane">{children}</div>
      </FocusTrap>
    </div>
  );
}
