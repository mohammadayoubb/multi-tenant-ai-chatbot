// Owner: Amer
// Vite production build configuration for the chat widget.
//
// The loader itself (public/widget.js) is hand-authored at ES2019 syntax and is
// copied verbatim by Vite's public/ passthrough. This config governs the iframe
// React app bundle and pins both halves to a single, committed language target.
//
// Contract: specs/003-widget-loader-hardening/contracts/widget-loader.md (C8)
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // ES2019 baseline locked per specs/003-widget-loader-hardening (FR-011, SC-004).
    target: "es2019",
  },
  // Dev-only proxy so the iframe app at http://localhost:5173 can reach the
  // FastAPI backend without CORS. In production the widget bundle is served
  // from the api origin directly, so no proxy is needed. The target uses the
  // docker-compose service name `api` so this works when the widget container
  // runs in the same compose network; override with VITE_API_TARGET for hosts
  // outside the compose network.
  server: {
    host: "0.0.0.0",
    proxy: {
      "/widgets": {
        target: process.env.VITE_API_TARGET ?? "http://api:8000",
        changeOrigin: false,
      },
      "/chat": {
        target: process.env.VITE_API_TARGET ?? "http://api:8000",
        changeOrigin: false,
      },
      "/tenants": {
        target: process.env.VITE_API_TARGET ?? "http://api:8000",
        changeOrigin: false,
      },
    },
  },
});
