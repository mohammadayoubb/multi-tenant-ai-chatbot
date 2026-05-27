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
});
