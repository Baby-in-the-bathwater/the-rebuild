# The Rebuild: web

A static TypeScript site that runs the CLI's report in the browser. The form page (`/`) takes a Sleeper league id and a team; the board page (`/board?league=<id>&team=<text>`) runs the report in a Web Worker (the unchanged Python engine under Pyodide), shows its progress, then shows the same trade board the CLI writes. It deploys as Cloudflare Workers static assets: there is no server code and no Worker script.

## Prerequisites

- Node 22.12 or newer
- pnpm

Install with `pnpm install --frozen-lockfile`. The esbuild and Wrangler's workerd binary need their install scripts; they are approved in `pnpm-workspace.yaml` (`allowBuilds`), so the install runs unattended.

## Commands

- `pnpm prepare-assets`: build `public/engine/engine.zip` (needs `python3` on PATH) and copy the Pyodide runtime into `public/pyodide/<version>/`. Both are generated and git-ignored. Run it once before `pnpm dev`, and again after changing `rebuild/` or the `pyodide` version.
- `pnpm dev`: start the Vite dev server (run `pnpm prepare-assets` first).
- `pnpm build`: run `prepare-assets`, type-check, then build the site into `dist/`.
- `pnpm typecheck`: run `tsc --noEmit`.
- `pnpm test`: run the Vitest suite once.
- `pnpm preview`: serve `dist/` locally with `wrangler dev` (run `pnpm build` first).
- `node scripts/smoke.mjs`: the browser smoke test (not part of CI; run `pnpm build` first). It copies the synthetic fixture's `players.json` and `snapshot_index.json` into `dist/data/`, serves `dist/` with `wrangler dev`, and drives headless Chrome through the form, the board, a reload from the cache and an unknown league, answering Sleeper and GitHub from `fixtures/synth/http.json`. It needs Chrome and `puppeteer-core`, which is not a dependency of this package: set `SMOKE_CHROME` and `SMOKE_PUPPETEER` (a `node_modules` folder holding `puppeteer-core`) if the defaults do not fit your machine.

## Source folders

- `src/engine/`: the worker protocol, the worker itself and the client that talks to it. No DOM code.
- `src/ui/`: the page code that runs on the main thread. `index.html` and `board.html` both load `src/ui/main.ts`, which starts the page named by `<body data-page>`. The board's CSS, markup and scripts are not copied: `src/ui/board.ts` imports them as text from `../rebuild/templates/` (the CLI's own sources), so the two boards cannot drift apart.
- `src/data/`: TypeScript that fetches data (from Sleeper and other sources) and caches it in the browser. Static files the site fetches at runtime go in `public/`, because Vite does not ship files under `src/` unless they are imported.

## Pages and routing

- `/` is `index.html`; `/board` is `board.html`. Wrangler's default `html_handling` (`auto-trailing-slash`) serves `board.html` at `/board` and redirects `/board.html` there, keeping the query; Vite's dev server serves `/board` the same way with no extra config.
- An unknown path gets `public/404.html` with a 404 status (`not_found_handling: "404-page"` in `wrangler.jsonc`).
- `/board` without a league or team links back to the form. `?fresh=1` (what "Refresh data" adds) rebuilds the report instead of using the 30-minute cache, and is then removed from the address.
- The last league and team entered are kept in `localStorage` under `rebuild-last`; the board keeps its own selection under `rebuild-board-<league id>`, as the CLI's file does.

## The Python runtime

Decision: Pyodide is self-hosted. `pyodide` is pinned to an exact version in `package.json`, `scripts/copy_pyodide.mjs` copies its runtime files into `public/pyodide/<version>/`, and the tests load the same package. The version served is therefore the version tested, and the site depends on no third-party host at run time. The version is in the path, so `public/_headers` marks `/pyodide/*` as cacheable for a year (`immutable`); `public/_headers` ends up in `dist/` for Cloudflare. The engine bundle at `/engine/engine.zip` is not versioned in its path and is not given that header.

Only the Python standard library is loaded: the engine never imports numpy or requests, and nothing calls `loadPackage`.

## Deploying

`wrangler.jsonc` points at `dist/` and holds no account id or token. It defines two environments:

| Environment | Worker name | Deployed by |
|-|-|-|
| `staging` | `the-rebuild-staging` | every push to `main` that touches `web/` or `rebuild/` |
| `production` | `the-rebuild` | the Deploy workflow, run by hand |

Which Cloudflare account a deploy goes to depends only on two values, never on a file in the repo:

- `CLOUDFLARE_API_TOKEN`: an API token made from Cloudflare's "Edit Cloudflare Workers" template.
- `CLOUDFLARE_ACCOUNT_ID`: the id of the account to deploy into.

### From GitHub

The Deploy workflow (`.github/workflows/deploy.yml`) runs the checks, builds the site, deploys it and then loads the front page. Set the two values as Actions secrets, either on the repository or on a GitHub environment named `staging` or `production` (an environment's secrets win over the repository's). In a repository with neither, the deploy is skipped with a notice.

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
