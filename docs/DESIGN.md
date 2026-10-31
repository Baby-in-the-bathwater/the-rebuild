# Design notes

## Planning options for how to run it

Three shapes were on the table. The repo ships the first two; the third is a path, not code.

| Option | Pros | Cons | Decision |
|-|-|-|-|
| **A. Local Python CLI** (`python -m rebuild`) | runs anywhere, full control, caches crawls on disk, no hosting | needs Python installed | shipped; the core |
| **B. GitHub Action** (workflow_dispatch) | zero install, inputs typed into a form, outputs as a downloadable artifact | 60-minute job cap, a fresh pool crawl is slow in CI, no persistent cache between runs | shipped as a wrapper around A; uses the shipped benchmark by default |
| **C. Hosted web app** (Streamlit / small Flask) | nicest UX, shareable link | hosting, uptime, rate limits against Sleeper from one IP, more code to maintain | not built; A + B cover the use |
| **D. Notebook (Colab)** | one click, visible intermediate tables | brittle to API shape, hard to version | not built |

A fifth path is the one this grew out of: run the CLI, then let a Claude session read `brief.md` and `board-data.json` to write the human brief and publish the board as a private artifact.

## Pipeline

```
league id + team
   |
   v
League.pull  -> settings, rosters, users, traded picks, weekly matchups, trades, bracket
Values.load  -> DynastyProcess CSV (value_2qb if Superflex else value_1qb)
walk_lineage -> previous_league_id chain, one bundle per season (cached forever once complete)
benchmark    -> shipped JSON for the format family, or discover_pool + crawl_lineages + build
grade        -> team_rows (own league) -> z within league -> percentile on the pool -> the call
classify_assets -> sell / hold / keep
deals        -> counterparties -> tradeable items -> Ask / Target / Floor packages (sells) and Open / Target / Ceiling packages (buys)
board.render + report.write
```

## Metrics (per team-season)

All from weekly `matchups` (starters and `players_points`):

- `ppg`, `QB`, `RB`, `WR`, `TE`, `DEF`: points per week in total and by the position of the player in each starting slot.
- `eff`: actual starter points over the best possible lineup for the roster positions (Superflex slots take a QB when one is left and it beats the next flex option).
- `sf_qb_rate`: share of weeks a QB sat in the Superflex slot.
- `floor`, `above_med`: worst week; share of weeks above the league median that week.
- `depth` and `depQB/RB/WR/TE`: players on the final roster averaging a startable score (QB 14, RB 9, WR 9, TE 7 per game).
- `starter_age`: mean age on September 1 of the season across every start.
- `champ`, `playoff`: from `winners_bracket` (`p == 1` row's `w` is the champion).

Everything is z-scored within its league-season before pooling, so a 2019 league and a 2026 league are comparable and scoring quirks wash out.

## Benchmark tables

- **Coefficients by season**: OLS of win% z on the five positional z's. The sign and ordering across seasons is the stability check.
- **Champion profile**: mean z of each metric for champions, playoff teams, non-playoff teams; which position carried each champion.
- **Depth, Superflex-usage and age buckets**: win%, playoff rate, title rate.
- **Trajectories**: bottom-3 teams in every completed season with a following season, tracked for N+1..N+3 by roster id (roster ids persist across renewals; owner ids do not, which is how orphan takeovers are detected). Behaviour is classified from late-N (week 8+) and N+1 trades: net +1 first or +2 picks = sold for picks; the reverse = bought; trades without net picks = churned; none = stood pat. A pre-season variant uses only trades before N+1 week 1 (Sleeper files offseason trades under week 1), so every outcome column is a real forecast.
- **Pick hit rates**: rookie drafts (70%+ of picks are players with zero prior experience) by slot bucket (early / mid / late first by thirds, round 2, round 3) and position; bars are startable, top-24 and top-12 at the position by pooled ppg within three seasons.
- **Quantiles**: 101-point ladders of each metric's z across the pool, used for percentiles in the grade.

## The call

Inputs: rank in the league, startable-depth percentile on the pool, total-value rank (players + picks), core age (mean age of the top-8 assets by value).

- **contend**: top 40% by record and depth at or above the pool median.
- **rebuild**: bottom 35% by record, or thin depth (35th percentile or lower) on a bottom-half asset base, or a retool roster whose core age is 27+.
- **retool**: everything else.

Window: contend = this season; retool = next; rebuild = two seasons out if the core is under 25.5 and a first in the next draft is held, otherwise three.

## Ledger

Sell age by position (where the format's value curve turns down): QB 30, RB 25, WR 27, TE 28. In rebuild mode a player with value 900+ at or past that age (RB one year earlier) is a sell; one tier younger but already producing is also a sell (peak price). Value 600+ and clearly younger is a hold; 24 and under or a rookie is a keep.

## Packages

A counterparty's tradeable items are everything they hold worth 150+, each scored by what the asking side wants: in rebuild and retool mode firsts in the next two drafts score highest (projected early firsts higher still), then any first, players 25 and under, seconds. The builder searches every combination of up to four pieces from the sixteen most preferred items, keeps the ones that clear the target (3% slack under it) and picks the lowest cost: overshoot, plus twice any undershoot, minus a preference bonus for each piece worth at least a tenth of the target, plus a small per-piece penalty. It stops at two pieces when a two-piece answer exists. Nothing clears the target: the most valuable pieces go in.

Sell deals (rebuild, retool): Ask = 115%, Target = 100%, Floor = 88% of the outgoing asset; a deal is dropped when even the Floor package cannot reach 97% of the floor. The walk-away line names the most preferred piece in the target package.

Buy deals (contend, retool): the two weakest positions by this season's z, skipping any the roster already covers when healthy (two startable QBs in Superflex, two RBs, three WRs, one TE), so a weakness caused by missed games is not bought twice. Contend targets startable producers near or past the sell age on bottom-half teams and pays with picks and youth. Retool targets startable players young enough to be there when the window opens (value 1,500+, age at most one year under the position's sell age) on any team, surplus-heavy and pick-hungry teams first, and pays with picks other than the own first in the next draft plus youth outside the top-8 core. Variants read Open = 88%, Target = 100%, Ceiling = 115% of the incoming player; the walk-away line is the ceiling.

Deals are ordered by the size of the asset, then by the quality of the return (preference per piece, need fit, firsts in the next two drafts), and capped at two per counterparty and four per asset.

## Trade board

One HTML file. Your roster pinned left with SELL / HOLD tags, a tab per team (teams with drafted deals first), the deal rail between them with Ask / Target / Floor (or Open / Target / Ceiling for a buy) variants that highlight what you send (red) and receive (green) on both rosters and show the value return. Dark-first with a light palette for light-mode viewers. State (selected team, deal, variant) lives in `localStorage` only.

## What it does not do

- It does not model your league's trade market; values are one public market and the ladder is where to open.
- It does not simulate rookies or injuries. The trajectory tables carry that uncertainty honestly (year-2 R² around 0.14 in the shipped pool).
- It does not post anything to Sleeper. Read-only.
