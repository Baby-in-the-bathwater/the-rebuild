import type { EngineRequest, EngineResponse } from "./protocol";

export interface WorkerLike {
  postMessage(msg: unknown): void;
  addEventListener(type: "message" | "error", listener: (e: any) => void): void;
}

type Pending = { resolve: (engine: string) => void; reject: (err: Error) => void };

export function createEngine(worker: WorkerLike): { ping(): Promise<string> } {
  let nextId = 1;
  const pending = new Map<number, Pending>();

  worker.addEventListener("message", (e) => {
    const res = e.data as EngineResponse;
    const entry = pending.get(res.id);
    if (!entry) return;
    pending.delete(res.id);
    if (res.type === "pong") entry.resolve(res.engine);
    else entry.reject(new Error(res.message));
  });

  worker.addEventListener("error", (e) => {
    const err = new Error(e?.message || "worker error");
    for (const entry of pending.values()) entry.reject(err);
    pending.clear();
  });

  return {
    ping() {
      const id = nextId++;
      return new Promise<string>((resolve, reject) => {
        pending.set(id, { resolve, reject });
        const req: EngineRequest = { id, type: "ping" };
        worker.postMessage(req);
      });
    },
  };
}
