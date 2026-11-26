import { describe, expect, it } from "vitest";
import { countingFetch, http } from "../testing/fixture";
import { createSleeper, SLEEPER_BASE } from "./sleeper";
import { findLeagues, leagueFormat, LookupError } from "./user";

// The synthetic league's own responses, plus the user lookups a browser makes before it knows the league. Every
// id and name here is made up (see tests/synth_league.py).
const url = (path: string) => `${SLEEPER_BASE}/${path}`;
const league = JSON.parse(http[url("league/L1")]!) as Record<string, unknown>;
const user = { user_id: "U3", username: "manager3", display_name: "Manager 3" };

function pagesFor(extra: Record<string, unknown>): Record<string, string> {
  const pages: Record<string, string> = { ...http };
  for (const [path, body] of Object.entries(extra)) pages[url(path)] = JSON.stringify(body);
  return pages;
}
const withLeagues = (current: unknown[], previous: unknown[] = []) =>
  pagesFor({ "user/manager3": user, "user/U3/leagues/nfl/2026": current, "user/U3/leagues/nfl/2025": previous });

const sleeperOver = (pages: Record<string, string>) => {
  const fake = countingFetch(pages);
  return { fake, sleeper: createSleeper({ fetch: fake.fetch, retries: 2, sleep: async () => {} }) };
};
const failure = async (run: Promise<unknown>): Promise<LookupError> => {
  const error = await run.then(
    () => null,
    (e: unknown) => e,
  );
  expect(error).toBeInstanceOf(LookupError);
  return error as LookupError;
};

describe("findLeagues", () => {
  it("returns the user's leagues for the current season, each with its format, its teams and the user's own", async () => {
    const { sleeper } = sleeperOver(withLeagues([league]));
    const found = await findLeagues(sleeper, "manager3");
    expect(found).toMatchObject({ username: "manager3", displayName: "Manager 3", season: "2026" });
    expect(found.leagues).toHaveLength(1);
    const [lg] = found.leagues;
    expect(lg).toMatchObject({
      leagueId: "L1",
      name: "Synthetic Dynasty League",
      season: "2026",
      format: "12-team dynasty · Superflex · half PPR",
      own: 3,
    });
    expect(lg!.teams).toHaveLength(12);
    expect(lg!.teams.map((t) => t.rosterId)).toEqual([...Array(12)].map((_, i) => i + 1));
    expect(lg!.teams[2]).toEqual({ rosterId: 3, name: "Team 3", manager: "Manager 3" });
  });

  it("trims the username, drops a leading @ and asks Sleeper once per endpoint", async () => {
    const { sleeper, fake } = sleeperOver(withLeagues([league]));
    await findLeagues(sleeper, "  @manager3 ");
    expect([...fake.calls.keys()].sort()).toEqual(
      ["league/L1/rosters", "league/L1/users", "state/nfl", "user/U3/leagues/nfl/2026", "user/manager3"].map(url),
    );
    expect([...fake.calls.values()].every((n) => n === 1)).toBe(true);
  });

  it("uses the previous season when the current one has no leagues yet", async () => {
    const old = { ...(JSON.parse(http[url("league/L0")]!) as object) };
    const { sleeper } = sleeperOver(withLeagues([], [old]));
    const found = await findLeagues(sleeper, "manager3");
    expect(found.season).toBe("2025");
    expect(found.leagues.map((l) => l.leagueId)).toEqual(["L0"]);
    expect(found.leagues[0]!.own).toBe(3);
  });

  it("says so when Sleeper has no such user, whether it answers null or 404", async () => {
    for (const pages of [pagesFor({ "user/nobody": null }), pagesFor({})]) {
      const { sleeper, fake } = sleeperOver(pages);
      const error = await failure(findLeagues(sleeper, "nobody"));
      expect(error.kind).toBe("username");
      expect(error.message).toContain('"nobody"');
      expect([...fake.calls.keys()].some((u) => u.includes("/leagues/"))).toBe(false);
    }
  });

  it("asks for a username when it is blank, without calling Sleeper", async () => {
    const { sleeper, fake } = sleeperOver(withLeagues([league]));
    expect((await failure(findLeagues(sleeper, "   "))).kind).toBe("username");
    expect(fake.state.total).toBe(0);
  });

  it("says so when the user is in no league this season or last", async () => {
    const { sleeper } = sleeperOver(withLeagues([], []));
    const error = await failure(findLeagues(sleeper, "manager3"));
    expect(error.kind).toBe("leagues");
    expect(error.message).toBe("Manager 3 is not in any NFL league on Sleeper for 2026 or 2025.");
  });

  it("reports Sleeper not answering as its own kind of failure", async () => {
    const down = (async () => {
      throw new TypeError("network down");
    }) as typeof fetch;
    const error = await failure(findLeagues(createSleeper({ fetch: down, retries: 2, sleep: async () => {} }), "manager3"));
    expect(error.kind).toBe("sleeper");
  });

  it("finds a co-owned team, and names an ownerless roster by its number", async () => {
    const rosters = (JSON.parse(http[url("league/L1/rosters")]!) as Record<string, unknown>[]).map((r) =>
      r.roster_id === 3 ? { ...r, owner_id: "U5", co_owners: ["U3"] } : r.roster_id === 5 ? { ...r, owner_id: null } : r,
    );
    const pages = { ...withLeagues([league]), [url("league/L1/rosters")]: JSON.stringify(rosters) };
    const [lg] = (await findLeagues(sleeperOver(pages).sleeper, "manager3")).leagues;
    expect(lg!.own).toBe(3);
    expect(lg!.teams[4]).toEqual({ rosterId: 5, name: "Team 5", manager: "" });
  });

  it("keeps a league where the user owns no team, with no team of their own", async () => {
    const rosters = (JSON.parse(http[url("league/L1/rosters")]!) as Record<string, unknown>[]).filter((r) => r.roster_id !== 3);
    const pages = { ...withLeagues([league]), [url("league/L1/rosters")]: JSON.stringify(rosters) };
    const [lg] = (await findLeagues(sleeperOver(pages).sleeper, "manager3")).leagues;
    expect(lg!.own).toBeNull();
    expect(lg!.teams).toHaveLength(11);
  });

  it("lists several leagues by name", async () => {
    const second = { ...league, league_id: "L0", name: "Another League" };
    const found = await findLeagues(sleeperOver(withLeagues([league, second])).sleeper, "manager3");
    expect(found.leagues.map((l) => l.name)).toEqual(["Another League", "Synthetic Dynasty League"]);
  });
});

describe("leagueFormat", () => {
  const base = { total_rosters: 10, settings: { type: 2 }, roster_positions: ["QB", "RB", "WR", "TE", "FLEX", "BN"], scoring_settings: { rec: 1 } };
  it.each([
    [base, "10-team dynasty · 1QB · PPR"],
    [{ ...base, settings: { type: 0 }, scoring_settings: {} }, "10-team redraft · 1QB · standard"],
    [{ ...base, settings: { type: 1 }, roster_positions: ["QB", "QB", "RB"] }, "10-team keeper · 2QB · PPR"],
    [{ ...base, roster_positions: ["QB", "SUPER_FLEX"], scoring_settings: { rec: 0.5, bonus_rec_te: 0.5 } }, "10-team dynasty · Superflex · half PPR · TE premium"],
    [{ ...base, scoring_settings: { rec: 0.25 } }, "10-team dynasty · 1QB · 0.25 PPR"],
    [{}, "1QB · standard"],
  ])("%j -> %s", (lg, text) => {
    expect(leagueFormat(lg)).toBe(text);
  });
});
