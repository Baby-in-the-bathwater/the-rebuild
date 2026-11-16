# The Rebuild: web

A static TypeScript site. A Web Worker will run the Python engine in the browser; for now the worker only answers a ping. It deploys as Cloudflare Workers static assets: there is no server code and no Worker script.

## Prerequisites

- Node 22.12 or newer
- pnpm

Install with `pnpm install --frozen-lockfile`. The esbuild and Wrangler's workerd binary need their install scripts; they are approved in `pnpm-workspace.yaml` (`allowBuilds`), so the install runs unattended.

## Commands

- `pnpm dev`: start the Vite dev server.
- `pnpm build`: type-check, then build the site into `dist/`.
- `pnpm typecheck`: run `tsc --noEmit`.
- `pnpm test`: run the Vitest suite once.
- `pnpm preview`: serve `dist/` locally with `wrangler dev` (run `pnpm build` first).

## Source folders

- `src/engine/`: the worker protocol, the worker itself and the client that talks to it. No DOM code.
- `src/ui/`: the page code that runs on the main thread.
- `src/data/`: TypeScript that fetches data (from Sleeper and other sources) and caches it in the browser. Static files the site fetches at runtime go in `public/`, because Vite does not ship files under `src/` unless they are imported.

## Deploying

`wrangler.jsonc` points at `dist/` and holds no account id or token. Supply credentials through your environment or CI secrets, never in the repo.
