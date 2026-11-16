// Runs one report end to end: fetch the league's texts, hand them to the Python engine, cache the result.
// No league logic here: Python decides what the texts mean; this only fetches, caches and passes them along.
import { collectLeague } from "../data/collect";
import { snapshotCsv, staticText, valuesCsv } from "../data/feeds";
import { createSleeper, SleeperError, type Fetch } from "../data/sleeper";
import type { Store } from "../data/store";
import type { Engine, Lookup, Report } from "../engine/python";

export type ReportErrorKind = "league" | "team" | "sleeper" | "data" | "engine";

export class ReportError extends Error {
  kind: ReportErrorKind;
  constructor(kind: ReportErrorKind, message: string) {
    super(message);
    this.name = "ReportError";
    this.kind = kind;
  }
}

export type Deps = {
  fetch: Fetch;
  store: Store;
  engine: () => Promise<Engine>;
  now: () => Date;
  sleep?: (ms: number) => Promise<void>;
  /** Where the site serves players.json and snapshot_index.json. Default "/data/". */
  dataBase?: string;
};
export type Stored = { report: Report; built: string /* ISO */ };
export const REPORT_TTL_MS = 30 * 60 * 1000;

/** A report, and what the page should tell the user about this run (empty when nothing went missing). */
export type RunResult = Report & { notices: string[] };
export const TRADE_HISTORY_NOTICE = "Trade history could not be loaded this time. Refresh data to try again.";

/** Snapshot CSVs in flight at once, and the wait before the one retry of a snapshot that failed. */
export const SNAPSHOT_CONCURRENCY = 6;
export const SNAPSHOT_RETRY_MS = 1000;
const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

const teamKey = (leagueId: string, team: string) => `team:${leagueId}:${team.trim().toLowerCase()}`;
const reportKey = (leagueId: string, rosterId: number) => `report:${leagueId}:${rosterId}`;
const leagueMissing = (id: string) => new ReportError("league", `League ${id} was not found on Sleeper.`);
const engineFailed = (message: string) => new ReportError("engine", `The report could not be built: ${message}`);
const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** The store, with every failure answered as a miss or ignored: a cache must never fail a report. */
function forgiving(store: Store): Store {
  return {
    get: async <T>(key: string) => {
      try {
        return await store.get<T>(key);
      } catch {
        return undefined;
      }
    },
    set: async (key, value) => {
      try {
        await store.set(key, value);
      } catch {
        // ignored
      }
    },
  };
}

async function cached(store: Store, leagueId: string, team: string, now: Date): Promise<Report | undefined> {
  const rosterId = await store.get<number>(teamKey(leagueId, team));
  if (rosterId === undefined) return undefined;
  const held = await store.get<Stored>(reportKey(leagueId, rosterId));
  if (!held) return undefined;
  const age = now.getTime() - Date.parse(held.built);
  return age >= 0 && age < REPORT_TTL_MS ? held.report : undefined;
}

export async function runReport(
  req: { leagueId: string; team: string; fresh?: boolean },
  deps: Deps,
  onProgress: (line: string) => void,
): Promise<RunResult> {
  const store = forgiving(deps.store);
  const now = deps.now();
  if (!req.fresh) {
    // a report that lost its trade history is never stored, so a cached one has nothing to add
    const hit = await cached(store, req.leagueId, req.team, now);
    if (hit) return { ...hit, notices: [] };
  }
  try {
    return await build(req, deps, store, now, onProgress);
  } catch (e) {
    if (e instanceof ReportError) throw e;
    if (e instanceof SleeperError) throw new ReportError("sleeper", "Sleeper is not responding. Try again in a minute.");
    throw engineFailed(messageOf(e));
  }
}

async function build(
  req: { leagueId: string; team: string; fresh?: boolean },
  deps: Deps,
  store: Store,
  now: Date,
  onProgress: (line: string) => void,
): Promise<RunResult> {
  const { leagueId } = req;
  const dataBase = deps.dataBase ?? "/data/";
  const api = createSleeper({ fetch: deps.fetch, sleep: deps.sleep });

  onProgress("pulling league");
  const loading = deps.engine();
  // Awaited below. The rejection handler keeps a failure before then from being an unhandled rejection.
  loading.then(() => onProgress("engine ready"), () => {});
  const stateText = await api.text("state/nfl");
  // A body of literal `null` reads as no state, as Python's `state/nfl` lookup does.
  const state = ((stateText === null ? null : JSON.parse(stateText)) ?? {}) as { week?: unknown; season?: unknown };
  const week = Number(state.week) || null;
  const season = state.season == null ? null : String(state.season);

  const dataMissing = () => {
    throw new ReportError("data", "Could not load player data. Try again in a minute.");
  };
  onProgress("walking this league's history");
  const [league, players, values, index] = await Promise.all([
    collectLeague(api, store, leagueId, { week, season }, now, { fresh: req.fresh }).then((got) => {
      if (got.found) onProgress(`history: ${got.chain.length} seasons`);
      return got;
    }),
    staticText(deps.fetch, `${dataBase}players.json`).catch(dataMissing),
    valuesCsv(deps.fetch, store, now).catch(dataMissing),
    staticText(deps.fetch, `${dataBase}snapshot_index.json`).catch(() => undefined),
  ]);
  if (!league.found) throw leagueMissing(leagueId);

  const engine = await loading;
  const texts = new Map(Object.entries(league.texts));
  if (stateText !== null) texts.set("state/nfl", stateText);
  texts.set("players", players);
  texts.set("values_csv", values);
  if (index !== undefined) texts.set("snapshot_index", index);
  const lookup: Lookup = (key) => texts.get(key);

  let plan;
  try {
    plan = engine.plan(lookup, leagueId);
  } catch (e) {
    throw engineFailed(messageOf(e));
  }
  if (!plan.found) throw leagueMissing(leagueId);
  const { name, season: planSeason, status, week: planWeek } = plan.league;
  onProgress(`league: ${name} | season ${planSeason} ${status} | week ${planWeek}`);
  const csvs = await snapshotCsvs(plan.snapshot_shas, (sha) => snapshotCsv(deps.fetch, store, sha), deps.sleep ?? defaultSleep);
  // all or none: with none, Python skips trade history and says why
  if (csvs) plan.snapshot_shas.forEach((sha, i) => texts.set(`snapshot/${sha}`, csvs[i]!));
  const historyLost = index === undefined || csvs === null;

  const runAt = deps.now().toISOString();
  const result = engine.build(lookup, leagueId, req.team, runAt, onProgress);
  if (!result.ok) {
    if (result.kind === "team") throw new ReportError("team", result.message);
    if (result.kind === "league") throw leagueMissing(leagueId);
    throw engineFailed(result.message);
  }
  const { report } = result;
  // A report missing its trade history only because a fetch failed is not kept: the next run tries again.
  if (!historyLost) {
    const stored: Stored = { report, built: runAt };
    await store.set(reportKey(leagueId, report.roster_id), stored);
  }
  await store.set(teamKey(leagueId, req.team), report.roster_id);
  return { ...report, notices: historyLost ? [TRADE_HISTORY_NOTICE] : [] };
}

/** Every snapshot's text in order, or null when one still fails after one retry. At most SNAPSHOT_CONCURRENCY are in
 * flight; after a failure no new ones start, since none of them would be used. */
async function snapshotCsvs(
  shas: string[],
  fetchOne: (sha: string) => Promise<string>,
  sleep: (ms: number) => Promise<void>,
): Promise<string[] | null> {
  const texts: string[] = [];
  let next = 0;
  let failed = false;
  const lane = async () => {
    while (!failed && next < shas.length) {
      const i = next++;
      const sha = shas[i]!;
      try {
        texts[i] = await fetchOne(sha);
      } catch {
        await sleep(SNAPSHOT_RETRY_MS);
        try {
          texts[i] = await fetchOne(sha);
        } catch {
          failed = true;
        }
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(SNAPSHOT_CONCURRENCY, shas.length) }, lane));
  return failed ? null : texts;
}
