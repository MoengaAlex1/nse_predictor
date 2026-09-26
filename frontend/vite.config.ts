import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Build tag surfaced in the AppShell workstation header so cache issues on
// Cloudflare Pages can be diagnosed at a glance. Falls back to the ISO date
// when GITHUB_SHA isn't set (local dev).
const buildTag = process.env.GITHUB_SHA
  ? process.env.GITHUB_SHA.slice(0, 7)
  : new Date().toISOString().slice(0, 10);

export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_TAG__: JSON.stringify(buildTag),
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
