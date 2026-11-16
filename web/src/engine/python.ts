// Loads the Python engine under Pyodide. Works in Node (tests) and in a Web Worker (the site).
// League data crosses into Python as the exact text of each response, through `lookup`; results come back as JSON text.
import { loadPyodide, version } from "pyodide";

/** The exact text of one successful response by its key (a Sleeper path, `players`, `values_csv`, `snapshot_index`,
 * `snapshot/<sha>`), or null/undefined if there is none. Never an empty or error body. See rebuild/web_api.py. */
export type Lookup = (key: string) => string | null | undefined;
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
  // PyProxies for the module, its two entry points and sys.modules, taken once and kept for the engine's lifetime.
  const api = pyodide.pyimport("rebuild.web_api");
  const pyPlan = api.plan;
  const pyBuild = api.build;
  const sysModules = pyodide.pyimport("sys").modules;

  // Per call, Python receives the lookup and log as JsProxies it releases when the call returns; keys and log lines
  // arrive as JS strings, the returned text as a Python str. JavaScript undefined arrives as None but null arrives
  // as Pyodide's jsnull, so the lookup is wrapped to answer undefined for both.
  const missingAsUndefined = (lookup: Lookup) => (key: string) => lookup(key) ?? undefined;
  return {
    plan: (lookup, leagueId) => JSON.parse(pyPlan(missingAsUndefined(lookup), leagueId) as string) as Plan,
    build: (lookup, leagueId, team, runAt, log) =>
      JSON.parse(pyBuild(missingAsUndefined(lookup), leagueId, team, runAt, log) as string) as BuildResult,
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
