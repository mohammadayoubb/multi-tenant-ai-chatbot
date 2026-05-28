// Owner: Amer
// ChatPane — owns the chat state machine and renders the conversation.
//
// Per spec.md FR-018 / FR-019 / Constitution Principle IV:
//   - All conversation state lives in React useState (component-local).
//   - No localStorage, sessionStorage, cookies, or IndexedDB writes anywhere.
//   - On iframe unmount, the entire conversation is garbage-collected.
//
// State machine (see specs/002-widget-chat-ui/data-model.md §3):
//   idle ──send──▶ sending ──ok──▶ idle (history grows)
//                     │
//                     ├─401────▶ expired   (terminal)
//                     └─other──▶ error
//                                  │
//                                  └─retry──▶ sending (loops)

import React, { useEffect, useRef, useState } from "react";
import { ApiError, sendChatMessage } from "../api";
import type { ChatErrorKind, ChatMessage, ChatStatus } from "../types";
import { ChatInput } from "./ChatInput";

const defaultBackendUrl = (): string => window.location.origin;

interface ChatPaneProps {
  backendUrl?: string;
}

let _idCounter = 0;
function nextId(): string {
  _idCounter += 1;
  return `msg-${_idCounter}`;
}

export function ChatPane({ backendUrl }: ChatPaneProps): JSX.Element {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const [errorInfo, setErrorInfo] = useState<ChatErrorKind | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const resolvedBackendUrl = backendUrl ?? defaultBackendUrl();

  // Auto-scroll on new message (FR-008 / SC-006).
  useEffect(() => {
    const el = listRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, status]);

  async function dispatch(text: string): Promise<void> {
    // FR-005 single-in-flight guard.
    if (status === "sending" || status === "expired") return;

    // Append the user bubble before the call (FR-006).
    const userMsg: ChatMessage = {
      id: nextId(),
      role: "user",
      content: text,
    };
    setMessages((m) => [...m, userMsg]);
    setPendingPrompt(text);
    setStatus("sending");
    setErrorInfo(null);

    try {
      const reply = await sendChatMessage(resolvedBackendUrl, text);
      if (reply.route !== "workflow" && reply.route !== "agent" &&
          reply.route !== "blocked" && reply.route !== "escalate") {
        // Unknown route — render normally per contracts/chat-endpoint-consumer.md.
        console.warn("[concierge.widget] unknown route value", reply.route);
      }
      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: reply.answer,
        ticket_id:
          reply.route === "escalate" && reply.ticket_id ? reply.ticket_id : null,
      };
      setMessages((m) => [...m, assistantMsg]);
      setStatus("idle");
      setPendingPrompt(null);
    } catch (err) {
      if (err instanceof ApiError && err.kind === "expired") {
        setStatus("expired");
      } else if (err instanceof ApiError) {
        setErrorInfo(err.kind);
        setStatus("error");
      } else {
        setErrorInfo("server");
        setStatus("error");
      }
    }
  }

  async function retryLast(): Promise<void> {
    if (pendingPrompt === null || status !== "error") return;
    // Per FR-015 / FR-016: do NOT append a second user bubble. Just re-dispatch
    // by sending the same prompt directly to the server and appending the
    // assistant reply when it lands.
    setStatus("sending");
    setErrorInfo(null);
    try {
      const reply = await sendChatMessage(resolvedBackendUrl, pendingPrompt);
      if (reply.route !== "workflow" && reply.route !== "agent" &&
          reply.route !== "blocked" && reply.route !== "escalate") {
        console.warn("[concierge.widget] unknown route value", reply.route);
      }
      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: reply.answer,
        ticket_id:
          reply.route === "escalate" && reply.ticket_id ? reply.ticket_id : null,
      };
      setMessages((m) => [...m, assistantMsg]);
      setStatus("idle");
      setPendingPrompt(null);
    } catch (err) {
      if (err instanceof ApiError && err.kind === "expired") {
        setStatus("expired");
      } else if (err instanceof ApiError) {
        setErrorInfo(err.kind);
        setStatus("error");
      } else {
        setErrorInfo("server");
        setStatus("error");
      }
    }
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const showTicketPill = lastAssistant?.ticket_id ? lastAssistant.ticket_id : null;

  return (
    <>
      <header className="chat-header">
        <div className="chat-header__avatar" aria-hidden="true">
          C
        </div>
        <div className="chat-header__meta">
          <span className="chat-header__title">Concierge</span>
          <span className="chat-header__status">
            <span className="chat-header__dot" aria-hidden="true" />
            Online — typically replies instantly
          </span>
        </div>
      </header>

      <div className="chat-pane">
        <div
          ref={listRef}
          className="message-list"
          data-testid="message-list"
        >
          {messages.length === 0 && status !== "sending" && (
            <div className="empty-state" aria-hidden="true">
              <div className="empty-state__icon">
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
              <div className="empty-state__title">How can we help?</div>
              <div className="empty-state__sub">
                Ask anything about our products, pricing, or account.
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div
              key={m.id}
              data-testid={
                m.role === "user" ? "message-bubble--user" : "message-bubble--assistant"
              }
              className={`message-bubble message-bubble--${m.role}`}
            >
              {m.content}
            </div>
          ))}
          {status === "sending" && (
            <div className="message-loading" data-testid="loading-indicator">
              <span />
            </div>
          )}
          {showTicketPill && (
            <span className="ticket-pill" data-testid="ticket-pill">
              Ticket #{showTicketPill}
            </span>
          )}
        </div>

        {status === "expired" && (
          <div className="status-banner status-banner--expired" role="status">
            Session expired, please reload
          </div>
        )}

        {status === "error" && (
          <div className="status-banner status-banner--error" role="alert">
            <span>Couldn&apos;t reach the assistant.</span>
            <button
              type="button"
              data-testid="retry-button"
              onClick={() => {
                void retryLast();
              }}
            >
              Retry
            </button>
          </div>
        )}

        <ChatInput
          disabled={status === "sending" || status === "expired"}
          onSubmit={(text) => {
            void dispatch(text);
          }}
        />
      </div>
    </>
  );
}
