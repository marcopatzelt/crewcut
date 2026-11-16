/// <reference types="vitest" />
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// The app talks to the Crewcut server. In development, Vite forwards /api to the main port
// and /p (teleprompter data) to the teleprompter port. Override with CREWCUT_API / CREWCUT_PROMPTER.
const api = process.env.CREWCUT_API ?? "http://127.0.0.1:4747";
const prompter = process.env.CREWCUT_PROMPTER ?? "http://127.0.0.1:4748";

/**
 * Astryx's prebuilt CSS holds a few rules that remove the focus outline on :focus (for components Crewcut does not
 * use, such as AppShell). Crewcut draws its own ring on :focus-visible (DESIGN.md rule 15), so these rules are left
 * out of the build: no style sheet of the app may hide focus.
 */
function noFocusRemoval(): Plugin {
  return {
    name: "crewcut-no-focus-removal",
    enforce: "pre",
    transform(code, id) {
      if (!/@astryxdesign[\\/]core[\\/].*\.css($|\?)/.test(id)) return null;
      const out = code.replace(/\.[\w-]+:focus(?::not\(#\\#\))*\{outline:none\}/g, "");
      return out === code ? null : { code: out, map: null };
    },
  };
}

export default defineConfig({
  plugins: [react(), noFocusRemoval()],
  base: "/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        prompter: fileURLToPath(new URL("./prompter.html", import.meta.url)),
      },
      output: {
        // React, icons and fonts in one shared file; the demo data in another.
        manualChunks(id) {
          if (id.includes("node_modules")) return "vendor";
          if (id.includes("/src/demo/")) return "demo";
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: api, changeOrigin: false },
      "^/p/[^/]+/(script|control)$": { target: prompter, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
