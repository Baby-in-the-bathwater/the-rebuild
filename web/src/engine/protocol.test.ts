import { expect, test } from "vitest";
import { createHandler, type EngineRequest, type EngineResponse, type Runner } from "./protocol";
import { ReportError, type RunResult } from "../report/run";

const report = (team: string): RunResult => ({ league_id: "L1", roster_id: 3, summary: { team }, board_data: {}, brief: team, notices: [] });

const replies = async (run: Runner, req: EngineRequest) => {
  const out: EngineResponse[] = [];
  await createHandler(run)(req, (res) => out.push(res));
  return out;
};

const unused: Runner = async () => {
  throw new Error("not called");
};

test("ping answers pong with the engine name", async () => {
  expect(await replies(unused, { id: 7, type: "ping" })).toEqual([{ id: 7, type: "pong", engine: "placeholder" }]);
});

test("an unknown message type gets an error reply", async () => {
  expect(await replies(unused, { id: 8, type: "nope" } as never)).toEqual([
    { id: 8, type: "error", message: "unknown message type: nope" },
  ]);
});

test("a report request posts its progress lines in order, then the report", async () => {
  const seen: unknown[] = [];
  const run: Runner = async (req, onProgress) => {
    seen.push(req);
    onProgress("pulling league");
    onProgress("grading");
    return report(req.team);
  };
  const out = await replies(run, { id: 3, type: "report", leagueId: "L1", team: "Team 3", fresh: true });
  expect(seen).toEqual([{ leagueId: "L1", team: "Team 3", fresh: true }]);
  expect(out).toEqual([
    { id: 3, type: "progress", line: "pulling league" },
    { id: 3, type: "progress", line: "grading" },
    { id: 3, type: "report", report: report("Team 3") },
  ]);
});

test("a report carries the runner's notices to the page", async () => {
  const noted = { ...report("Team 3"), notices: ["Trade history could not be loaded this time."] };
  expect(await replies(async () => noted, { id: 6, type: "report", leagueId: "L1", team: "Team 3" })).toEqual([
    { id: 6, type: "report", report: noted },
  ]);
});

test("a failed report posts one error carrying the kind", async () => {
  const run: Runner = async (_req, onProgress) => {
    onProgress("pulling league");
    throw new ReportError("team", "No team matches");
  };
  expect(await replies(run, { id: 4, type: "report", leagueId: "L1", team: "x" })).toEqual([
    { id: 4, type: "progress", line: "pulling league" },
    { id: 4, type: "error", message: "No team matches", kind: "team" },
  ]);
});

test("an unexpected failure posts an error without a kind", async () => {
  const run: Runner = async () => {
    throw new Error("boom");
  };
  expect(await replies(run, { id: 5, type: "report", leagueId: "L1", team: "x" })).toEqual([
    { id: 5, type: "error", message: "boom" },
  ]);
});
