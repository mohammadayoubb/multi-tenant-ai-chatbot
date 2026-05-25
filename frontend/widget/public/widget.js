// Owner: Amer
(function () {
  const script = document.currentScript;
  const widgetId = script && script.getAttribute("data-widget-id");

  const iframe = document.createElement("iframe");
  iframe.src = "http://localhost:5173?widget_id=" + encodeURIComponent(widgetId || "");
  iframe.style.position = "fixed";
  iframe.style.right = "24px";
  iframe.style.bottom = "24px";
  iframe.style.width = "360px";
  iframe.style.height = "520px";
  iframe.style.border = "0";
  iframe.style.borderRadius = "0.6rem";
  iframe.style.boxShadow = "0 10px 30px rgba(0,0,0,0.15)";

  document.body.appendChild(iframe);
})();
