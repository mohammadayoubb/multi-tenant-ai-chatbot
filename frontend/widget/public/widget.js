// Owner: Amer
// Embeddable widget loader. Runs on the tenant's host page.
//
// Contract: specs/003-widget-loader-hardening/contracts/widget-loader.md
// Hand-authored at ES2019 syntax. Single-file, no imports — Vite's public/
// passthrough ships this verbatim. See contract clause C8 for the forbidden
// syntax tokens enforced by the loader test suite.
//
// Behavior:
//   - Idempotent: at most one iframe per data-widget-id per page (FR-007).
//   - Fail-soft: any misconfiguration or unexpected error logs exactly one
//     console.error and never propagates an exception to the host page
//     (FR-008, FR-009).
//   - No host-page storage access (FR-014).
(function () {
  try {
    var script = document.currentScript;
    if (!script) return;

    var widgetIdRaw = script.getAttribute("data-widget-id");
    var widgetId = widgetIdRaw ? widgetIdRaw.trim() : "";
    if (!widgetId) {
      console.error("[concierge] data-widget-id is required");
      return;
    }

    var defaultBackend = new URL(script.src).origin;
    var backendUrl =
      script.getAttribute("data-backend-url") || defaultBackend;

    function mount() {
      if (
        document.querySelector(
          'iframe[data-concierge-widget-id="' + widgetId + '"]'
        )
      ) {
        return;
      }

      var iframe = document.createElement("iframe");
      iframe.src = backendUrl + "/?widget_id=" + encodeURIComponent(widgetId);
      iframe.setAttribute("data-concierge-widget-id", widgetId);
      iframe.setAttribute("title", "Concierge chat widget");
      iframe.setAttribute(
        "sandbox",
        "allow-scripts allow-same-origin allow-forms"
      );
      iframe.setAttribute("referrerpolicy", "no-referrer-when-downgrade");
      iframe.style.position = "fixed";
      iframe.style.right = "16px";
      iframe.style.bottom = "16px";
      iframe.style.width = "80px";
      iframe.style.height = "80px";
      iframe.style.border = "0";
      iframe.style.background = "transparent";
      iframe.style.borderRadius = "0";
      iframe.style.boxShadow = "none";

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

      // US4 / T106: iframe sizing handshake. The widget posts a resize
      // message when its open/closed state changes; the loader adjusts the
      // iframe accordingly so the bubble doesn't eat host-page clicks.
      var iframeOrigin = new URL(iframe.src).origin;
      var MOBILE_BREAKPOINT = 640;
      window.addEventListener("message", function (event) {
        if (event.source !== iframe.contentWindow) return;
        if (event.origin !== iframeOrigin) return;
        var data = event.data;
        if (!data || data.type !== "concierge.widget.resize") return;
        var width = typeof data.width === "number" ? data.width : 80;
        var height = typeof data.height === "number" ? data.height : 80;
        // Mobile decision is made HERE using the host viewport. The iframe
        // can't read host width — its `window.innerWidth` reflects the
        // iframe's own size, which is tiny when collapsed.
        var hostIsMobile = window.innerWidth < MOBILE_BREAKPOINT;
        if (data.mode === "open" && hostIsMobile) {
          iframe.style.right = "0";
          iframe.style.bottom = "0";
          iframe.style.width = "100vw";
          iframe.style.height = "100vh";
          iframe.style.borderRadius = "0";
          iframe.style.boxShadow = "none";
        } else if (data.mode === "open") {
          iframe.style.right = "16px";
          iframe.style.bottom = "16px";
          iframe.style.width = width + "px";
          iframe.style.height = height + "px";
          iframe.style.borderRadius = "0.6rem";
          iframe.style.boxShadow = "0 10px 30px rgba(0,0,0,0.15)";
        } else {
          iframe.style.right = "16px";
          iframe.style.bottom = "16px";
          iframe.style.width = width + "px";
          iframe.style.height = height + "px";
          iframe.style.borderRadius = "0";
          iframe.style.boxShadow = "none";
        }
      });

      document.body.appendChild(iframe);
    }

    if (!document.body) {
      document.addEventListener("DOMContentLoaded", mount, { once: true });
      return;
    }
    mount();
  } catch (err) {
    console.error("[concierge] widget loader aborted:", err);
  }
})();
