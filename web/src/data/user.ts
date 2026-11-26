// Finds a Sleeper user's NFL leagues, and the team the user owns in each, from a username. Sleeper has no login:
// a username gives the user's id, and the id gives the leagues. Display only; the report itself never uses this.
import { SleeperError, type Sleeper } from "./sleeper";

export type LeagueTeam = {
  rosterId: number;
  /** The team's name, or the manager's name when the team has none, or "Team <roster id>" for a roster with no owner. */
  name: string;
  /** The owner's display name; "" for a roster with no owner. */
  manager: string;
};

export type FoundLeague = {
  leagueId: string;
  name: string;
  season: string;
  /** For example "12-team dynasty · Superflex · half PPR · TE premium". */
  format: string;
  /** Every team in the league, by roster id. */
  teams: LeagueTeam[];
  /** The roster the user owns or co-owns; null when they own none. */
  own: number | null;
};

export type Found = { username: string; displayName: string; season: string; leagues: FoundLeague[] };

/** Why a lookup found nothing: a blank or unknown username, a user with no leagues, or Sleeper not answering. */
export class LookupError extends Error {
  kind: "username" | "leagues" | "sleeper";
  constructor(kind: LookupError["kind"], message: string) {
    super(message);
    this.name = "LookupError";
    this.kind = kind;
  }
}

type Json = Record<string, any>;

/** The parsed body, or null for a missing response, a JSON `null` (how Sleeper answers an unknown user) or bad JSON. */
function parse(text: string | null): any {
  if (text === null) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** A league's format in a few words, from the settings Sleeper sends with the league. */
export function leagueFormat(league: Json): string {
  const positions: string[] = Array.isArray(league.roster_positions) ? league.roster_positions : [];
  const scoring: Json = league.scoring_settings ?? {};
  const kind = ({ 0: "redraft", 1: "keeper", 2: "dynasty" } as Record<number, string>)[league.settings?.type as number];
  const teams = Number(league.total_rosters) || 0;
  const qb = positions.includes("SUPER_FLEX") ? "Superflex" : positions.filter((p) => p === "QB").length >= 2 ? "2QB" : "1QB";
  const rec = Number(scoring.rec) || 0;
  const ppr = rec === 1 ? "PPR" : rec === 0.5 ? "half PPR" : rec === 0 ? "standard" : `${rec} PPR`;
  return [
    [teams ? `${teams}-team` : "", kind ?? ""].filter(Boolean).join(" "),
    qb,
    ppr,
    Number(scoring.bonus_rec_te) > 0 ? "TE premium" : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function teamsOf(rosters: Json[], users: Json[]): LeagueTeam[] {
  const byId = new Map(users.map((u) => [String(u.user_id), u]));
  return rosters
    .filter((r) => Number.isInteger(r.roster_id))
    .map((r) => {
      const owner = r.owner_id == null ? undefined : byId.get(String(r.owner_id));
      const manager = String(owner?.display_name ?? "");
      const teamName = String(owner?.metadata?.team_name ?? "").trim();
      return { rosterId: r.roster_id as number, name: teamName || manager || `Team ${r.roster_id}`, manager };
    })
    .sort((a, b) => a.rosterId - b.rosterId);
}

/** The user's leagues for the current NFL season, or for the season before when the current one has none yet.
 * Throws `LookupError` with a message fit to show. */
export async function findLeagues(sleeper: Sleeper, username: string): Promise<Found> {
  const name = username.trim().replace(/^@/, "");
  if (name === "") throw new LookupError("username", "Enter your Sleeper username.");
  try {
    const [user, state] = await Promise.all([
      sleeper.text(`user/${encodeURIComponent(name)}`).then(parse),
      sleeper.text("state/nfl").then(parse),
    ]);
    if (!user?.user_id) {
      throw new LookupError(
        "username",
        `Sleeper has no user called "${name}". Check the spelling: it is the username on your Sleeper profile, not your team's name.`,
      );
    }
    const uid = String(user.user_id);
    const displayName = String(user.display_name ?? user.username ?? name);
    const current = Number(state?.league_season ?? state?.season);
    if (!Number.isInteger(current)) throw new SleeperError();

    const leaguesIn = async (season: number): Promise<Json[]> => {
      const list = parse(await sleeper.text(`user/${encodeURIComponent(uid)}/leagues/nfl/${season}`));
      return Array.isArray(list) ? list.filter((l) => l && l.league_id != null) : [];
    };
    let season = current;
    let list = await leaguesIn(season);
    if (list.length === 0) {
      season = current - 1;
      list = await leaguesIn(season);
    }
    if (list.length === 0) {
      throw new LookupError("leagues", `${displayName} is not in any NFL league on Sleeper for ${current} or ${current - 1}.`);
    }

    const leagues = await Promise.all(
      list.map(async (league): Promise<FoundLeague> => {
        const id = String(league.league_id);
        const [rosters, users] = await Promise.all([
          sleeper.text(`league/${encodeURIComponent(id)}/rosters`).then(parse),
          sleeper.text(`league/${encodeURIComponent(id)}/users`).then(parse),
        ]);
        const rosterList: Json[] = Array.isArray(rosters) ? rosters : [];
        const mine = rosterList.find(
          (r) => String(r.owner_id) === uid || (Array.isArray(r.co_owners) && r.co_owners.map(String).includes(uid)),
        );
        return {
          leagueId: id,
          name: String(league.name ?? `League ${id}`),
          season: String(league.season ?? season),
          format: leagueFormat(league),
          teams: teamsOf(rosterList, Array.isArray(users) ? users : []),
          own: Number.isInteger(mine?.roster_id) ? (mine!.roster_id as number) : null,
        };
      }),
    );
    leagues.sort((a, b) => a.name.localeCompare(b.name) || a.leagueId.localeCompare(b.leagueId));
    return { username: String(user.username ?? name), displayName, season: String(season), leagues };
  } catch (e) {
    if (e instanceof LookupError) throw e;
    if (e instanceof SleeperError) throw new LookupError("sleeper", "Sleeper is not answering right now. Wait a minute, then try again.");
    throw e;
  }
}
