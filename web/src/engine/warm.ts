// Fetches the engine's files ahead of time from the form page, so the board page finds them in the browser's cache.
// The engine itself still starts on the board page (a worker does not outlive its page); this saves the download.
// It imports nothing from ./python, so the form page's bundle stays free of the Pyodide package.
import { dependencies } from "../../package.json";

/** The exact Pyodide version in package.json; the same value as `PYODIDE_VERSION` in ./python (a test checks). */
export const WARM_PYODIDE_VERSION: string = dependencies.pyodide;

/** What the engine worker downloads before its first report (scripts/copy_pyodide.mjs lists the Pyodide files). */
export function engineFiles(version: string = WARM_PYODIDE_VERSION): string[] {
  const pyodide = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"];
  return [...pyodide.map((name) => `/pyodide/${version}/${name}`), "/engine/engine.zip"];
}

/** Requests each file once, quietly: a failure here costs nothing, the board page fetches the file itself. */
export function warmEngine(fetchFn: typeof fetch, files: string[] = engineFiles()): Promise<void> {
  return Promise.all(
    files.map((url) =>
      fetchFn(url, { priority: "low" } as RequestInit)
        .then((res) => res.arrayBuffer())
        .catch(() => undefined),
    ),
  ).then(() => undefined);
}
