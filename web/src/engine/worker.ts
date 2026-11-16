// The engine worker: runs reports with the real network, the IndexedDB store and Pyodide, loaded once.
import { openStore } from "../data/store";
import { runReport } from "../report/run";
import { createHandler } from "./protocol";
import { loadEngine, PYODIDE_VERSION, type Engine } from "./python";

declare const self: DedicatedWorkerGlobalScope;

let loading: Promise<Engine> | null = null;

/** The engine, loaded on first use and reused; a failed load is forgotten so the next request tries again. */
function engine(): Promise<Engine> {
  if (!loading) {
    loading = (async () => {
      const res = await fetch("/engine/engine.zip");
      if (!res.ok) throw new Error(`/engine/engine.zip answered ${res.status}`);
      return loadEngine({ indexURL: `/pyodide/${PYODIDE_VERSION}/`, bundle: await res.arrayBuffer() });
    })();
    loading.catch(() => {
      loading = null;
    });
  }
  return loading;
}

const store = openStore();

const handle = createHandler(async (req, onProgress) =>
  runReport(
    req,
    { fetch: (input, init) => fetch(input, init), store: await store, engine, now: () => new Date() },
    onProgress,
  ),
);

self.addEventListener("message", (e: MessageEvent) => {
  void handle(e.data, (res) => self.postMessage(res));
});
