import { defineConfig } from "vitest/config";
import path from "node:path";

// Vitest reuses our Vite config conventions — same `@/*` alias, same TS
// resolution. Only pure-logic tests for now (no DOM / React component
// testing); if we ever add component tests we'd switch `environment` to
// "jsdom" and add @testing-library/react.
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    globals: false,
  },
});
