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

Deals are ordered by the size of the asset, then by the quality of the return (preference per piece, need fit, firsts in the next two drafts), and capped at four per asset; every player on the sell list gets its deals (no per-counterparty cap).

## Trade board

One HTML file whose layout follows the number of teams. With two rosters on screen it is three columns: your roster, then the deals with the selected team, their variants and the current trade, then theirs. A third roster (pinned with a tab's + button, or a third team in the trade) reflows it to a deal strip on top and the rosters side by side below in a horizontal scroller: yours with SELL / HOLD tags, the selected team, any pinned, and every team in the trade in progress. Once a trade involves three or more teams, the deal list steps aside and the trade takes the strip's full width, one block per team with what it gets, what it sends and its return; clearing the trade brings the list back. A tab per team (teams with drafted deals first) selects the team whose deals show. Originally the deal rail sat between two rosters with Ask / Target / Floor (or Open / Target / Ceiling for a buy) variants that highlight what you send (red) and receive (green) on both rosters and show the value return. Dark-first with a light palette for light-mode viewers. State (selected team, deal, variant, view, filters, custom trade) lives in `localStorage` only.

Clicking any player row or pick chip forks the shown deal into a custom trade (your roster feeds the send side, the counterparty's the receive side); the variant buttons go inactive and reset to the drafted deal. Team names carry the manager's Sleeper username, since DMs go by username.

**Three-team deals** (`trades.three_team_deals`, rebuild and retool only): for each sell asset S and each buyer A (the same contenders the two-team deals use), you take one or two of A's most-wanted pieces X (leaving at least 15% of S), a third team B pays the rest Y (up to two pieces, from what a rebuilder wants), and B takes from A players a rebuilder does not want, Z (up to three, scored by B's two weakest positions, a contender's taste for startable players, and A's redundancy at S's position). Kept when X+Y is 97-120% of S, B's return Z/Y and A's return S/(X+Z) are both 87-115%, B is contending or Z fills one of its holes, and the quality of your return (the two-team scoring) beats A's best two-team package by 0.10. Two per sell asset (different buyers), eight in all. On the board a custom trade is a list of moves (piece, from, to); clicking your roster sends to the selected team, clicking any other roster sends to you, any piece can be dragged onto another team's block or roster to send it there instead, and the trade survives selecting other teams; pin more rosters to pull pieces from any number of teams. Each team's return shows once a third team is in.

**All deals** lists every drafted deal as a card with its variants side by side, in the brief's ranked order, sortable by return, value or team and filterable by the asset.

**P/V (production vs price)**: among rostered players at a position with 4+ games with points, a player's rank by points per game against his rank by value; the gap shows on every row. Tags split on the sell age: BUY LOW is a startable player under it producing at least twice as well as priced (and 6+ spots better); SELL HIGH is a player at or past it, worth 900+, not on IR, priced at least twice as well as producing. Old players producing cheaply and young players priced on their future show in the gap but are not tagged.

**League trades** (`trade_history.py`): every completed trade across the league's seasons, each side priced with the DynastyProcess snapshot committed the week of the trade (the data repo commits `values.csv` weekly; snapshots are immutable and cached under `cache/dp_history/`) and with today's values. Picks then: the exact slot when that draft was next, the Mid tier the season after, flat or discounted beyond. Picks now: the value today of the player drafted with it (the original owner comes from the draft order; Sleeper's pick `roster_id` is the picker), or the board's pick price if undrafted. A side wins when it is ahead by 10% of the larger side and 150+ value; otherwise even. Starter points: points the received players (or drafted players) scored in that roster's starting lineup from the trade week on. Managers are keyed by Sleeper user id. The market table credits each two-team side's return (received / sent, at trade time) to what it sent, by value share, and averages by category; 108%+ reads as a premium, 92% or under as below market, under 5 trades as thin. Consolidation is the return to the side that sold the single best asset for more pieces. FAAB is shown, not valued. The feed begins in February 2019 (its early files use older column and pick names, which are mapped): a trade older than that is shown but not priced at the time. The brief lists the first twelve deals; the board shows all of them.

**Custom league weights** (off by default; everything above is pure DP when off). A toggle above the board, one row, on the Trade board view only:

- **Steepness.** DP's values are almost exactly `10,467 × e^(−0.0235 × rank)` (fitted across 620 players), so any value moves to another steepness from the value alone: `new = 10,467 × (dp / 10,467) ^ (steepness / 0.0235)`, which covers picks and their discounts too. The default is 0.015: re-pricing 48 of this league's 54 trades with the values of their week, the median gap between the two sides is 53% at DP's 0.0235 and 32% at 0.015, flat below that. A flatter curve pulls any two sides closer together, so this overstates the case somewhat; it is a constant, not refit each run.
- **Lineup cost.** For each team in a trade, the board builds its best lineup from season points per game and the league's roster slots (narrowest slots first; IR and taxi players sit out, and stay out after a trade), before and after the trade, and multiplies the change in weekly points by a rate for the team's type: contend 300, retool 150, rebuild 50 per point. Those rates are placeholders with no evidence behind them yet. A team's return is `max(0, value received + lineup amount) / value sent`.
- **Team types** come from running the grade on every team (a team that cannot be graded is retool). Each roster header has a dropdown to override one; overrides are kept until set back to the app's grade, and Reset does not clear them.
- Roster values show the DP value beneath ("was"), the trade panel shows each team's lineup line and your pure DP return, and All deals re-prices its returns with a note naming the settings. The deal list is not rebuilt: drafted deals and their ranked order still come from DP values, and "Walk away if" numbers are marked as DP. P/V tags, League trades, `brief.md` and `summary.json` stay on DP.
- The logic lives in `rebuild/templates/board_weights.js`, inlined into the board at render time and tested with `node --test tests/`.

## What it does not do

- It does not model your league's trade market; values are one public market and the ladder is where to open.
- It does not simulate rookies or injuries. The trajectory tables carry that uncertainty honestly (year-2 R² around 0.14 in the shipped pool).
- It does not post anything to Sleeper. Read-only.
