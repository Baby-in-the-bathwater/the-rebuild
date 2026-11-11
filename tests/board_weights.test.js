// Pricing and lineup logic for the board's custom league weights. Run with: node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const {WEIGHT_DEFAULTS, normalizeWeights, curveValue, bestLineup, lineupChange, teamReturn} = require("../rebuild/templates/board_weights.js");

test("curve re-prices from the DP value alone", () => {
  assert.equal(curveValue(0, 0.015), 0);
  assert.ok(Math.abs(curveValue(7846, 0.0235) - 7846) <= 1);
  assert.ok(Math.abs(curveValue(108, 0.0235) - 108) <= 1);
  const ratio = curveValue(1504, 0.015) / curveValue(108, 0.015);   // Skattebo over Gordon
  assert.ok(ratio > 5 && ratio < 5.8, `ratio ${ratio}`);
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

test("return floors the top at zero and is null when nothing is sent", () => {
  assert.equal(teamReturn(100, 200, 0), 50);
  assert.equal(teamReturn(100, 200, 100), 100);
  assert.equal(teamReturn(100, 200, -500), 0);
  assert.equal(teamReturn(100, 0, 0), null);
});

test("saved settings merge onto defaults and drop invalid fields", () => {
  assert.deepEqual(normalizeWeights(null), WEIGHT_DEFAULTS);
  const w = normalizeWeights({on: true, steepness: "x", rates: {contend: 100}, types: {3: "contend", 4: "nonsense"}});
  assert.equal(w.on, true);
  assert.equal(w.steepness, 0.015);
  assert.deepEqual(w.rates, {contend: 100, retool: 150, rebuild: 50});
  assert.deepEqual(w.types, {3: "contend"});
});
