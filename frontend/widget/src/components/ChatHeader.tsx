// Owner: Amer
// Header for the embedded concierge widget.

import React from "react";

interface ChatHeaderProps {
  isBusy: boolean;
}

export function ChatHeader({ isBusy }: ChatHeaderProps): JSX.Element {
  return (
    <header className="chat-header">
      <div className="chat-header__brand">
        <div className="chat-header__avatar" aria-hidden="true">
          C
        </div>
        <div className="chat-header__meta">
          <span className="chat-header__eyebrow">Visitor support desk</span>
          <span className="chat-header__title">Concierge</span>
          <span className="chat-header__status">
            <span className="chat-header__dot" aria-hidden="true" />
            {isBusy ? "Replying now" : "Online - replies in seconds"}
          </span>
        </div>
      </div>

      <div className="chat-header__trust">Secure session</div>
    </header>
  );
}
