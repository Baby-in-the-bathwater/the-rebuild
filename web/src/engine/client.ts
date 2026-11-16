import type { EngineRequest, EngineResponse, ReportRequest } from "./protocol";
import type { RunResult } from "../report/run";

export interface WorkerLike {
  postMessage(msg: unknown): void;
  addEventListener(type: "message" | "error", listener: (e: any) => void): void;
}

/** A failed request; `kind` is the ReportError kind when the worker sent one ("league", "team", "sleeper", ...). */
export class EngineError extends Error {
  kind?: string;
  constructor(message: string, kind?: string) {
    super(message);
    this.name = "EngineError";
    if (kind !== undefined) this.kind = kind;
  }
}

type Pending = {
  resolve: (res: EngineResponse) => void;
  reject: (err: Error) => void;
  onProgress?: (line: string) => void;
};

export function createEngine(worker: WorkerLike): {
  ping(): Promise<string>;
  report(req: ReportRequest, onProgress: (line: string) => void): Promise<RunResult>;
} {
  let nextId = 1;
  const pending = new Map<number, Pending>();

  worker.addEventListener("message", (e) => {
    const res = e.data as EngineResponse;
    const entry = pending.get(res.id);
    if (!entry) return;
    if (res.type === "progress") {
      entry.onProgress?.(res.line);
      return;
    }
    pending.delete(res.id);
    if (res.type === "error") entry.reject(new EngineError(res.message, res.kind));
    else entry.resolve(res);
  });

  worker.addEventListener("error", (e) => {
    const err = new EngineError(e?.message || "worker error");
    for (const entry of pending.values()) entry.reject(err);
    pending.clear();
  });

  const send = (req: EngineRequest, onProgress?: (line: string) => void) =>
    new Promise<EngineResponse>((resolve, reject) => {
      pending.set(req.id, { resolve, reject, ...(onProgress ? { onProgress } : {}) });
      worker.postMessage(req);
    });

  const unexpected = (res: EngineResponse) => new EngineError(`unexpected reply: ${res.type}`);

  return {
    async ping() {
      const res = await send({ id: nextId++, type: "ping" });
      if (res.type !== "pong") throw unexpected(res);
      return res.engine;
    },
    async report(req, onProgress) {
      const res = await send({ id: nextId++, type: "report", ...req }, onProgress);
      if (res.type !== "report") throw unexpected(res);
      return res.report;
    },
  };
}
