# the-rebuild

Grade any Sleeper dynasty roster against what actually wins its format, make the call (contend, retool, rebuild), and draft the trades, with an interactive trade board you can open in a browser.

League id and team name in. Brief, trade board and data out.

```
python -m rebuild --league 123456789012345678 --team "My Team"
```

```
[    0s] pulling league
[    1s] league: <name> | dynasty-12team-sf-halfppr | season 2026 in_season | week 8 | 32 calls
[    1s] team: My Team (roster 9, manager <you>)
[    2s] values: DynastyProcess value_2qb as of 2026-10-31
[    2s] walking this league's history
[   38s] history: 5 seasons (2026, 2025, 2024, 2023, 2022)
[   38s] benchmark: shipped dynasty-12team-sf-halfppr (13452 team-seasons)
[   39s] call: rebuild (window 2029); 9th of 12 with startable depth at the 56th percentile; asset base ranks 11th of 12
[   39s] ledger: sell 4, hold 2, keep 9
[   39s] deals: 12 across 6 counterparties

  brief        out/<league id>/brief.md
  trade board  out/<league id>/trade-board.html
  summary      out/<league id>/summary.json
```

The first run of a league pulls its past seasons (about 40 seconds for five); they are cached, so later runs take a few seconds.

## What it does

1. **Pulls the league** from Sleeper's public API: settings, rosters, users, traded picks, every week's lineups and points, this season's trades. No login, no API key.
2. **Prices every asset** with the open DynastyProcess values feed (Superflex or 1QB column chosen from the league settings). Picks are priced by the original team's projected slot from current standings.
3. **Walks the league's own history** through `previous_league_id`: who won each season, what carried them, and how this roster slot finished under each manager.
4. **Loads the format benchmark**: what wins in leagues like this one. Two benchmarks ship: 12-team Superflex half-PPR dynasty (251 leagues, 1,100+ league-seasons back to 2019) and the same format with TE premium (166 leagues, 580 league-seasons). Any other format gets crawled on first run (about 4 minutes for 160 leagues; up to 20 for a big family) and saved for next time.
5. **Grades the roster** on the metrics that predict winning: positional points, startable depth, lineup efficiency, starter age, pick capital. Each one is a within-league z-score placed on the pool, so a percentile reads the same in any league of the format.
6. **Makes the call** and sets the window: contend now, retool for next season, or rebuild for two to three seasons out. A redraft league is always contend for this season: no picks, age ignored, bench depth is the currency (the values feed is a dynasty market, so read its numbers as relative size only).
7. **Writes the ledger**: sell (production that will not survive the window), hold (young core), keep (cheap youth).
8. **Drafts the deals**. Rebuild: for each sell asset and each contender with pick capital, an Ask / Target / Floor package built from what that team actually holds, scored by what a rebuilder should want (firsts in the next two drafts, players under 25). Contend: buy an older producer at the weakest starting spot with far-out picks and non-producing youth. Retool: sell anything past its sell age the same way, and buy one young starter at the weakest uncovered position with surplus picks and non-core youth, keeping the own first in the next draft; buy packages read Open / Target / Ceiling (what you pay).
9. **Writes it up**: `brief.md` (the call, standing, what wins, history, ledger, deals, what to expect, pick hit rates; `--pdf` adds `brief.pdf`) and `trade-board.html` (Sleeper-style, all rosters, every deal highlighted on both sides with the value return).
10. **Routes sells through a third team** when a buyer cannot pay in what you want: the buyer sends players you do not want to a team that does, and that team pays you. Kept only when both other teams land near fair at market value and your return beats the buyer's best two-team package (brief section and All deals view). On the board, any custom trade can take a third or fourth team: route any piece to any team.
11. **Builds the trade board's other views**: click any players and picks to build your own trade and see its return; compare every drafted deal side by side (All deals); tag each rostered player's production against his price (P/V column, BUY LOW / SELL HIGH); and price the league's whole trade history (League trades) with the DynastyProcess values from the week of each trade and with today's, naming who won each one, who trades well, and what this league pays over or under market for each kind of asset.

## Three ways to run it

| | Who it suits | How |
|-|-|-|
| **Local CLI** | anyone with Python 3.10+ | `pip install -r requirements.txt`, then the command above. Add `--open` to launch the board. |
| **GitHub Action** | no install at all | Fork the repo, Actions tab, "Run the rebuild", enter league id and team, download the artifact from the run page. |
| **Claude session** | you want to talk it through | Run the CLI, then hand the brief and board to a Claude session for the write-up; the board publishes as a private artifact as is. |

## Options

```
--league ID          Sleeper league id (required)
--team NAME          team name (as Sleeper shows it), manager display name, username, or roster id (required)
--out DIR            output folder (default out/<league id>)
--pool               crawl a fresh benchmark pool for this format even if a shipped one matches
--pool-target N      leagues to find (default 150)
--crawl-seconds S    time cap for discovery (default 600)
--benchmarks PATH    use this benchmark JSON
--no-history         skip the league's own previous-season walk
--no-trade-history   skip pricing the league's past trades (it fetches weekly DynastyProcess snapshots from GitHub, cached after the first run)
--refresh-values     re-download the values feed
--cache-dir DIR      where pulls and crawled seasons are cached (default ./cache)
--pdf                also render brief.pdf (needs Chrome, Chromium or Edge installed; the Action does this)
--open               open the trade board when done
```

## Benchmarks

`benchmarks/*.json` hold aggregate tables only (no manager names, no rosters): positional regression coefficients by season, champion profiles, depth and age buckets, rebuild trajectories (bottom-3 teams followed for three seasons, split by what they did), and rookie pick hit rates by slot and position. The matching rule is the format family: team count, dynasty, Superflex or 1QB, reception scoring, TE premium or not.

Shipped: `dynasty-12team-sf-halfppr` and `dynasty-12team-sf-halfppr-tep`. Building one yourself: run with `--pool` on any league of the format. The crawl snowballs from that league's managers through their other leagues, keeps the ones in the family, walks each one's history, and writes `benchmark-<format>.json` into the output folder. Copy it into `benchmarks/` to ship it.

## Method notes

See [docs/DESIGN.md](docs/DESIGN.md) for the metric definitions, the call rule, the package builder, and the planning options that were considered.

## Data and credits

- Sleeper public API (`api.sleeper.app/v1`). Read-only, unauthenticated.
- Trade values: [DynastyProcess](https://github.com/dynastyprocess/data) open data, MIT. Historical values for the trade history come from that repo's weekly commits of `values.csv`.
- Built by Core-E LLC. MIT license.
