// Gathers the exact response text for a league and its past seasons, reusing what the store already holds.
import type { Sleeper } from "./sleeper";
import type { Store } from "./store";

export type Texts = Record<string, string>;
export type SeasonEntry = { texts: Texts; stored: string; status: string; season: string; week: number | null };
export const MAX_SEASONS = 12;
export const SEASON_TTL_MS = 30 * 60 * 1000;

const WEEKS = Array.from({ length: 18 }, (_, i) => i + 1);

/** One league's responses, keyed by path. The bodies are parsed (a copy) only to find the draft ids. */
export async function fetchLeagueTexts(
  api: Sleeper,
  id: string,
): Promise<{ league: Record<string, any>; texts: Texts } | null> {
  const leagueText = await api.text(`league/${id}`);
  if (leagueText === null) return null;
  const league = JSON.parse(leagueText);
  const texts: Texts = { [`league/${id}`]: leagueText };
  const get = async (path: string) => {
    const text = await api.text(path);
    if (text !== null) texts[path] = text;
    return text;
  };
  const base = `league/${id}`;
  const picks = async () => {
    const draftsText = await get(`${base}/drafts`);
    if (draftsText === null) return;
    const drafts: Array<{ draft_id?: string }> = JSON.parse(draftsText);
    await Promise.all(drafts.filter((d) => d.draft_id).map((d) => get(`draft/${d.draft_id}/picks`)));
  };
  await Promise.all([
    get(`${base}/rosters`),
    get(`${base}/users`),
    get(`${base}/traded_picks`),
    get(`${base}/winners_bracket`),
    picks(),
    ...WEEKS.map((w) => get(`${base}/matchups/${w}`)),
    ...WEEKS.map((w) => get(`${base}/transactions/${w}`)),
  ]);
  return { league, texts };
}

function reusable(
  entry: SeasonEntry | undefined,
  week: number | null,
  now: Date,
  fresh: boolean | undefined,
): entry is SeasonEntry {
  if (!entry) return false;
  if (entry.status === "complete") return true;
  const age = now.getTime() - Date.parse(entry.stored);
  return !fresh && age >= 0 && age < SEASON_TTL_MS && entry.week === week;
}

export async function collectLeague(
  api: Sleeper,
  store: Store,
  leagueId: string,
  state: { week: number | null; season: string | null },
  now: Date,
  opts: { fresh?: boolean; onSeason?: (n: number) => void } = {},
): Promise<{ found: boolean; chain: string[]; texts: Texts }> {
  const chain: string[] = [];
  const texts: Texts = {};
  let next: string | null = leagueId;
  while (next && next !== "0" && chain.length < MAX_SEASONS) {
    const id: string = next;
    let entry: SeasonEntry | undefined;
    try {
      entry = await store.get<SeasonEntry>(`season:${id}`);
    } catch {
      entry = undefined;
    }
    let leagueText: string;
    if (reusable(entry, state.week, now, opts.fresh)) {
      Object.assign(texts, entry.texts);
      leagueText = entry.texts[`league/${id}`] ?? "{}";
    } else {
      const got = await fetchLeagueTexts(api, id);
      if (!got) break;
      Object.assign(texts, got.texts);
      leagueText = got.texts[`league/${id}`] ?? "{}";
      const fresh: SeasonEntry = {
        texts: got.texts,
        stored: now.toISOString(),
        status: String(got.league.status ?? ""),
        season: String(got.league.season ?? ""),
        week: state.week,
      };
      try {
        await store.set(`season:${id}`, fresh);
      } catch {
        // a store that fails must not fail the collect
      }
    }
    chain.push(id);
    opts.onSeason?.(chain.length);
    const previous = JSON.parse(leagueText).previous_league_id;
    next = previous == null ? null : String(previous);
  }
  return { found: chain.length > 0, chain, texts };
}
