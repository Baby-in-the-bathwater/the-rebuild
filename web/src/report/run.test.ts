import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { memoryStore, type Store } from "../data/store";
import { snapshotUrl } from "../data/feeds";
import { loadEngine, type Engine, type Report } from "../engine/python";
import { fixtureText, http, meta, webRoot } from "../testing/fixture";
import { ReportError, runReport, type Deps } from "./run";

const expected = (name: string) => fixtureText(join("expected", name));
const NOW = new Date(meta.run_at);
const minutes = (n: number) => new Date(NOW.getTime() + n * 60_000);
const SLEEPER = "https://api.sleeper.app/v1/";
const PLAYERS = "/data/players.json";
const INDEX = "/data/snapshot_index.json";
const pages: Record<string, string> = {
  ...http,
  [PLAYERS]: fixtureText("players.json"),
  [INDEX]: fixtureText("snapshot_index.json"),
};
const snapshotUrls = Object.keys(http).filter((u) => /dynastyprocess\/data\/(?!master)/.test(u));

let tmp: string;
let engine: Engine;

beforeAll(async () => {
  tmp = mkdtempSync(join(tmpdir(), "engine-"));
  const zip = join(tmp, "engine.zip");
  execFileSync("python3", [join(webRoot, "scripts", "build_engine.py"), "--out", zip], { cwd: webRoot, stdio: "pipe" });
  engine = await loadEngine({ indexURL: join(webRoot, "node_modules", "pyodide") + "/", bundle: readFileSync(zip) });
}, 120_000);

afterAll(() => {
  if (tmp) rmSync(tmp, { recursive: true, force: true });
});

/** A fetch over `served` that counts requests per url; urls in `failing` answer 500, unknown urls 404. */
function fakeFetch(failing: Iterable<string> = [], served: Record<string, string> = pages) {
  const broken = new Set(failing);
  const calls = new Map<string, number>();
  const fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.set(url, (calls.get(url) ?? 0) + 1);
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (broken.has(url)) return new Response("server error", { status: 500 });
    const body = served[url];
    return body === undefined ? new Response("not found", { status: 404 }) : new Response(body, { status: 200 });
  }) as typeof globalThis.fetch;
  const total = () => [...calls.values()].reduce((a, b) => a + b, 0);
  return { fetch, calls, total, reset: () => calls.clear() };
}

function setup(opts: { failing?: string[]; store?: Store; now?: () => Date; served?: Record<string, string> } = {}) {
  const f = fakeFetch(opts.failing, opts.served);
  const engineCalls = { n: 0 };
  const deps: Deps = {
    fetch: f.fetch,
    store: opts.store ?? memoryStore(),
    engine: async () => {
      engineCalls.n++;
      return engine;
    },
    now: opts.now ?? (() => NOW),
    sleep: async () => {},
  };
  return { f, deps, engineCalls };
}

const run = (deps: Deps, req: Partial<{ leagueId: string; team: string; fresh: boolean }> = {}) => {
  const lines: string[] = [];
  const done = runReport({ leagueId: meta.league_id, team: meta.team, ...req }, deps, (l) => lines.push(l));
  return { lines, done };
};

const failure = async (p: Promise<unknown>): Promise<ReportError> => {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(ReportError);
    return e as ReportError;
  }
  throw new Error("expected the report to fail");
};

const expectFixtureReport = (report: Report) => {
  expect(report.league_id).toBe(meta.league_id);
  expect(report.summary).toEqual(JSON.parse(expected("summary.json")));
  expect(report.board_data).toEqual(JSON.parse(expected("board-data.json")));
  expect(report.brief).toBe(expected("brief.md"));
};

describe("runReport", () => {
  it("builds the fixture's report and reports progress in order", async () => {
    const { deps } = setup();
    const { lines, done } = run(deps);
    expectFixtureReport(await done);
    const at = (pred: (l: string) => boolean) => lines.findIndex(pred);
    const order = [
      at((l) => l === "pulling league"),
      at((l) => l === "walking this league's history"),
      at((l) => l === "history: 2 seasons"),
      at((l) => l.startsWith("league: ")),
      at((l) => l === "grading"),
    ];
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    // the engine loads while the league is fetched, so its line comes at any point before the plan's
    const ready = at((l) => l === "engine ready");
    expect(ready).toBeGreaterThan(0);
    expect(ready).toBeLessThan(at((l) => l.startsWith("league: ")));
    expect(lines.find((l) => l.startsWith("league: "))).toMatch(/^league: .+ \| season 2026 \S+ \| week 6$/);
  });

  it("answers a second run within 30 minutes from the store, and refetches only the current season when fresh", async () => {
    let now = NOW;
    const { f, deps, engineCalls } = setup({ now: () => now });
    const first = await run(deps).done;
    expect(engineCalls.n).toBe(1);

    f.reset();
    now = minutes(29);
    const again = await run(deps, { team: `  ${meta.team.toUpperCase()} ` }).done;
    expect(f.total()).toBe(0);
    expect(engineCalls.n).toBe(1);
    expect(again).toEqual(first);

    f.reset();
    const fresh = await run(deps, { fresh: true }).done;
    const urls = [...f.calls.keys()];
    expect(urls.some((u) => u.startsWith(`${SLEEPER}league/L1`))).toBe(true);
    expect(urls.some((u) => u.startsWith(`${SLEEPER}league/L0`) || u === `${SLEEPER}draft/D0/picks`)).toBe(false);
    expect(fresh).toEqual(first);
  });

  it("rebuilds once the stored report is 30 minutes old", async () => {
    let now = NOW;
    const { f, deps, engineCalls } = setup({ now: () => now });
    await run(deps).done;
    f.reset();
    now = minutes(31);
    expectFixtureReport(await run(deps).done);
    expect(engineCalls.n).toBe(2);
    expect(f.calls.get(`${SLEEPER}state/nfl`)).toBe(1);
  });

  it("names an unknown league", async () => {
    const { deps } = setup();
    const err = await failure(run(deps, { leagueId: "L404" }).done);
    expect(err.kind).toBe("league");
    expect(err.message).toBe("League L404 was not found on Sleeper.");
  });

  it("names an unknown team and lists the league's teams", async () => {
    const { deps } = setup();
    const err = await failure(run(deps, { team: "No Such Team" }).done);
    expect(err.kind).toBe("team");
    expect(err.message).toContain("Teams in this league");
  });

  it("says Sleeper is not responding when an endpoint keeps failing", async () => {
    const { f, deps } = setup({ failing: [`${SLEEPER}league/L1/rosters`] });
    const err = await failure(run(deps).done);
    expect(err.kind).toBe("sleeper");
    expect(err.message).toBe("Sleeper is not responding. Try again in a minute.");
    expect(f.calls.get(`${SLEEPER}league/L1/rosters`)).toBe(4);
  });

  for (const [what, failing] of [
    ["the snapshot index", [INDEX]],
    ["a snapshot CSV", snapshotUrls],
  ] as const) {
    it(`builds without trade history when ${what} cannot be fetched`, async () => {
      expect(failing.length).toBeGreaterThan(0);
      const { deps } = setup({ failing: [...failing] });
      const { lines, done } = run(deps);
      const report = await done;
      expect(report.board_data.trade_history).toBeNull();
      expect(lines.some((l) => l.startsWith("trade history skipped"))).toBe(true);
    });
  }

  it("reads a state/nfl body of literal null as no state", async () => {
    const { deps } = setup({ served: { ...pages, [`${SLEEPER}state/nfl`]: "null" } });
    const report = await run(deps).done;
    expect(report.league_id).toBe(meta.league_id);
  });

  it("offers the engine every snapshot CSV or none of them", async () => {
    const shas = ["aaa1111", "bbb2222"];
    const offered = async (served: Record<string, string>) => {
      const seen: Record<string, boolean> = {};
      const stub: Engine = {
        plan: () => ({
          found: true,
          league: { name: "Stub", season: "2026", status: "in_season", week: 6 },
          chain: [meta.league_id],
          snapshot_shas: shas,
          teams: [],
        }),
        build: (lookup) => {
          for (const sha of shas) seen[sha] = lookup(`snapshot/${sha}`) != null;
          return { ok: true, report: { league_id: meta.league_id, roster_id: 1, summary: {}, board_data: {}, brief: "" } };
        },
        loadedModules: () => [],
      };
      const { deps } = setup({ served });
      await runReport({ leagueId: meta.league_id, team: meta.team }, { ...deps, engine: async () => stub }, () => {});
      return seen;
    };
    const both = { ...pages, [snapshotUrl(shas[0]!)]: "csv a", [snapshotUrl(shas[1]!)]: "csv b" };
    expect(await offered(both)).toEqual({ aaa1111: true, bbb2222: true });
    const oneMissing = { ...pages, [snapshotUrl(shas[0]!)]: "csv a" };
    expect(await offered(oneMissing)).toEqual({ aaa1111: false, bbb2222: false });
  });

  it("fails with a data error when the player table cannot be fetched", async () => {
    const { deps } = setup({ failing: [PLAYERS] });
    const err = await failure(run(deps).done);
    expect(err.kind).toBe("data");
    expect(err.message).toBe("Could not load player data. Try again in a minute.");
  });

  it("completes when the store cannot save", async () => {
    const broken: Store = {
      get: async () => undefined,
      set: async () => {
        throw new Error("quota");
      },
    };
    const { deps } = setup({ store: broken });
    expectFixtureReport(await run(deps).done);
  });

  it("does not use the network for a cached report", async () => {
    let now = NOW;
    const { f, deps } = setup({ now: () => now });
    await run(deps).done;
    f.reset();
    now = minutes(1);
    const offline: Deps = { ...deps, fetch: (async () => { throw new Error("offline"); }) as typeof fetch };
    expectFixtureReport(await run(offline).done);
    expect(f.total()).toBe(0);
  });
});
