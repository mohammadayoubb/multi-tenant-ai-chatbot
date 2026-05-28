// Owner: Amer
// Shell used by boot-time widget states such as loading and unavailable.

import React from "react";

type WidgetShellTone = "neutral" | "warning";

interface WidgetShellStateProps {
  eyebrow: string;
  title: string;
  body: string;
  tone?: WidgetShellTone;
}

export function WidgetShellState({
  eyebrow,
  title,
  body,
  tone = "neutral",
}: WidgetShellStateProps): JSX.Element {
  return (
    <div className={`widget-shell widget-shell--state widget-shell--state-${tone}`}>
      <div className="widget-state">
        <span className="widget-state__eyebrow">{eyebrow}</span>
        <h1 className="widget-state__title">{title}</h1>
        <p className="widget-state__body">{body}</p>
      </div>
    </div>
  );
}
