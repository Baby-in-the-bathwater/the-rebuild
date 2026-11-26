# data

TypeScript that fetches data (from Sleeper and other sources) and caches it in the browser.

Static files the site fetches at runtime belong in `web/public/`, not here: Vite does not ship files under `src/` unless they are imported.

The repository is public, so no league ids, manager names or rosters may ever be committed. The public-data guard rejects Sleeper-style ids.

## Files

- `sleeper.ts`: Sleeper client. `text(path)` returns the response body exactly as sent (never parsed and re-written), `null` for 404. A 429 waits 5 s, 10 s, 15 s ... and retries; a network error or 5xx waits 1 s, 2 s ... and retries; when four attempts are used up it throws `SleeperError`. At most 8 requests are in flight.
- `store.ts`: key-value store on IndexedDB (database `the-rebuild`, object store `kv`). If IndexedDB cannot be opened, or a later read or write fails, it answers from memory for the rest of the session. `get` and `set` never reject.
- `collect.ts`: `fetchLeagueTexts` fetches one league's responses, keyed by the paths Python's `rebuild/sleeper.py` asks for (the Lookup keys). `collectLeague` walks `previous_league_id` back (at most 12 seasons) and returns the union of texts.
- `user.ts`: `findLeagues` turns a Sleeper username into the user's NFL leagues for the current season (the season before when the current one has none yet), each with its name, a short format label, every team and the roster the user owns or co-owns. It throws `LookupError` with a message fit to show: `username` (blank or unknown; Sleeper answers an unknown user with a JSON `null`), `leagues` (no leagues in either season) or `sleeper` (no answer). Nothing here is cached. It is for the form page only; the report never uses it.
- `feeds.ts`: DynastyProcess `values.csv` and per-commit snapshots, plus `staticText` for other static files.

## Cache rules

- `season:<league id>`: reused for good once the league's status is `complete`. Otherwise reused for 30 minutes when the NFL week is unchanged and the caller did not ask for fresh data.
- `values`: the current values file, reused for 20 hours.
- `snapshot:<sha>`: a commit's values file; a commit never changes, so it is kept for good.

TypeScript here does no league logic: it fetches, caches and passes text along. It parses a copy of a response only to learn what to fetch next, or (in `user.ts`) to label a league and its teams on the form page.
