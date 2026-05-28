// Owner: Amer
// ChatPane owns the chat state machine and conversation rendering.
//
// Per spec.md FR-018 / FR-019 / Constitution Principle IV:
//   - All conversation state lives in component-local memory only.
//   - No localStorage, sessionStorage, cookies, or IndexedDB writes.
//   - On iframe unmount, the conversation is garbage-collected.

import React, { useEffect, useRef, useState } from "react";
import { ApiError, sendChatMessage } from "../api";
import type {
  ChatErrorKind,
  ChatMessage,
  ChatResponse,
  ChatStatus,
} from "../types";
import { ChatHeader } from "./ChatHeader";
import { ChatInput } from "./ChatInput";

const defaultBackendUrl = (): string => window.location.origin;
const KNOWN_ROUTES = new Set(["workflow", "agent", "blocked", "escalate"]);

interface ChatPaneProps {
  backendUrl?: string;
}

let _idCounter = 0;
function nextId(): string {
  _idCounter += 1;
  return `msg-${_idCounter}`;
}

function EmptyState(): JSX.Element {
  return (
    <div className="empty-state" aria-hidden="true">
      <div className="empty-state__icon">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </div>
      <div className="empty-state__title">Start with a clear question</div>
      <div className="empty-state__sub">
        The assistant is best at product guidance, pricing context, and next-step
        follow-up.
      </div>
      <div className="empty-state__chips">
        <span className="empty-state__chip">Compare plans</span>
        <span className="empty-state__chip">Request pricing help</span>
        <span className="empty-state__chip">Talk to a person</span>
      </div>
    </div>
  );
}

export function ChatPane({ backendUrl }: ChatPaneProps): JSX.Element {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const [errorInfo, setErrorInfo] = useState<ChatErrorKind | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const resolvedBackendUrl = backendUrl ?? defaultBackendUrl();

  useEffect(() => {
    const el = listRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, status]);

  function commitReply(reply: ChatResponse): void {
    if (!KNOWN_ROUTES.has(reply.route)) {
      console.warn("[concierge.widget] unknown route value", reply.route);
    }

    const assistantMsg: ChatMessage = {
      id: nextId(),
      role: "assistant",
      content: reply.answer,
      ticket_id:
        reply.route === "escalate" && reply.ticket_id ? reply.ticket_id : null,
    };

    setMessages((current) => [...current, assistantMsg]);
    setStatus("idle");
    setPendingPrompt(null);
  }

  async function dispatch(text: string): Promise<void> {
    if (status === "sending" || status === "expired") return;

    const userMsg: ChatMessage = {
      id: nextId(),
      role: "user",
      content: text,
    };
    setMessages((current) => [...current, userMsg]);
    setPendingPrompt(text);
    setStatus("sending");
    setErrorInfo(null);

    try {
      const reply = await sendChatMessage(resolvedBackendUrl, text);
      commitReply(reply);
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

    setStatus("sending");
    setErrorInfo(null);

    try {
      const reply = await sendChatMessage(resolvedBackendUrl, pendingPrompt);
      commitReply(reply);
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
      <ChatHeader isBusy={status === "sending"} />

      <div className="chat-pane">
        <div ref={listRef} className="message-list" data-testid="message-list">
          {messages.length === 0 && status !== "sending" && <EmptyState />}

          {messages.map((m) => (
            <div
              key={m.id}
              className={`message-cluster message-cluster--${m.role}`}
            >
              <span className="message-cluster__label">
                {m.role === "user" ? "You" : "Concierge"}
              </span>
              <div
                data-testid={
                  m.role === "user"
                    ? "message-bubble--user"
                    : "message-bubble--assistant"
                }
                className={`message-bubble message-bubble--${m.role}`}
              >
                {m.content}
              </div>
            </div>
          ))}

          {status === "sending" && (
            <div className="message-cluster message-cluster--assistant">
              <span className="message-cluster__label">Concierge</span>
              <div className="message-loading" data-testid="loading-indicator">
                <span />
              </div>
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
            <span>
              {errorInfo === "network"
                ? "Couldn't reach the assistant."
                : "The assistant is having trouble responding."}
            </span>
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
