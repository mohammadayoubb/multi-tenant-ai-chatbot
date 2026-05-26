// Owner: Amer
// Minimal vitest configuration for the widget storage-discipline tests.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/__tests__/**/*.test.ts", "src/**/*.test.ts"],
    globals: false,
  },
});
