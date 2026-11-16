import { describe, expect, it } from "vitest";
import { snapshotCsv, snapshotUrl, staticText, VALUES_URL, valuesCsv } from "./feeds";
import { memoryStore, type Store } from "./store";
import { countingFetch, http } from "../testing/fixture";

const HOUR = 3600_000;
const T0 = new Date("2026-11-16T12:00:00Z");
const SHA = "5a1c0de";

describe("feeds", () => {
  it("valuesCsv fetches once within 20 hours and again after", async () => {
    const f = countingFetch();
    const store = memoryStore();
    const first = await valuesCsv(f.fetch, store, T0);
    expect(first).toBe(http[VALUES_URL]);
    await valuesCsv(f.fetch, store, new Date(T0.getTime() + 19 * HOUR));
    expect(f.calls.get(VALUES_URL)).toBe(1);
    await valuesCsv(f.fetch, store, new Date(T0.getTime() + 21 * HOUR));
    expect(f.calls.get(VALUES_URL)).toBe(2);
  });
  it("snapshotCsv fetches a sha once", async () => {
    const f = countingFetch();
    const store = memoryStore();
    expect(await snapshotCsv(f.fetch, store, SHA)).toBe(http[snapshotUrl(SHA)]);
    await snapshotCsv(f.fetch, store, SHA);
    expect(f.calls.get(snapshotUrl(SHA))).toBe(1);
  });
  it("staticText throws on a non-200", async () => {
    const bad = (async () => new Response("no", { status: 500 })) as typeof fetch;
    await expect(staticText(bad, "https://example.test/x")).rejects.toThrow();
    await expect(valuesCsv(bad, memoryStore(), T0)).rejects.toThrow();
  });
  it("a store that rejects is a miss and its write is ignored", async () => {
    const broken: Store = { get: async () => { throw new Error("x"); }, set: async () => { throw new Error("x"); } };
    const f = countingFetch();
    expect(await valuesCsv(f.fetch, broken, T0)).toBe(http[VALUES_URL]);
    expect(await snapshotCsv(f.fetch, broken, SHA)).toBe(http[snapshotUrl(SHA)]);
  });
  it("an empty 200 throws and stores nothing", async () => {
    const empty = (async () => new Response("", { status: 200 })) as typeof fetch;
    const store = memoryStore();
    await expect(valuesCsv(empty, store, T0)).rejects.toThrow();
    await expect(snapshotCsv(empty, store, SHA)).rejects.toThrow();
    expect(await store.get("values")).toBeUndefined();
    expect(await store.get(`snapshot:${SHA}`)).toBeUndefined();
  });
});
