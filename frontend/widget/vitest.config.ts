// Owner: Amer
// Vitest configuration for widget tests (storage discipline + chat UI).
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: [
      "src/**/__tests__/**/*.test.ts",
      "src/**/__tests__/**/*.test.tsx",
      "src/**/*.test.ts",
      "src/**/*.test.tsx",
    ],
    setupFiles: ["./src/__tests__/setup.ts"],
    globals: false,
  },
});
