// Owner: Amer
// Types matching:
//   specs/001-widget-token-exchange/contracts/widget-token-endpoint.md
//   specs/001-widget-token-exchange/contracts/widget-loader-postmessage.md
//   specs/002-widget-chat-ui/data-model.md
//   specs/002-widget-chat-ui/contracts/chat-endpoint-consumer.md

export interface WidgetTokenResponse {
  token: string;
  expires_in: number;
  session_id: string;
}

export interface HostOriginMessage {
  type: "concierge.widget.host_origin";
  origin: string;
}

export interface ReadyMessage {
  type: "concierge.widget.ready";
}

export type WidgetMessage = HostOriginMessage | ReadyMessage;

// --- Phase 2 chat UI ---

export interface Citation {
  title?: string;
  url?: string;
  [extra: string]: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  ticket_id?: string | null;
  citations?: Citation[] | unknown[];
  route?: string;
  used_tools?: string[];
}

export interface AgentConfig {
  greeting: string;
  chips: string[];
  _placeholder?: boolean;
}

// Defensive-parse shape of the /chat success response. `answer` and `route`
// are required; the rest default to safe values inside api.ts.
export interface ChatResponse {
  answer: string;
  route: string;
  used_tools: string[];
  citations: unknown[];
  ticket_id: string | null;
}

export type ChatStatus = "idle" | "sending" | "error" | "expired";

export type ChatErrorKind = "network" | "server";
