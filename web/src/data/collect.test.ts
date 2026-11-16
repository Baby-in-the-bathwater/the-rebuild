import { describe, expect, it } from "vitest";
import { collectLeague, MAX_SEASONS } from "./collect";
import { createSleeper } from "./sleeper";
import { memoryStore, type Store } from "./store";
import { countingFetch, meta, responses } from "../testing/fixture";

const NOW = new Date(meta.run_at);
const minutes = (n: number) => new Date(NOW.getTime() + n * 60_000);
const state = { week: 6, season: "2026" };
const sleeperKeys = [...responses.keys()].filter((k) => k !== "players" && k !== "snapshot_index" && k !== "values_csv" && !k.startsWith("snapshot/") && k !== "state/nfl");

const setup = (concurrency?: number) => {
  const f = countingFetch();
  return { f, api: createSleeper({ fetch: f.fetch, concurrency }) };
};

describe("collectLeague", () => {
  it("returns the fixture's chain with every response byte for byte", async () => {
    const { api } = setup();
    const got = await collectLeague(api, memoryStore(), meta.league_id, state, NOW);
    expect(got.found).toBe(true);
    expect(got.chain).toEqual(["L1", "L0"]);
    for (const [key, text] of Object.entries(got.texts)) expect(text).toBe(responses.get(key));
    expect(Object.keys(got.texts).sort()).toEqual(sleeperKeys.sort());
  });
  it("overlaps requests but never exceeds the cap", async () => {
    const { f, api } = setup(3);
    await collectLeague(api, memoryStore(), meta.league_id, state, NOW);
    expect(f.state.maxInFlight).toBe(3);
  });
  it("reuses stored seasons, and refetches only the current one when stale", async () => {
    const store = memoryStore();
    const { f, api } = setup();
    await collectLeague(api, store, meta.league_id, state, NOW);
    const current = (url: string) => /\/league\/L1|\/draft\/D1/.test(url);
    const requestsFor = (pred: (u: string) => boolean) => [...f.calls.keys()].filter(pred).length;
    const l0 = (u: string) => u.includes("/league/L0");

    f.reset();
    const again = await collectLeague(api, store, meta.league_id, state, minutes(29));
    expect(f.state.total).toBe(0);
    expect(again.chain).toEqual(["L1", "L0"]);
    for (const [key, text] of Object.entries(again.texts)) expect(text).toBe(responses.get(key));

    for (const [when, s, opts] of [
      [minutes(31), state, {}],
      [minutes(5), { week: 7, season: "2026" }, {}],
      [minutes(5), state, { fresh: true }],
    ] as const) {
      f.reset();
      const got = await collectLeague(api, store, meta.league_id, s, when, opts);
      expect(requestsFor(l0)).toBe(0);
      expect(requestsFor(current)).toBeGreaterThan(0);
      expect(f.state.total).toBeGreaterThan(0);
      for (const [key, text] of Object.entries(got.texts)) expect(text).toBe(responses.get(key));
    }
  });
  it("answers found:false after one request for an unknown league", async () => {
    const { f, api } = setup();
    const got = await collectLeague(api, memoryStore(), "nope", state, NOW);
    expect(got).toEqual({ found: false, chain: [], texts: {} });
    expect(f.state.total).toBe(1);
  });
  it("reports seasons as they finish", async () => {
    const { api } = setup();
    const seen: number[] = [];
    await collectLeague(api, memoryStore(), meta.league_id, state, NOW, { onSeason: (n) => seen.push(n) });
    expect(seen).toEqual([1, 2]);
  });
  it("is not failed by a store that throws", async () => {
    const broken: Store = {
      get: async () => { throw new Error("no"); },
      set: async () => { throw new Error("no"); },
    };
    const { api } = setup();
    const got = await collectLeague(api, broken, meta.league_id, state, NOW);
    expect(got.chain).toEqual(["L1", "L0"]);
  });
  it("stops at MAX_SEASONS", async () => {
    const pages: Record<string, string> = {};
    for (let i = 0; i < 20; i++) {
      pages[`https://api.sleeper.app/v1/league/S${i}`] = JSON.stringify({ league_id: `S${i}`, previous_league_id: `S${i + 1}`, status: "complete", season: "x" });
    }
    const f = countingFetch(pages);
    const got = await collectLeague(createSleeper({ fetch: f.fetch }), memoryStore(), "S0", state, NOW);
    expect(got.chain).toHaveLength(MAX_SEASONS);
  });
  describe("bad stored entries", () => {
    const league = (id: string, extra: object = {}) => JSON.stringify({ league_id: id, status: "complete", season: "2025", ...extra });
    const seed = async (entry: unknown) => {
      const store = memoryStore();
      await store.set("season:L0", entry);
      return store;
    };
    const cases: Array<[string, unknown]> = [
      ["no texts", { status: "complete", stored: NOW.toISOString(), season: "2025", week: 6 }],
      ["no league key", { status: "complete", stored: NOW.toISOString(), season: "2025", week: 6, texts: { "league/other": "{}" } }],
      ["league text that is not JSON", { status: "complete", stored: NOW.toISOString(), season: "2025", week: 6, texts: { "league/L0": "oops" } }],
      ["status that is not a string", { status: 3, stored: NOW.toISOString(), texts: { "league/L0": "{}" } }],
    ];
    for (const [name, entry] of cases) {
      it(`refetches over ${name}`, async () => {
        const store = await seed(entry);
        const { f, api } = setup();
        const got = await collectLeague(api, store, meta.league_id, state, NOW);
        expect(got.chain).toEqual(["L1", "L0"]);
        for (const [key, text] of Object.entries(got.texts)) expect(text).toBe(responses.get(key));
        expect([...f.calls.keys()].some((u) => u.endsWith("/league/L0"))).toBe(true);
        const stored = await store.get<{ texts: Record<string, string> }>("season:L0");
        expect(stored?.texts["league/L0"]).toBe(responses.get("league/L0"));
      });
    }
    it("stops when previous_league_id loops back into the chain", async () => {
      const f = countingFetch({
        "https://api.sleeper.app/v1/league/A": league("A", { previous_league_id: "B" }),
        "https://api.sleeper.app/v1/league/B": league("B", { previous_league_id: "A" }),
      });
      const got = await collectLeague(createSleeper({ fetch: f.fetch }), memoryStore(), "A", state, NOW);
      expect(got.chain).toEqual(["A", "B"]);
    });
    it("stops at the id \"0\" and keeps the leagues found", async () => {
      const f = countingFetch({ "https://api.sleeper.app/v1/league/A": league("A", { previous_league_id: "0" }) });
      const got = await collectLeague(createSleeper({ fetch: f.fetch }), memoryStore(), "A", state, NOW);
      expect(got.chain).toEqual(["A"]);
    });
    it("stops at a missing earlier league and keeps the leagues found", async () => {
      const f = countingFetch({ "https://api.sleeper.app/v1/league/A": league("A", { previous_league_id: "gone" }) });
      const got = await collectLeague(createSleeper({ fetch: f.fetch }), memoryStore(), "A", state, NOW);
      expect(got).toMatchObject({ found: true, chain: ["A"] });
      expect(Object.keys(got.texts)).toContain("league/A");
    });
  });
  it("stores nothing for a season whose endpoint fails, and fetches it again next time", async () => {
    const store = memoryStore();
    const pages = Object.fromEntries([...responses.keys()].filter((k) => k.startsWith("league/") || k.startsWith("draft/")).map((k) => [`https://api.sleeper.app/v1/${k}`, responses.get(k)!]));
    let failing = true;
    const f = countingFetch(pages);
    const flaky = (async (input: RequestInfo | URL, init?: RequestInit) =>
      failing && String(input).endsWith("/league/L1/users") ? new Response("", { status: 500 }) : f.fetch(input, init)) as typeof fetch;
    const api = createSleeper({ fetch: flaky, sleep: async () => {} });
    await expect(collectLeague(api, store, meta.league_id, state, NOW)).rejects.toThrow();
    expect(await store.get("season:L1")).toBeUndefined();
    failing = false;
    f.reset();
    const got = await collectLeague(api, store, meta.league_id, state, NOW);
    expect(got.chain).toEqual(["L1", "L0"]);
    expect([...f.calls.keys()].some((u) => u.includes("/league/L1"))).toBe(true);
  });
});
