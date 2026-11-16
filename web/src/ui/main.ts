import { createEngine } from "../engine/client";

const status = document.getElementById("engine-status");
if (!status) throw new Error("missing #engine-status element");

const worker = new Worker(new URL("../engine/worker.ts", import.meta.url), { type: "module" });

createEngine(worker)
  .ping()
  .then((engine) => {
    status.textContent = `engine ready (${engine})`;
  })
  .catch((err: unknown) => {
    status.textContent = `engine failed: ${err instanceof Error ? err.message : String(err)}`;
  });
