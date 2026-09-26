/// <reference types="vite/client" />

// Build-time constant injected by vite.config.ts's `define`. Surfaced in
// AppShell so cache issues can be diagnosed at a glance.
declare const __BUILD_TAG__: string;
