// Owner: Amer
// Pure-function state machine for the widget chat surface.
//
// The reducer + initialState are EXPORTED for unit testing (T027). The
// `useChatReducer` hook wraps them with the impure send / retry flows that
// call into api.ts. Phase 2 extracts this from the old ChatPane; later
// phases (US1 chips, US4 bubble) layer on top without touching reducer.ts.

import { useCallback, useReducer } from "react";
import { ApiError, sendChatMessage } from "../api";
import type {
  ChatErrorKind,
  ChatMessage,
  ChatResponse,
  ChatStatus,
} from "../types";

export interface ChatState {
  open: boolean;
  messages: ChatMessage[];
  status: ChatStatus;
  pendingPrompt: string | null;
  errorKind: ChatErrorKind | null;
}

export type ChatAction =
  | { type: "OPEN" }
  | { type: "CLOSE" }
  | { type: "SEND_START"; userMessage: ChatMessage; prompt: string }
  | { type: "SEND_OK"; assistantMessage: ChatMessage }
  | { type: "SEND_ERROR"; kind: ChatErrorKind }
  | { type: "SESSION_EXPIRED" }
  | { type: "RETRY_LAST" }
  | { type: "RESET" };

// US4 (T105) starts the orchestrator with the bubble visible — the panel
// only opens on user interaction. The OPEN/CLOSE transitions drive both
// sides of that flip.
export const initialState: ChatState = {
  open: false,
  messages: [],
  status: "idle",
  pendingPrompt: null,
  errorKind: null,
};

export function reducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "OPEN":
      return { ...state, open: true };
    case "CLOSE":
      return { ...state, open: false };
    case "SEND_START":
      // Single-in-flight guard: ignore SEND_START while sending or expired.
      if (state.status === "sending" || state.status === "expired") {
        return state;
      }
      return {
        ...state,
        messages: [...state.messages, action.userMessage],
        status: "sending",
        pendingPrompt: action.prompt,
        errorKind: null,
      };
    case "SEND_OK":
      return {
        ...state,
        messages: [...state.messages, action.assistantMessage],
        status: "idle",
        pendingPrompt: null,
        errorKind: null,
      };
    case "SEND_ERROR":
      return {
        ...state,
        status: "error",
        errorKind: action.kind,
      };
    case "SESSION_EXPIRED":
      return {
        ...state,
        status: "expired",
        pendingPrompt: null,
      };
    case "RETRY_LAST":
      if (state.pendingPrompt === null || state.status !== "error") {
        return state;
      }
      return {
        ...state,
        status: "sending",
        errorKind: null,
      };
    case "RESET":
      return { ...initialState, open: state.open };
    default:
      return state;
  }
}

let _idCounter = 0;
function nextId(): string {
  _idCounter += 1;
  return `msg-${_idCounter}`;
}

function buildAssistantMessage(reply: ChatResponse): ChatMessage {
  return {
    id: nextId(),
    role: "assistant",
    content: reply.answer,
    ticket_id:
      reply.route === "escalate" && reply.ticket_id ? reply.ticket_id : null,
    citations: Array.isArray(reply.citations) ? reply.citations : [],
    route: reply.route,
  };
}

export interface UseChatReducerResult {
  state: ChatState;
  open: () => void;
  close: () => void;
  send: (text: string) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
}

export function useChatReducer(
  backendUrl: string,
  initialOpen: boolean = false
): UseChatReducerResult {
  const [state, dispatch] = useReducer(reducer, initialState, (s) => ({
    ...s,
    open: initialOpen,
  }));

  const open = useCallback(() => dispatch({ type: "OPEN" }), []);
  const close = useCallback(() => dispatch({ type: "CLOSE" }), []);
  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  const handleApiError = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.kind === "expired") {
      dispatch({ type: "SESSION_EXPIRED" });
      return;
    }
    if (err instanceof ApiError) {
      dispatch({ type: "SEND_ERROR", kind: err.kind });
      return;
    }
    dispatch({ type: "SEND_ERROR", kind: "server" });
  }, []);

  const send = useCallback(
    async (text: string): Promise<void> => {
      if (state.status === "sending" || state.status === "expired") return;
      const userMessage: ChatMessage = {
        id: nextId(),
        role: "user",
        content: text,
      };
      dispatch({ type: "SEND_START", userMessage, prompt: text });
      try {
        const reply = await sendChatMessage(backendUrl, text);
        dispatch({
          type: "SEND_OK",
          assistantMessage: buildAssistantMessage(reply),
        });
      } catch (err) {
        handleApiError(err);
      }
    },
    [backendUrl, state.status, handleApiError]
  );

  const retry = useCallback(async (): Promise<void> => {
    if (state.pendingPrompt === null || state.status !== "error") return;
    const prompt = state.pendingPrompt;
    dispatch({ type: "RETRY_LAST" });
    try {
      const reply = await sendChatMessage(backendUrl, prompt);
      dispatch({
        type: "SEND_OK",
        assistantMessage: buildAssistantMessage(reply),
      });
    } catch (err) {
      handleApiError(err);
    }
  }, [backendUrl, state.pendingPrompt, state.status, handleApiError]);

  return { state, open, close, send, retry, reset };
}
