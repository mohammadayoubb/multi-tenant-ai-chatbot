// Owner: Amer
// Single chat bubble. Renders user/assistant content, optional citation
// chips on assistant replies, and the inline ticket pill when route is
// escalate. Citation rendering is a no-op until US1 (T048) populates it.

import React from "react";
import type { ChatMessage, Citation } from "../types";

interface MessageProps {
  message: ChatMessage;
}

function isUrl(value: unknown): value is string {
  return typeof value === "string" && /^https?:\/\//i.test(value);
}

function asCitation(c: unknown): Citation | null {
  if (c === null || typeof c !== "object") return null;
  return c as Citation;
}

export function Message({ message }: MessageProps): JSX.Element {
  const isUser = message.role === "user";
  const citations = (message.citations ?? []) as unknown[];
  const showTicket =
    message.role === "assistant" &&
    message.route === "escalate" &&
    typeof message.ticket_id === "string" &&
    message.ticket_id.length > 0;

  return (
    <>
      <div
        data-testid={
          isUser ? "message-bubble--user" : "message-bubble--assistant"
        }
        className={`message-bubble message-bubble--${message.role}`}
      >
        {message.content}
      </div>
      {!isUser && citations.length > 0 && (
        <div
          className="citation-chips"
          data-testid="citation-chips"
          aria-label="Sources"
        >
          {citations.map((raw, idx) => {
            const c = asCitation(raw);
            if (c === null) return null;
            const title =
              typeof c.title === "string" && c.title.length > 0
                ? c.title
                : "Source";
            if (isUrl(c.url)) {
              return (
                <a
                  key={idx}
                  className="citation-chip"
                  data-testid="citation-chip"
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {title}
                </a>
              );
            }
            return (
              <span
                key={idx}
                className="citation-chip"
                data-testid="citation-chip"
              >
                {title}
              </span>
            );
          })}
        </div>
      )}
      {showTicket && (
        <span className="ticket-pill" data-testid="ticket-pill">
          Ticket #{message.ticket_id}
        </span>
      )}
    </>
  );
}
