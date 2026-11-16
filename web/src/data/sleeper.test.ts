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
  it("reports each finished attempt, whether it got a response or failed", async () => {
    const seen: number[] = [];
    const api = createSleeper({ fetch: scripted([0, 500, 200]).fake, sleep: sleeps().sleep, onCall: (n) => seen.push(n) });
    await api.text("a");
    expect(seen).toEqual([1, 2, 3]);
  });
  it("does not retry a 4xx other than 404 and 429", async () => {
    const { fake, urls } = scripted([403]);
    const s = sleeps();
    await expect(createSleeper({ fetch: fake, sleep: s.sleep }).text("x")).rejects.toThrow(SleeperError);
    expect(urls).toHaveLength(1);
    expect(s.waits).toEqual([]);
  });
  it("treats an empty 200 as a failed attempt", async () => {
    const s = sleeps();
    const { fake } = scripted([200, 200]);
    let n = 0;
    const f = (async (u: string) => (n++ === 0 ? new Response("", { status: 200 }) : fake(u))) as typeof fetch;
    expect(await createSleeper({ fetch: f, sleep: s.sleep }).text("x")).toBe("[1, 2]");
    expect(s.waits).toEqual([1000]);
  });
  it("aborts an attempt that hangs and tries again", async () => {
    const s = sleeps();
    let n = 0;
    const signals: AbortSignal[] = [];
    const f = ((_url: string, init?: RequestInit) => {
      signals.push(init!.signal!);
      if (n++ > 0) return Promise.resolve(new Response("ok", { status: 200 }));
      return new Promise<Response>((_, reject) => init!.signal!.addEventListener("abort", () => reject(new Error("aborted"))));
    }) as unknown as typeof fetch;
    expect(await createSleeper({ fetch: f, sleep: s.sleep, timeoutMs: 5 }).text("x")).toBe("ok");
    expect(signals[0]!.aborted).toBe(true);
    expect(s.waits).toEqual([1000]);
  });
  it("respects the cap on its own", async () => {
    let flying = 0;
    let peak = 0;
    const f = (async () => {
      peak = Math.max(peak, ++flying);
      await new Promise((r) => setTimeout(r, 0));
      flying--;
      return new Response("ok", { status: 200 });
    }) as unknown as typeof fetch;
    const api = createSleeper({ fetch: f, concurrency: 2 });
    await Promise.all(Array.from({ length: 10 }, (_, i) => api.text(`p${i}`)));
    expect(peak).toBe(2);
  });
  it("is not stuck after a request fails", async () => {
    const f = (async (u: string) => new Response("ok", { status: u.endsWith("/bad") ? 403 : 200 })) as unknown as typeof fetch;
    const api = createSleeper({ fetch: f, concurrency: 1 });
    const results = await Promise.allSettled([api.text("bad"), api.text("a"), api.text("b")]);
    expect(results.map((r) => r.status)).toEqual(["rejected", "fulfilled", "fulfilled"]);
  });
});
