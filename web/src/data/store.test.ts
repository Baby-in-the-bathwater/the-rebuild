import { IDBFactory } from "fake-indexeddb";
import { describe, expect, it } from "vitest";
import { memoryStore, openStore } from "./store";

describe("stores", () => {
  it("memoryStore round-trips", async () => {
    const s = memoryStore();
    await s.set("a", { n: 1 });
    expect(await s.get("a")).toEqual({ n: 1 });
    expect(await s.get("b")).toBeUndefined();
  });
  it("openStore keeps values across a reopen", async () => {
    const idb = new IDBFactory();
    await (await openStore(idb)).set("k", { text: "héllo" });
    expect(await (await openStore(idb)).get("k")).toEqual({ text: "héllo" });
    expect(await (await openStore(idb)).get("missing")).toBeUndefined();
  });
  it("falls back to memory when open throws", async () => {
    const idb = { open: () => { throw new Error("denied"); } } as unknown as IDBFactory;
    const s = await openStore(idb);
    await s.set("k", "v");
    expect(await s.get("k")).toBe("v");
  });
  it("falls back to memory when there is no IndexedDB", async () => {
    const s = await openStore(undefined);
    await s.set("k", "v");
    expect(await s.get("k")).toBe("v");
  });
  it("keeps answering when writes fail", async () => {
    const real = new IDBFactory();
    const idb = {
      open: (name: string, version?: number) => {
        const request = real.open(name, version);
        request.addEventListener("success", () => {
          const db = request.result;
          const transaction = db.transaction.bind(db);
          db.transaction = ((names: string, mode?: IDBTransactionMode) => {
            if (mode === "readwrite") throw new Error("quota");
            return transaction(names, mode);
          }) as typeof db.transaction;
        });
        return request;
      },
    } as unknown as IDBFactory;
    const s = await openStore(idb);
    await s.set("k", "v");
    expect(await s.get("k")).toBe("v");
    expect(await s.get("other")).toBeUndefined();
  });
});
