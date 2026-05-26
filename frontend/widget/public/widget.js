// Owner: Amer
// Embeddable widget loader. Runs on the tenant's host page.
//
// Contract: specs/001-widget-token-exchange/contracts/widget-loader-postmessage.md
//   - After the iframe loads, the loader posts the host page's origin to the
//     iframe (the iframe runs on the platform origin and cannot read it directly).
//   - The iframe uses this origin only for UX / internal display; the platform
//     authoritatively reads `Origin` from the HTTP request header on its
//     /widgets/token call.
//
// Idempotent: at most one iframe per data-widget-id per page (FR-013 fail-soft).
(function () {
  const script = document.currentScript;
  if (!script) return;

  const widgetId = script.getAttribute("data-widget-id");
  if (!widgetId) {
    console.error("[concierge] data-widget-id is required");
    return;
  }

  if (
    document.querySelector(
      'iframe[data-concierge-widget-id="' + widgetId + '"]'
    )
  ) {
    return;
  }

  const defaultBackend = new URL(script.src).origin;
  const backendUrl =
    script.getAttribute("data-backend-url") || defaultBackend;

  const iframe = document.createElement("iframe");
  iframe.src = backendUrl + "/?widget_id=" + encodeURIComponent(widgetId);
  iframe.setAttribute("data-concierge-widget-id", widgetId);
  iframe.setAttribute("title", "Concierge chat widget");
  iframe.setAttribute(
    "sandbox",
    "allow-scripts allow-same-origin allow-forms"
  );
  iframe.setAttribute("referrerpolicy", "no-referrer-when-downgrade");
  iframe.style.position = "fixed";
  iframe.style.right = "24px";
  iframe.style.bottom = "24px";
  iframe.style.width = "360px";
  iframe.style.height = "520px";
  iframe.style.border = "0";
  iframe.style.borderRadius = "0.6rem";
  iframe.style.boxShadow = "0 10px 30px rgba(0,0,0,0.15)";

  iframe.addEventListener("load", function () {
    if (iframe.contentWindow) {
      iframe.contentWindow.postMessage(
        {
          type: "concierge.widget.host_origin",
          origin: window.location.origin,
        },
        iframe.src
      );
    }
  });

  document.body.appendChild(iframe);
})();
