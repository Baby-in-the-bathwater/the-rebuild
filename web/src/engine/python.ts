// Loads the Python engine under Pyodide. Works in Node (tests) and in a Web Worker (the site).
// League data crosses into Python as the exact text of each response, through `lookup`; results come back as JSON text.
import { loadPyodide, version } from "pyodide";

/** The exact text of one response by its key (a Sleeper path, `players`, `values_csv`, `snapshot_index`,
 * `snapshot/<sha>`), or undefined if there is none. See rebuild/web_api.py. */
export type Lookup = (key: string) => string | undefined;
export type Plan =
  | { found: false }
  | {
      found: true;
      league: { name: string; season: string; status: string; week: number };
      chain: string[];
      snapshot_shas: string[];
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
  | { ok: false; kind: "league" | "team" | "inputs" | "engine"; message: string };

export interface Engine {
  plan(lookup: Lookup, leagueId: string): Plan;
  build(lookup: Lookup, leagueId: string, team: string, runAt: string, log: (line: string) => void): BuildResult;
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

  // Python receives the functions as JsProxies it releases after the call; a key arrives as a JS string and the
  // returned text as a Python str, and undefined arrives as None. No PyProxy is created, so none needs destroying.
  return {
    plan: (lookup, leagueId) => JSON.parse(api.plan(lookup, leagueId) as string) as Plan,
    build: (lookup, leagueId, team, runAt, log) =>
      JSON.parse(api.build(lookup, leagueId, team, runAt, log) as string) as BuildResult,
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
