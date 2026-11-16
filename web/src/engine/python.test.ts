import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { fixtureLookup, fixtureText, lookup, meta, responses, webRoot } from "../testing/fixture";
import { loadEngine, PYODIDE_VERSION, type BuildResult, type Engine } from "./python";

const expected = (name: string) => fixtureText(join("expected", name));
const snapshotKeys = [...responses.keys()].filter((k) => k.startsWith("snapshot/"));

let tmp: string;
let engine: Engine;
let result: BuildResult;
const lines: string[] = [];
const asked: string[] = [];

beforeAll(async () => {
  tmp = mkdtempSync(join(tmpdir(), "engine-"));
  const zip = join(tmp, "engine.zip");
  execFileSync("python3", [join(webRoot, "scripts", "build_engine.py"), "--out", zip], { cwd: webRoot, stdio: "pipe" });
  engine = await loadEngine({
    indexURL: join(webRoot, "node_modules", "pyodide") + "/",
    bundle: readFileSync(zip),
  });
  const counting = (key: string) => {
    asked.push(key);
    return lookup(key);
  };
  result = engine.build(counting, meta.league_id, meta.team, meta.run_at, (line) => lines.push(line));
}, 120_000);

afterAll(() => {
  if (tmp) rmSync(tmp, { recursive: true, force: true });
});

describe("the engine under Pyodide", () => {
  it("is pinned to the version the site serves", () => {
    expect(PYODIDE_VERSION).toBe("314.0.8");
  });

  it("builds exactly the report the CLI builds", () => {
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.report.summary).toEqual(JSON.parse(expected("summary.json")));
    expect(result.report.board_data).toEqual(JSON.parse(expected("board-data.json")));
    expect(result.report.brief).toBe(expected("brief.md"));
    expect(lines.length).toBeGreaterThan(0);
  });

  it("asks for each response once", () => {
    expect(asked.length).toBeGreaterThan(0);
    expect(new Set(asked).size).toBe(asked.length);
  });

  it("plans the league, its chain and the snapshots to fetch", () => {
    const plan = engine.plan(lookup, meta.league_id);
    expect(plan.found).toBe(true);
    if (!plan.found) return;
    const inputs = JSON.parse(fixtureText("inputs.json"));
    expect(plan.league.name).toBe(inputs.pull.league.name);
    expect(plan.league.week).toBe(inputs.state.week);
    expect(plan.chain).toEqual(inputs.chain);
    expect(plan.snapshot_shas.length).toBeGreaterThan(0);
    expect([...plan.snapshot_shas].sort()).toEqual(Object.keys(inputs.snapshots).sort());
    expect(plan.teams.map((t) => t.name)).toContain(meta.team);
    // the plan needs the index, not the CSVs it names
    const withoutCsvs = engine.plan(fixtureLookup(snapshotKeys), meta.league_id);
    expect(withoutCsvs.found && withoutCsvs.snapshot_shas).toEqual(plan.snapshot_shas);
  });

  it("says when the league does not exist", () => {
    expect(engine.plan(lookup, "L404")).toEqual({ found: false });
    const bad = engine.build(lookup, "L404", meta.team, meta.run_at, () => {});
    expect(bad.ok).toBe(false);
    if (!bad.ok) expect(bad.kind).toBe("league");
  });

  it("names the problem for an unknown team", () => {
    const bad = engine.build(lookup, meta.league_id, "No Such Team", meta.run_at, () => {});
    expect(bad.ok).toBe(false);
    if (!bad.ok) expect(bad.kind).toBe("team");
  });

  it("builds without trade history when the snapshot index is missing", () => {
    const skipped: string[] = [];
    const out = engine.build(fixtureLookup(["snapshot_index"]), meta.league_id, meta.team, meta.run_at, (l) => skipped.push(l));
    expect(out.ok).toBe(true);
    if (!out.ok) return;
    expect(out.report.board_data.trade_history).toBeNull();
    expect(skipped).toContain("trade history skipped: no snapshot index");
  });

  it("never loads numpy or requests", () => {
    const loaded = engine.loadedModules();
    expect(loaded).toContain("rebuild.web_api");
    expect(loaded).not.toContain("numpy");
    expect(loaded).not.toContain("requests");
  });
});
