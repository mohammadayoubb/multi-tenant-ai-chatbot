// Owner: Amer
import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function WidgetApp() {
  return (
    <div className="widget-shell">
      <h1>Concierge</h1>
      <p>Placeholder embedded widget.</p>
      <input placeholder="Ask a question..." />
      <button>Send</button>
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<WidgetApp />);
