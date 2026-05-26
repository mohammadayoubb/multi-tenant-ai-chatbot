// Owner: Amer
// Types matching specs/001-widget-token-exchange/contracts/widget-token-endpoint.md
//                and contracts/widget-loader-postmessage.md

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
