# data

TypeScript that fetches data (from Sleeper and other sources) and caches it in the browser.

Static files the site fetches at runtime belong in `web/public/`, not here: Vite does not ship files under `src/` unless they are imported.

The repository is public, so no league ids, manager names or rosters may ever be committed. The public-data guard rejects Sleeper-style ids.
