import { describe, expect, it } from "vitest";
import { createSleeper, SleeperError, SLEEPER_BASE } from "./sleeper";

const scripted = (statuses: number[], body = "[1, 2]") => {
  let i = 0;
  const urls: string[] = [];
  const fake = (async (url: string) => {
    urls.push(url);
    const s = statuses[Math.min(i++, statuses.length - 1)];
    if (s === 0) throw new TypeError("network down");
    return new Response(s === 200 ? body : "x", { status: s });
  }) as typeof fetch;
  return { fake, urls };
};
const sleeps = () => {
  const waits: number[] = [];
  return { waits, sleep: async (ms: number) => void waits.push(ms) };
};

describe("Sleeper.text", () => {
  it("returns the body untouched", async () => {
    const { fake, urls } = scripted([200], '{"a":  1}\n');
    const api = createSleeper({ fetch: fake });
    expect(await api.text("league/L1")).toBe('{"a":  1}\n');
    expect(urls).toEqual([`${SLEEPER_BASE}/league/L1`]);
    expect(api.calls).toBe(1);
  });
  it("waits 5000 after a 429 and tries again", async () => {
    const { fake } = scripted([429, 200]);
    const s = sleeps();
    expect(await createSleeper({ fetch: fake, sleep: s.sleep }).text("x")).toBe("[1, 2]");
    expect(s.waits).toEqual([5000]);
  });
  it("waits 1000 after a 500 and after a network error", async () => {
    const s = sleeps();
    expect(await createSleeper({ fetch: scripted([500, 200]).fake, sleep: s.sleep }).text("x")).toBe("[1, 2]");
    expect(await createSleeper({ fetch: scripted([0, 200]).fake, sleep: s.sleep }).text("x")).toBe("[1, 2]");
    expect(s.waits).toEqual([1000, 1000]);
  });
  it("lengthens the wait with each failure", async () => {
    const s = sleeps();
    await createSleeper({ fetch: scripted([429, 429, 200]).fake, sleep: s.sleep }).text("x");
    expect(s.waits).toEqual([5000, 10000]);
  });
  it("throws SleeperError when attempts run out", async () => {
    const s = sleeps();
    const api = createSleeper({ fetch: scripted([500]).fake, sleep: s.sleep });
    await expect(api.text("x")).rejects.toThrow(SleeperError);
    await expect(api.text("x")).rejects.toThrow("Sleeper is not responding");
    expect(api.calls).toBe(8);
  });
  it("answers null for 404 without retrying", async () => {
    const { fake, urls } = scripted([404]);
    expect(await createSleeper({ fetch: fake }).text("x")).toBeNull();
    expect(urls).toHaveLength(1);
  });
  it("reports each call", async () => {
    const seen: number[] = [];
    const api = createSleeper({ fetch: scripted([200]).fake, onCall: (n) => seen.push(n) });
    await Promise.all([api.text("a"), api.text("b")]);
    expect(seen).toEqual([1, 2]);
  });
});
