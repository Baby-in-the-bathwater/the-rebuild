// DynastyProcess value files and other static text, cached in the store.
import type { Fetch } from "./sleeper";
import type { Store } from "./store";

export const VALUES_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv";
export const snapshotUrl = (sha: string) => `https://raw.githubusercontent.com/dynastyprocess/data/${sha}/files/values.csv`;
const VALUES_TTL_MS = 20 * 60 * 60 * 1000;

const readOrMiss = async <T>(store: Store, key: string): Promise<T | undefined> => {
  try {
    return await store.get<T>(key);
  } catch {
    return undefined;
  }
};
const writeOrIgnore = async (store: Store, key: string, value: unknown) => {
  try {
    await store.set(key, value);
  } catch {
    // a store that fails must not fail the fetch
  }
};

export async function staticText(fetch: Fetch, url: string): Promise<string> {
  const res = await fetch(url);
  if (res.status !== 200) throw new Error(`${url} answered ${res.status}`);
  const text = await res.text();
  if (text === "") throw new Error(`${url} answered an empty body`);
  return text;
}

export async function valuesCsv(fetch: Fetch, store: Store, now: Date): Promise<string> {
  const held = await readOrMiss<{ text: string; stored: string }>(store, "values");
  if (held && typeof held.text === "string" && held.text !== "") {
    const age = now.getTime() - Date.parse(held.stored);
    if (age >= 0 && age < VALUES_TTL_MS) return held.text;
  }
  const text = await staticText(fetch, VALUES_URL);
  await writeOrIgnore(store, "values", { text, stored: now.toISOString() });
  return text;
}

export async function snapshotCsv(fetch: Fetch, store: Store, sha: string): Promise<string> {
  const key = `snapshot:${sha}`;
  const held = await readOrMiss<string>(store, key);
  if (typeof held === "string" && held !== "") return held;
  const text = await staticText(fetch, snapshotUrl(sha));
  await writeOrIgnore(store, key, text);
  return text;
}
