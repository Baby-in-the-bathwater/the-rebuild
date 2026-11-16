// Loads the Python engine under Pyodide. Works in Node (tests) and in a Web Worker (the site).
// Everything crosses the JavaScript/Python boundary as JSON text, never as Pyodide proxies.
import { loadPyodide, version } from "pyodide";

export type Plan = {
  snapshot_index: [string, string][] | null;
  snapshot_shas: string[];
  benchmark: unknown | null;
  benchmark_note: string;
  teams: { rid: number; name: string; owner: string }[];
};
export type Report = {
  league_id: string;
  roster_id: number;
  summary: Record<string, unknown>;
  board_data: Record<string, unknown>;
  brief: string;
};
export type BuildResult =
  | { ok: true; report: Report }
  | { ok: false; kind: "team" | "inputs" | "engine"; message: string };

export interface Engine {
  currentWeek(league: unknown, state: unknown): number;
  plan(partial: unknown): Plan;
  build(inputs: unknown, team: string, log: (line: string) => void): BuildResult;
  /** Names in Python's sys.modules; lets a test check that numpy and requests never load. */
  loadedModules(): string[];
}

export const PYODIDE_VERSION: string = version;

export async function loadEngine(opts: {
  indexURL: string;
  bundle: ArrayBuffer | Uint8Array;
}): Promise<Engine> {
  const pyodide = await loadPyodide({ indexURL: opts.indexURL });
  // A plain Uint8Array: Pyodide rejects subclasses such as Node's Buffer.
  const bytes =
    opts.bundle instanceof Uint8Array
      ? new Uint8Array(opts.bundle.buffer, opts.bundle.byteOffset, opts.bundle.byteLength)
      : new Uint8Array(opts.bundle);
  pyodide.unpackArchive(bytes, "zip", { extractDir: "/engine" });
  pyodide.runPython(`
import sys
sys.path.insert(0, "/engine")
from rebuild import web_api
web_api.BENCHMARK_DIR = "/engine/benchmarks"
`);
  const api = pyodide.pyimport("rebuild.web_api");
  const sysModules = pyodide.pyimport("sys").modules;

  const json = (x: unknown) => JSON.stringify(x);
  return {
    currentWeek: (league, state) => api.current_week(json(league), json(state)) as number,
    plan: (partial) => JSON.parse(api.plan(json(partial)) as string) as Plan,
    build: (inputs, team, log) =>
      JSON.parse(api.build(json(inputs), team, log) as string) as BuildResult,
    loadedModules: () => {
      const keys = sysModules.keys();
      try {
        return Array.from(keys as Iterable<string>);
      } finally {
        keys.destroy();
      }
    },
  };
}
