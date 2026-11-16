// DynastyProcess value files and other static text, cached in the store.
import type { Fetch } from "./sleeper";
import type { Store } from "./store";

export const VALUES_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv";
export const snapshotUrl = (sha: string) => `https://raw.githubusercontent.com/dynastyprocess/data/${sha}/files/values.csv`;
const VALUES_TTL_MS = 20 * 60 * 60 * 1000;

export async function staticText(fetch: Fetch, url: string): Promise<string> {
  const res = await fetch(url);
  if (res.status !== 200) throw new Error(`${url} answered ${res.status}`);
  return res.text();
}

export async function valuesCsv(fetch: Fetch, store: Store, now: Date): Promise<string> {
  const held = await store.get<{ text: string; stored: string }>("values");
  if (held) {
    const age = now.getTime() - Date.parse(held.stored);
    if (age >= 0 && age < VALUES_TTL_MS) return held.text;
  }
  const text = await staticText(fetch, VALUES_URL);
  await store.set("values", { text, stored: now.toISOString() });
  return text;
}

export async function snapshotCsv(fetch: Fetch, store: Store, sha: string): Promise<string> {
  const key = `snapshot:${sha}`;
  const held = await store.get<string>(key);
  if (held !== undefined) return held;
  const text = await staticText(fetch, snapshotUrl(sha));
  await store.set(key, text);
  return text;
}
