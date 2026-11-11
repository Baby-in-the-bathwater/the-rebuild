# Custom league weights: design

## Why

The board prices everything with DynastyProcess (DP) values. Real offers in DYNASTY DOGS show two gaps:

- **The curve looks too steep for this league.** Ollie Gordon II (value 108) starts for Unsolicited Dak Pick-ens, and his owner would not swap him for Cam Skattebo (1,504). An owner called two firsts plus Garrett Wilson for CeeDee Lamb a "massive win" for the seller, while the app rates it 102%.
- **Values ignore what a deal does to each team's lineup and where each team is headed.** A contender feels lost weekly points. A rebuilder cares much less.

The user wants to see both effects and tweak them, without losing the plain DP view. This is an exploration tool for judging offers, not a replacement for DP.

## Goals

- By default, the board shows exactly what it shows today: pure DP values.
- A toggle, "Custom league weights", applies an adjusted curve steepness and a lineup cost.
- The settings behind them are visible and editable, and changes update the screen immediately.
- Each team's type (contend, retool, rebuild) can be overridden on the board, because the user may ask an owner how they see themselves.

## Non-goals

- Regenerating the suggested deals in the browser. The deal list stays the one built from DP values; only its prices change.
- A this-season value blend from rest-of-season rankings. It may follow later.
- A separate bonus for picks on rebuilding teams. A low lineup rate covers this for now.
- The Yahoo integration.
- Changing `brief.md`, `summary.json` or the League trades view. They stay on pure DP values.

## Anti-goals

This would be a failure if:

- Turning the toggle off leaves any number different from today's board.
- The settings push the rosters down the page. That was the complaint that produced the two-team layout.
- Numbers change with no way to see why.

## What the user sees

**The strip.** One row above the board (layout A from the mockups), shown only on the Trade board view:

- The toggle is always visible and off by default.
- When on, the same row shows: Steepness, one lineup rate slider per team type (Contend, Retool, Rebuild, in value per weekly point), and Reset.
- It may wrap on narrow windows, but should stay one line at laptop width.
- Reset returns the sliders to their defaults. It does not clear team type overrides, because those record what an owner told the user and can't be regenerated. An override is cleared by setting that team's dropdown back to the app's grade.

**Roster rows.** With the toggle on, every player and pick value shows the re-priced number, with the DP value beside it in small muted text ("was 7,846"). The P/V column and BUY LOW and SELL HIGH tags stay on DP values.

**Team type.** With the toggle on, each roster panel header shows that team's type as a small dropdown, set to the app's grade or the user's override, with overrides visibly marked. This includes the user's own team. Changing it re-prices the current trade immediately.

**The trade panel.** With the toggle on, each team's block in the trade adds a lineup line, such as "lineup −3.3 pts/wk, −990", and its return percentage includes that amount. The panel also shows the user's pure DP return for comparison ("Pure DP: 99%"). This applies to suggested two-team deals, three-team deals, and custom trades.

**All deals view.** Prices and returns follow the toggle too, including lineup cost. The strip stays on the Trade board; with the toggle on, this view shows a one-line notice with the current settings and a link back to the board, so the changed numbers are explained. The Return and Value sorts use the re-priced numbers. The default Ranked order and the three-team order stay as built from DP values, since a ranking can't be recomputed in the browser.

## How the numbers work

**Steepness.** DP's values are almost exactly `10,467 × e^(−0.0235 × rank)` (fitted across 620 players). A value can be re-priced from the value alone, so ranks are not needed:

```
new = 10467 × (dp_value / 10467) ^ (steepness / 0.0235)
```

This also covers picks, including the app's discounted future picks. A value of 0 stays 0. At 0.0235 the formula returns the DP value (up to rounding), so at that setting the prices match DP.

**Lineup change.** For each team in a trade:

1. Take its roster, leaving out IR and taxi players. Build its best lineup from season points per game, using the league's real roster slots, with narrowest slots filled first. Sum the points.
2. Apply the trade: remove what the team sends, add what it receives. Build the best lineup again. A player on IR or taxi stays out of the lineup after moving, so he changes neither team's lineup. Otherwise a deal would create points from nothing.
3. The lineup change is after minus before. It can be positive.

Season average is used on purpose, so this week's byes and lineup choices do not affect it.

**Lineup amount.** Lineup change × the rate for that team's type. It can add to or subtract from the team's side.

**Return.** For each team: `(value received + lineup amount) / value sent`, with the top floored at 0. If a team sends nothing, its return shows "–" as it does today.

**Defaults.**

| Setting | Default | Basis |
|---|---|---|
| Steepness | 0.015 | Best fit to the league's trades (below) |
| Contend rate | 300 per point | Placeholder, meant to be tuned by hand |
| Retool rate | 150 per point | Placeholder |
| Rebuild rate | 50 per point | Placeholder |

**Evidence for 0.015.** Of the 54 league trades, 48 could be re-priced with the values of their week. Median imbalance between the two sides:

| Steepness | 0.0125 | 0.015 | 0.0175 | 0.02 | 0.0235 (DP) | 0.03 |
|---|---|---|---|---|---|---|
| Median imbalance | 32% | 32% | 37% | 43% | 53% | 81% |

Caveat: a flatter curve pulls any two sides closer together, so this overstates the case somewhat. The result is flat below 0.015, and 0.015 is the least flattening that reaches that low point. The default is a constant, not refit on each run.

## Data and build

- **Python** computes each team's type by running the existing grade on every team, and ships it with the board data, along with the league's roster slots. It keeps working when a team cannot be graded, showing "retool" for that team.
- **The browser** does all the re-pricing and lineup calculations in `rebuild/templates/trade_board.html`. There is no server and no re-run when a setting moves.
- **Saved state.** The toggle, settings and overrides are saved in the existing localStorage state (`rebuild-board-<league_id>`), so they survive reloads and weekly re-runs.
- **Scope of the suggested deal text.** "Walk away if" lines contain DP numbers. With the toggle on, these numbers must not be presented as re-priced figures.

## Known limits

- Season points per game treats a player who is out for the year as if he still scores.
- A player on IR who is due back soon adds nothing to the lineup calculation for the team receiving him, even though his value still counts.
- A rookie or recently returned player's average may rest on few games.
- The rates are placeholders with no evidence behind them yet. The lineup idea itself rests on six players.
- The suggested deals are chosen using DP values, so custom weights can reveal that one is lopsided but will not propose a replacement.

## Left to the builder

- Control styling and exact wording, matching the existing board.
- Slider ranges and steps, as long as DP's 0.0235 and 0 per point are reachable.
- How to structure the JavaScript, as long as a single pricing function is the only source of displayed values.
- How to handle roster slot types beyond the ones this league uses, such as other flex variants.
