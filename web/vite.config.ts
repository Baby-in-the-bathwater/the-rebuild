import { fileURLToPath } from "node:url";
import { searchForWorkspaceRoot } from "vite";
import { defineConfig } from "vitest/config";

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

// pyodide.mjs also runs under Node, so it imports node:* modules that the browser build replaces with empty stubs.
// Vite warns about each one; those warnings, and only those, are expected.
const fromPyodide = /externalized for browser compatibility, imported by "[^"]*[\\/]pyodide[\\/]pyodide\.mjs"/;
const onLog = (level: string, log: { message: string }, handler: (level: any, log: any) => void) => {
  if (level === "warn" && fromPyodide.test(log.message)) return;
  handler(level, log);
};

export default defineConfig({
  build: {
    rolldownOptions: {
      input: { index: here("./index.html"), board: here("./board.html") },
      onLog,
    },
  },
  worker: { rolldownOptions: { onLog } },
  server: {
    // The board's CSS, markup and scripts are imported as text from the CLI's templates, outside this folder.
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), here("../rebuild/templates")] },
  },
  test: {
    environment: "node",
  },
});
