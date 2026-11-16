// The synthetic league in web/fixtures/synth (written by tests/make_web_fixture.py), for tests only.
// Bodies stay the exact text Python wrote: they are never parsed and re-written here.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Lookup } from "../engine/python";

export const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const folder = join(webRoot, "fixtures", "synth");

/** One fixture file as text, e.g. "expected/brief.md". */
export const fixtureText = (name: string): string => readFileSync(join(folder, name), "utf8");

export const meta: { league_id: string; team: string; run_at: string } = JSON.parse(fixtureText("meta.json"));

/** Every request a browser report makes: url -> exact response text. A league that does not exist is absent. */
export const http: Record<string, string> = JSON.parse(fixtureText("http.json"));

const SLEEPER = "https://api.sleeper.app/v1/";
const VALUES_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv";
const SNAPSHOT = /^https:\/\/raw\.githubusercontent\.com\/dynastyprocess\/data\/([^/]+)\/files\/values\.csv$/;

/** The key Python's `lookup` asks for a url's response by (mirrors `key_of` in tests/make_web_fixture.py). */
export function keyOfUrl(url: string): string {
  if (url === VALUES_URL) return "values_csv";
  const snapshot = SNAPSHOT.exec(url);
  if (snapshot) return `snapshot/${snapshot[1]}`;
  if (url.startsWith(SLEEPER)) return url.slice(SLEEPER.length);
  throw new Error(`not a url a browser report asks for: ${url}`);
}

/** {lookup key: text}: http.json's bodies plus the player table and the snapshot index. */
export const responses: ReadonlyMap<string, string> = new Map([
  ...Object.entries(http).map(([url, text]): [string, string] => [keyOfUrl(url), text]),
  ["players", fixtureText("players.json")],
  ["snapshot_index", fixtureText("snapshot_index.json")],
]);

/** A `Lookup` over the fixture, with `omit` answered as missing. */
export function fixtureLookup(omit: Iterable<string> = []): Lookup {
  const missing = new Set(omit);
  return (key) => (missing.has(key) ? undefined : responses.get(key));
}

export const lookup: Lookup = fixtureLookup();
