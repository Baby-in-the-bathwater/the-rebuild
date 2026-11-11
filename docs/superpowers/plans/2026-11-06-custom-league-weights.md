# Custom League Weights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Custom league weights" toggle to the trade board that re-prices values with an adjusted curve steepness and adds a per-trade lineup cost weighted by team type, all editable live, with pure DynastyProcess (DP) values as the default.

**Architecture:** Pure pricing and lineup logic lives in a new `rebuild/templates/board_weights.js`, testable with Node and inlined into the single-file board at render time. Python ships each team's graded type and the league's roster slots in the board data. The template routes every displayed value through one pricing function and recalculates in the browser.

**Tech Stack:** Python 3 (stdlib `unittest`, no new dependencies), vanilla JS, Node's built-in `node --test` for JS logic, Chrome for visual checks.

**Spec:** `docs/superpowers/specs/2026-11-06-custom-league-weights-design.md`

## Global Constraints

- Toggle off by default. With it off, every number on the board is identical to today's.
- Curve: `new = 10467 × (dp_value / 10467) ^ (steepness / 0.0235)`; 0 stays 0.
- Defaults: steepness 0.015; rates per weekly point: contend 300, retool 150, rebuild 50.
- Return: `max(0, value received + lineup amount) / value sent`; "–" if the team sends nothing.
- A player on IR or taxi stays out of the lineup, before and after moving.
- Lineups use season points per game and the league's real slots, never this week's starters.
- The strip is one row above the board, on the Trade board view only.
- Reset restores sliders only, never team type overrides.
- P/V column and tags, League trades, `brief.md` and `summary.json` stay on DP values.
- Suggested deals are not regenerated. The default Ranked order and three-team order stay as built.
- The board stays one self-contained HTML file. No new Python or npm dependencies.

## Review Focus

1. Dragging a slider: the strip must not be rebuilt mid-drag, or the slider loses the pointer. Roster sideways scroll position must also survive each update.
2. Opening a deal from All deals: those handlers rebuild `sel` from scratch and would silently drop saved weights and overrides.
3. A saved board from before this feature, or saved settings that are partial or invalid: must load with defaults, not crash.
4. A trade naming a piece no longer on the roster after a weekly re-run: the lineup calculation must ignore it, as the value totals already do.
5. A roster holding positions with no slot (this league has DB players and no DB slot), or too few players to fill every slot: such players are skipped, unfilled slots score 0.

---

### Task 1: Pricing and lineup logic

**Files:**
- Create: `rebuild/templates/board_weights.js`, `tests/board_weights.test.js`, `tests/__init__.py`, `tests/test_board.py`
- Modify: `rebuild/templates/trade_board.html:251-252`, `rebuild/board.py` (`render`)

**Interfaces:**
- Produces, as browser globals and `module.exports`:
  - `WEIGHT_DEFAULTS = {on: false, steepness: 0.015, rates: {contend: 300, retool: 150, rebuild: 50}, types: {}}`
  - `normalizeWeights(saved) -> weights`: defaults merged with valid saved fields; non-numeric values and types other than contend/retool/rebuild are dropped
  - `curveValue(dp, steepness) -> integer`
  - `bestLineup(players, slots) -> number`: leaves out `ir` and `taxi`, fills narrowest slots first
  - `lineupChange(rid, moves, teamsByRid, slots) -> number`: after minus before; `moves` are `{key, from, to}`
  - `teamReturn(got, sent, lineupAmount) -> integer | null`

- [ ] **Step 1: Commit the work already pending**

```bash
git add rebuild/templates/trade_board.html docs/superpowers
git commit -m "Two-team board layout; custom league weights design and plan"
```

- [ ] **Step 2: Write the failing tests in `tests/board_weights.test.js`, using `node:test`**

```js
test("curve", () => {
  assert.equal(curveValue(0, 0.015), 0);
  assert.ok(Math.abs(curveValue(7846, 0.0235) - 7846) <= 1);
  assert.ok(Math.abs(curveValue(108, 0.0235) - 108) <= 1);
  const ratio = curveValue(1504, 0.015) / curveValue(108, 0.015);   // Skattebo over Gordon
  assert.ok(ratio > 5 && ratio < 5.8);
});
test("best lineup fills flex, skips IR, taxi and slotless positions", () => {
  const p = (pos, ppg, x = {}) => ({pos, ppg, ...x});
  const slots = ["QB", "RB", "WR", "FLEX", "SUPER_FLEX"];
  const players = [p("QB", 20), p("QB", 15), p("RB", 12), p("RB", 10), p("WR", 9), p("DB", 30), p("WR", 50, {ir: true}), p("WR", 40, {taxi: true})];
  assert.equal(bestLineup(players, slots), 66);
  assert.equal(bestLineup([p("QB", 20)], slots), 20);       // unfilled slots score 0
});
test("lineup change counts the return, and IR moves change nothing", () => {
  const T = {1: {players: [{id: "a", pos: "WR", ppg: 10}, {id: "b", pos: "WR", ppg: 6}, {id: "i", pos: "WR", ppg: 20, ir: true}], picks: []},
             2: {players: [{id: "c", pos: "WR", ppg: 8}], picks: []}};
  const mv = (key, from, to) => ({key, from, to});
  assert.equal(lineupChange(1, [mv("p:a", 1, 2)], T, ["WR"]), -4);
  assert.equal(lineupChange(2, [mv("p:a", 1, 2)], T, ["WR"]), 2);
  assert.equal(lineupChange(1, [mv("p:a", 1, 2), mv("p:c", 2, 1)], T, ["WR"]), -2);
  assert.equal(lineupChange(2, [mv("p:i", 1, 2)], T, ["WR"]), 0);
  assert.equal(lineupChange(1, [mv("k:2028-1-9", 1, 2), mv("p:gone", 1, 2)], T, ["WR"]), 0);
});
test("return", () => {
  assert.equal(teamReturn(100, 200, 0), 50);
  assert.equal(teamReturn(100, 200, 100), 100);
  assert.equal(teamReturn(100, 200, -500), 0);
  assert.equal(teamReturn(100, 0, 0), null);
});
test("saved settings", () => {
  assert.deepEqual(normalizeWeights(null), WEIGHT_DEFAULTS);
  const w = normalizeWeights({on: true, steepness: "x", rates: {contend: 100}, types: {3: "contend", 4: "nonsense"}});
  assert.equal(w.on, true); assert.equal(w.steepness, 0.015);
  assert.deepEqual(w.rates, {contend: 100, retool: 150, rebuild: 50});
  assert.deepEqual(w.types, {3: "contend"});
});
```

In `tests/test_board.py`, using `unittest`: `board.render({"league": "L"}, tmp_path)` writes a file containing `function curveValue` and not containing `/*__WEIGHTS_JS__*/`.

- [ ] **Step 3: Run the tests and see them fail**

Run: `node --test tests/ ; .venv/bin/python -m unittest discover tests`
Expected: FAIL, module and function not found.

- [ ] **Step 4: Implement `rebuild/templates/board_weights.js`**

Slot eligibility: `QB, RB, WR, TE, K, DEF` and any other single position are themselves; `FLEX` is RB/WR/TE; `SUPER_FLEX` is QB/RB/WR/TE; `WRRB_FLEX` is RB/WR; `REC_FLEX` is WR/TE; `IDP_FLEX` is DL/LB/DB. End the file with `if (typeof module !== "undefined") module.exports = {...}`.

- [ ] **Step 5: Inline it**

Add `/*__WEIGHTS_JS__*/` as the first line inside the template's `<script>`. In `board.render`, replace it with the contents of `board_weights.js`, read from beside `TEMPLATE`.

- [ ] **Step 6: Run the tests and see them pass**

Run: `node --test tests/ ; .venv/bin/python -m unittest discover tests`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add rebuild/templates/board_weights.js rebuild/templates/trade_board.html rebuild/board.py tests
git commit -m "Pricing and lineup logic for custom league weights"
```

### Task 2: Team types and roster slots in the board data

**Files:**
- Modify: `rebuild/grade.py`, `rebuild/cli.py:109-129`, `rebuild/board.py:60-85`
- Test: `tests/test_board.py`

**Interfaces:**
- Produces: `grade.team_types(league, values, bm, own_bundle, grade_fn=grade) -> {rid: "contend"|"retool"|"rebuild"}`; `board_data(..., team_types=None)`; each team in the data has `"type"`; the data has top-level `"slots"`, the league's `roster_positions` minus `BN`, `IR` and `TAXI`.

- [ ] **Step 1: Write the failing test**

`test_team_types_falls_back`: with `league = SimpleNamespace(team_name={1: "a", 2: "b"})` and a `grade_fn` that returns `{"mode": "contend"}` for rid 1 and raises for rid 2, `team_types(league, None, None, None, grade_fn=fn) == {1: "contend", 2: "retool"}`.

- [ ] **Step 2: Run it and see it fail**

Run: `.venv/bin/python -m unittest tests.test_board`
Expected: FAIL, `team_types` not defined.

- [ ] **Step 3: Implement `team_types`, and pass it through `cli.py` to `board_data`**

Catch exceptions per team, because `grade` can fail for a team with no history row. A missing `team_types` entry becomes `"retool"`.

- [ ] **Step 4: Run tests, then the app, and read the result**

Run: `.venv/bin/python -m unittest tests.test_board && .venv/bin/python -m rebuild --league 1314730205109059584 --team "YouGottaGive"`, then print each team's `type` and the `slots` from `board-data.json`.
Expected: tests pass. `slots` is `QB, RB, RB, WR, WR, WR, TE, FLEX, FLEX, FLEX, SUPER_FLEX, DEF`. YouGottaGive is `rebuild`. Show the user the full list of team types in the task report.

- [ ] **Step 5: Commit**

```bash
git add rebuild tests
git commit -m "Ship each team's graded type and the league's roster slots to the board"
```

### Task 3: Toggle, steepness and re-priced values

**Files:**
- Modify: `rebuild/templates/trade_board.html`

**Interfaces:**
- Consumes: `normalizeWeights`, `curveValue`, `WEIGHT_DEFAULTS`
- Produces, in the template: `W()` returns `sel.weights` (normalized on load); `px(dpValue) -> number` returns the DP value when off and `curveValue` when on. `px` is the only path from a DP value to a displayed value.

- [ ] **Step 1: Capture the baseline**

Rebuild the board before editing. In Chrome, on a local server, save the `innerText` of `#board` and `#compare` for one two-team deal and one three-team deal to the scratchpad.

- [ ] **Step 2: Add the state**

Normalize `sel.weights` on load. Add `weights: sel.weights` to both `sel = {...}` rebuilds in `renderCompare`'s `.open` handlers.

- [ ] **Step 3: Add the strip**

Add `<div id="weights">` between `#tabs` and `#board`. Build it once and never in `render()`: toggle, steepness slider (range 0.005 to 0.035, step 0.0005, showing its value and "DP 0.0235"), Reset. Slider `input` events update `sel.weights` and the readout, save, then call `render()`. Hide the strip outside the Trade board view, and hide the sliders when off. Keep `#rosters.scrollLeft` across each `render()`.

- [ ] **Step 4: Route values through `px`**

`assetOf`, `sum`, `dealPct`, deal variant totals, `itemHtml`, roster rows, pick chips, and the panel header's players and picks totals. With the toggle on, roster rows and pick chips also show the DP value in small muted text ("was 7,846"). Variant totals must be summed from re-priced items, not read from `v.value`. Do not route `sig`, `price_signals` output or `renderHistory` through `px`. With the toggle on, label "Walk away if" text "(at DP values)".

- [ ] **Step 5: Verify in Chrome**

- Toggle off: `innerText` matches the Step 1 baseline exactly.
- Toggle on at 0.0235: every value is within 1 of its DP value.
- Toggle on at 0.015, trade McConkey, Chase Brown and your 2028 first for Lamb and a 2028 second: return is 135% to 137%.
- Drag the slider with the mouse: it keeps tracking and values update as it moves. Scroll rosters sideways first and confirm the position holds.
- Open a deal from All deals, then reload: weights are kept.
- Clear `sel.weights` from localStorage and reload: board loads with the toggle off.

- [ ] **Step 6: Commit**

```bash
git add rebuild/templates/trade_board.html
git commit -m "Custom league weights toggle with a live steepness setting"
```

### Task 4: Lineup cost, rates and team types on the board

**Files:**
- Modify: `rebuild/templates/trade_board.html`

**Interfaces:**
- Consumes: `lineupChange`, `teamReturn`, `px`, `W()`, each team's `type`, `DATA.slots`
- Produces, in the template: `typeOf(rid) -> W().types[rid] || T[rid].type`; `sideOf(rid, moves) -> {got, sent, change, amount, pct}`. When off, `change` and `amount` are 0 and `pct` is the plain return.

- [ ] **Step 1: Add rate sliders to the strip**

Contend, Retool and Rebuild, range 0 to 1,000, step 10, shown as value per weekly point. Reset restores steepness and rates and leaves `types` alone.

- [ ] **Step 2: Add the type dropdown to each roster panel header, shown only with the toggle on**

Options are Contend, Retool and Rebuild, with the app's grade marked "(app)". Choosing the app's grade deletes the override. An override is marked visibly. Changing it saves and calls `render()`.

- [ ] **Step 3: Use `sideOf` in the trade panel**

Each team's block shows its `pct` and, with the toggle on, a line in the form "lineup −3.3 pts/wk, −990". With the toggle on, add "Pure DP: 99%" beside your return, using raw DP values and no lineup amount. Pass only the moves whose pieces still exist (the `R` list) to `lineupChange`.

- [ ] **Step 4: Verify in Chrome**

- Rates at 0: returns match Task 3's.
- Default rates, Lamb to Dirty Birds for Wilson and two firsts: Dirty Birds' block shows a lineup line that counts Lamb coming in. Changing Dirty Birds' type moves its percentage immediately.
- Reset keeps an override; setting the dropdown back to the app's grade clears it. Overrides survive a reload.
- A trade with a player on IR: neither team's lineup line changes when he's added.
- Custom and three-team trades both show lineup lines. Clicking a piece updates them.
- Toggle off: Task 3's baseline still matches.

- [ ] **Step 5: Commit**

```bash
git add rebuild/templates/trade_board.html
git commit -m "Per-trade lineup cost weighted by team type, with board overrides"
```

### Task 5: All deals view and docs

**Files:**
- Modify: `rebuild/templates/trade_board.html` (`renderCompare`), `README.md`, `docs/DESIGN.md`

**Interfaces:**
- Consumes: `sideOf`, `px`, `W()`

- [ ] **Step 1: Use `sideOf` for variant and three-team percentages in `renderCompare`**

Extract the two-team move-building now inside `render()` into `movesOfVariant(d, vname)` and use it in both places. Return and Value sorts use the re-priced numbers. Ranked order, the `#N` and `T#` labels and three-team order are unchanged.

- [ ] **Step 2: Add the notice**

With the toggle on, show one line above the cards: "Custom league weights on: steepness 0.015, lineup rates 300 / 150 / 50 per point." Use the current values, and add a "Change on the board" link that switches view.

- [ ] **Step 3: Document it**

README: what the toggle does and that defaults are DP. `docs/DESIGN.md`: the formula, the lineup calculation, why default steepness is 0.015 with the caveat, and that rates are placeholders.

- [ ] **Step 4: Verify**

Run: `node --test tests/ ; .venv/bin/python -m unittest discover tests`
Expected: all pass.

In Chrome: toggle off, `#compare` matches the Task 3 baseline. Toggle on, percentages change, the notice appears, and a card's Target return equals the same deal's return on the board. No console errors in either view. Then stop the local server and close the test tab.

- [ ] **Step 5: Commit**

```bash
git add rebuild/templates/trade_board.html README.md docs/DESIGN.md
git commit -m "Custom league weights in the All deals view, and docs"
```
