// The messages between the page and the engine worker, and how the worker answers them (testable without a Worker).
import { ReportError, type RunResult } from "../report/run";

export type ReportRequest = { leagueId: string; team: string; fresh?: boolean };

export type EngineRequest = { id: number; type: "ping" } | ({ id: number; type: "report" } & ReportRequest);

export type EngineResponse =
  | { id: number; type: "pong"; engine: string }
  | { id: number; type: "progress"; line: string }
  | { id: number; type: "report"; report: RunResult }
  | { id: number; type: "error"; message: string; kind?: string };

export const ENGINE_NAME = "placeholder";

/** Runs one report (in the worker, `runReport` with the worker's dependencies). */
export type Runner = (req: ReportRequest, onProgress: (line: string) => void) => Promise<RunResult>;

/** Answers each request through `post`: a ping with one pong; a report with its progress lines, then one report or
 * one error. Resolves once the last reply is posted. */
export function createHandler(run: Runner) {
  return async (req: EngineRequest, post: (res: EngineResponse) => void): Promise<void> => {
    switch (req.type) {
      case "ping":
        post({ id: req.id, type: "pong", engine: ENGINE_NAME });
        return;
      case "report": {
        const { id, leagueId, team, fresh } = req;
        try {
          const report = await run({ leagueId, team, ...(fresh === undefined ? {} : { fresh }) }, (line) =>
            post({ id, type: "progress", line }),
          );
          post({ id, type: "report", report });
        } catch (e) {
          const message = e instanceof Error ? e.message : String(e);
          post(e instanceof ReportError ? { id, type: "error", message, kind: e.kind } : { id, type: "error", message });
        }
        return;
      }
      default: {
        const unknown = req as { id: number; type: string };
        post({ id: unknown.id, type: "error", message: `unknown message type: ${unknown.type}` });
      }
    }
  };
}
