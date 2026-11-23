import { expect, test } from "vitest";
import { createEngine, EngineError, type WorkerLike } from "./client";
import { createHandler, type EngineRequest, type Runner } from "./protocol";
import { ReportError, type RunResult } from "../report/run";

type Listener = (e: any) => void;

interface FakeWorker extends WorkerLike {
  fail(message: string): void;
  flush(order?: "reverse"): void;
}

const report = (team: string): RunResult => ({ league_id: "L1", roster_id: 3, summary: { team }, board_data: {}, brief: team, notices: [] });

// A runner that reports "<team>: start", then waits until release(team) before "<team>: done" and its report.
// Team "bad" fails with a team error.
function gatedRunner() {
  const gates = new Map<string, () => void>();
  const run: Runner = async (req, onProgress) => {
    onProgress(`${req.team}: start`);
    await new Promise<void>((resolve) => gates.set(req.team, resolve));
    onProgress(`${req.team}: done`);
    if (req.team === "bad") throw new ReportError("team", "No team matches 'bad'");
    return report(req.team);
  };
  const release = async (team: string) => {
    for (let i = 0; i < 10 && !gates.has(team); i++) await Promise.resolve();
    gates.get(team)!();
    await new Promise((resolve) => setTimeout(resolve, 0));
  };
  return { run, release };
}

const instant: Runner = async (req, onProgress) => {
  onProgress("pulling league");
  onProgress("grading");
  if (req.team === "bad") throw new ReportError("team", "No team matches 'bad'");
  return report(req.team);
};

// Answers through protocol.createHandler. With `silent`, nothing is answered until
// flush() is called; failures can be injected with fail().
function fakeWorker(opts: { silent?: boolean; run?: Runner } = {}): FakeWorker {
  const listeners: Record<string, Listener[]> = { message: [], error: [] };
  const queued: EngineRequest[] = [];
  const handler = createHandler(opts.run ?? instant);
  const reply = (req: EngineRequest) =>
    void handler(req, (res) => {
      for (const l of listeners.message!) l({ data: res });
    });
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

test("a report resolves with the report and forwards progress in order", async () => {
  const lines: string[] = [];
  const got = await createEngine(fakeWorker()).report({ leagueId: "L1", team: "Team 3" }, (l) => lines.push(l));
  expect(got).toEqual(report("Team 3"));
  expect(lines).toEqual(["pulling league", "grading"]);
});

test("a report error rejects with its message and carries the kind", async () => {
  const p = createEngine(fakeWorker()).report({ leagueId: "L1", team: "bad" }, () => {});
  await expect(p).rejects.toBeInstanceOf(EngineError);
  await expect(p).rejects.toMatchObject({ message: "No team matches 'bad'", kind: "team" });
});

test("two concurrent reports are kept apart by id", async () => {
  const gated = gatedRunner();
  const engine = createEngine(fakeWorker({ run: gated.run }));
  const linesA: string[] = [];
  const linesB: string[] = [];
  const a = engine.report({ leagueId: "L1", team: "A" }, (l) => linesA.push(l));
  const b = engine.report({ leagueId: "L1", team: "bad" }, (l) => linesB.push(l));
  const settled = Promise.allSettled([a, b]);
  await gated.release("bad");
  await gated.release("A");
  const [ra, rb] = await settled;
  expect(ra).toEqual({ status: "fulfilled", value: report("A") });
  expect(rb.status).toBe("rejected");
  if (rb.status === "rejected") expect(rb.reason).toMatchObject({ kind: "team" });
  expect(linesA).toEqual(["A: start", "A: done"]);
  expect(linesB).toEqual(["bad: start", "bad: done"]);
});

test("a worker error rejects pending calls", async () => {
  const w = fakeWorker({ silent: true });
  const engine = createEngine(w);
  const p = engine.ping();
  const r = engine.report({ leagueId: "L1", team: "x" }, () => {});
  w.fail("boom");
  await expect(p).rejects.toThrow("boom");
  await expect(r).rejects.toThrow("boom");
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
