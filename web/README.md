# The Rebuild: web

A static TypeScript site that runs the CLI's report in the browser. The form page (`/`) takes a Sleeper username, lists that user's leagues and lets them pick a league and a team (a league id and a team can also be typed in); the board page (`/board?league=<id>&team=<text>`) runs the report in a Web Worker (the unchanged Python engine under Pyodide), shows its progress, then shows the same trade board the CLI writes. It deploys as Cloudflare Workers static assets: there is no server code and no Worker script.

## Prerequisites

- Node 22.12 or newer
- pnpm

Install with `pnpm install --frozen-lockfile`. The esbuild and Wrangler's workerd binary need their install scripts; they are approved in `pnpm-workspace.yaml` (`allowBuilds`), so the install runs unattended.

## Commands

- `pnpm prepare-assets`: build `public/engine/engine.zip` (needs `python3` on PATH) and copy the Pyodide runtime into `public/pyodide/<version>/`. Both are generated and git-ignored. Run it once before `pnpm dev`, and again after changing `rebuild/` or the `pyodide` version.
- `pnpm data`: write the two shared data files into `public/data/` (see "Data files" below). Needs `python3` and the network; run it once before `pnpm dev` if you want the real files (the smoke test always uses the synthetic fixture's). `pnpm build` does not run it.
- `pnpm dev`: start the Vite dev server (run `pnpm prepare-assets` first).
- `pnpm build`: run `prepare-assets`, type-check, then build the site into `dist/`.
- `pnpm typecheck`: run `tsc --noEmit`.
- `pnpm test`: run the Vitest suite once.
- `pnpm preview`: serve `dist/` locally with `wrangler dev` (run `pnpm build` first).
- `node scripts/smoke.mjs`: the browser smoke test (not part of CI; run `pnpm build` first). It copies `dist/` to a temporary folder outside the repo, adds the synthetic fixture's `players.json` and `snapshot_index.json` to the copy's `data/`, serves the copy with `wrangler dev --assets` (so `dist/` never holds fixture data), removes it at the end, and drives headless Chrome through the league id form, the username lookup (an unknown username, then a known one and its league list), the board, a reload from the cache, the board at phone width (no sideways scroll, no cut-off names, one roster on screen), a malformed league id and an unknown one, answering Sleeper and GitHub from `fixtures/synth/http.json`. It needs Chrome and `puppeteer-core`, which is not a dependency of this package: set `SMOKE_CHROME` and `SMOKE_PUPPETEER` (a `node_modules` folder holding `puppeteer-core`) if the defaults do not fit your machine. It stops at once if its port (`SMOKE_PORT`, default 8787) is taken.

## Data files

`public/data/` is generated and git-ignored, like `public/engine/` and `public/pyodide/`. `scripts/build_data.py` (run with `pnpm data`) writes two files the site fetches at run time:

- `players.json`: Sleeper's player table (`players/nfl`), keyed by player id in Sleeper's order, with each record cut to the fields the engine reads (the `PLAYER_FIELDS` constant in the script says which, and where each is read). The full table is about 10 MB; the trimmed file is a few MB. The browser never fetches Sleeper's full table.
- `snapshot_index.json`: `[[iso date, sha], ...]`, oldest first, of the DynastyProcess `values.csv` commits (`GITHUB_TOKEN` is used when set, to stay under GitHub's rate limit).

If a download fails, or the new player table has fewer than 5,000 players or fewer than 80% of the players in the file already in `public/data/`, the script keeps the existing files (or writes none) and exits 1. `--players-from FILE` and `--index-from FILE` read local files instead of the network, and `--out DIR` changes the folder. Sleeper asks clients to fetch the player table at most once a day, so run `pnpm data` sparingly. If `public/data/` does not exist the build still works; the site then cannot load players until the files are there.

The Checks workflow never runs the script and makes no request to Sleeper or GitHub's API. The Deploy workflow runs it, after the Cloudflare secrets check and before the build, so a failure stops the job before anything is deployed.

## Source folders

- `src/engine/`: the worker protocol, the worker itself and the client that talks to it. No DOM code.
- `src/ui/`: the page code that runs on the main thread. `index.html` and `board.html` both load `src/ui/main.ts`, which starts the page named by `<body data-page>`. The board's CSS, markup and scripts are not copied: `src/ui/board.ts` imports them as text from `../rebuild/templates/` (the CLI's own sources), so the two boards cannot drift apart.
- `src/data/`: TypeScript that fetches data (from Sleeper and other sources) and caches it in the browser. Static files the site fetches at runtime go in `public/`, because Vite does not ship files under `src/` unless they are imported.

## Pages and routing

- `/` is `index.html`; `/board` is `board.html`. Wrangler's default `html_handling` (`auto-trailing-slash`) serves `board.html` at `/board` and redirects `/board.html` there, keeping the query; Vite's dev server serves `/board` the same way with no extra config.
- An unknown path gets `public/404.html` with a 404 status (`not_found_handling: "404-page"` in `wrangler.jsonc`).
- `/board` without a league or team links back to the form. `?fresh=1` (what "Refresh data" adds) rebuilds the report instead of using the 30-minute cache, and is then removed from the address.
- The form page fetches the engine's files (`/engine/engine.zip` and the Pyodide runtime) as soon as it has loaded, so the board page finds them in the browser's cache. The engine still starts on the board page: its worker does not outlive the page.
- The username lookup sends the board page the roster number as `team` (for example `/board?league=<id>&team=3`), so two teams with the same name cannot be confused. The address alone rebuilds the report in any browser.
- The last username, league and team entered are kept in `localStorage` under `rebuild-last`; the board keeps its own selection under `rebuild-board-<league id>`, as the CLI's file does.

## The Python runtime

Decision: Pyodide is self-hosted. `pyodide` is pinned to an exact version in `package.json`, `scripts/copy_pyodide.mjs` copies its runtime files into `public/pyodide/<version>/`, and the tests load the same package. The version served is therefore the version tested, and the site depends on no third-party host at run time. The version is in the path, so `public/_headers` marks `/pyodide/*` as cacheable for a year (`immutable`); `public/_headers` ends up in `dist/` for Cloudflare. The engine bundle at `/engine/engine.zip` is not versioned in its path and is not given that header.

Only the Python standard library is loaded: the engine never imports numpy or requests, and nothing calls `loadPackage`.

## Deploying

`wrangler.jsonc` points at `dist/` and holds no account id or token. It defines two environments:

| Environment | Worker name | Deployed by |
|-|-|-|
| `staging` | `the-rebuild-staging` | every push to `main` that touches `web/` or `rebuild/`, and a daily schedule (refreshes the data files) |
| `production` | `the-rebuild` | the Deploy workflow, run by hand |

Which Cloudflare account a deploy goes to depends only on two values, never on a file in the repo:

- `CLOUDFLARE_API_TOKEN`: an API token made from Cloudflare's "Edit Cloudflare Workers" template.
- `CLOUDFLARE_ACCOUNT_ID`: the id of the account to deploy into.

### From GitHub

The Deploy workflow (`.github/workflows/deploy.yml`) runs the checks, builds the data files and the site, deploys it and then requests the front page, `/board`, `/data/players.json`, `/data/snapshot_index.json`, `/engine/engine.zip` and the Pyodide `pyodide.asm.wasm`, failing if any is not a 200. Set the two values as Actions secrets, either on the repository or on a GitHub environment named `staging` or `production` (an environment's secrets win over the repository's). In a repository with neither, the deploy is skipped with a notice.

To deploy by hand: Actions, then Deploy, then "Run workflow", and pick the environment. Or:

```
gh workflow run deploy.yml -f environment=production
```

Moving to another Cloudflare account means replacing the two secrets. No file changes.

### From a shell

```
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
pnpm build
pnpm exec wrangler deploy --env staging
```
