import { expect, test } from "vitest";
import { createEngine, type WorkerLike } from "./client";
import { handle, type EngineRequest } from "./protocol";

type Listener = (e: any) => void;

interface FakeWorker extends WorkerLike {
  fail(message: string): void;
  flush(order?: "reverse"): void;
}

// Answers through protocol.handle. With `silent`, nothing is answered until
// flush() is called; failures can be injected with fail().
function fakeWorker(opts: { silent?: boolean } = {}): FakeWorker {
  const listeners: Record<string, Listener[]> = { message: [], error: [] };
  const queued: EngineRequest[] = [];
  const reply = (req: EngineRequest) => {
    for (const l of listeners.message!) l({ data: handle(req) });
  };
  return {
    postMessage(msg) {
      if (opts.silent) queued.push(msg as EngineRequest);
      else reply(msg as EngineRequest);
    },
    addEventListener(type, listener) {
      listeners[type]!.push(listener);
    },
    fail(message) {
      for (const l of listeners.error!) l({ message });
    },
    flush(order) {
      const reqs = order === "reverse" ? [...queued].reverse() : [...queued];
      queued.length = 0;
      reqs.forEach(reply);
    },
  };
}

test("ping resolves with the engine name", async () => {
  expect(await createEngine(fakeWorker()).ping()).toBe("placeholder");
});

test("replies are matched to requests by id", async () => {
  const w = fakeWorker({ silent: true });
  const engine = createEngine(w);
  const first = engine.ping();
  const second = engine.ping();
  const order: string[] = [];
  void first.then(() => order.push("first"));
  void second.then(() => order.push("second"));
  w.flush("reverse");
  await expect(Promise.all([first, second])).resolves.toEqual(["placeholder", "placeholder"]);
  expect(order).toEqual(["second", "first"]);
});

test("a worker error rejects pending calls", async () => {
  const w = fakeWorker({ silent: true });
  const p = createEngine(w).ping();
  w.fail("boom");
  await expect(p).rejects.toThrow("boom");
});

test("an error reply rejects the pending call with its message", async () => {
  const listeners: Listener[] = [];
  const posted: EngineRequest[] = [];
  const worker: WorkerLike = {
    postMessage: (msg) => void posted.push(msg as EngineRequest),
    addEventListener: (type, l) => {
      if (type === "message") listeners.push(l);
    },
  };
  const p = createEngine(worker).ping();
  for (const l of listeners) l({ data: { id: posted[0]!.id, type: "error", message: "nope" } });
  await expect(p).rejects.toThrow("nope");
});

test("a worker error with an empty message rejects with a fallback", async () => {
  const w = fakeWorker({ silent: true });
  const p = createEngine(w).ping();
  w.fail("");
  await expect(p).rejects.toThrow("worker error");
});
