// Custom league weights: re-pricing on a different curve steepness, and the lineup cost of a trade.
// Inlined into the trade board at render time, and loaded by node for tests (module.exports at the end).

// DynastyProcess values are almost exactly DP_SCALE * e^(-DP_STEEPNESS * rank), so a value can be moved to another
// steepness from the value alone: new = DP_SCALE * (value / DP_SCALE) ^ (steepness / DP_STEEPNESS).
const DP_SCALE = 10467, DP_STEEPNESS = 0.0235;
const TEAM_TYPES = ["contend", "retool", "rebuild"];
const WEIGHT_DEFAULTS = {on: false, steepness: 0.015, rates: {contend: 300, retool: 150, rebuild: 50}, types: {}};

function normalizeWeights(saved) {
  const s = saved && typeof saved === "object" ? saved : {};
  const num = (v, d) => (typeof v === "number" && isFinite(v) && v >= 0 ? v : d);
  const rates = {};
  for (const t of TEAM_TYPES) rates[t] = num(s.rates && s.rates[t], WEIGHT_DEFAULTS.rates[t]);
  const types = {};
  for (const [rid, t] of Object.entries(s.types && typeof s.types === "object" ? s.types : {})) if (TEAM_TYPES.includes(t)) types[rid] = t;
  return {on: s.on === true, steepness: num(s.steepness, WEIGHT_DEFAULTS.steepness) || WEIGHT_DEFAULTS.steepness, rates, types};
}

function curveValue(dp, steepness) {
  if (!dp || dp <= 0) return 0;
  return Math.round(DP_SCALE * Math.pow(dp / DP_SCALE, steepness / DP_STEEPNESS));
}

// Which positions each lineup slot takes. Any slot not listed takes only its own position (QB, K, DEF, DL, ...).
const SLOT_TAKES = {FLEX: ["RB", "WR", "TE"], SUPER_FLEX: ["QB", "RB", "WR", "TE"], WRRB_FLEX: ["RB", "WR"], REC_FLEX: ["WR", "TE"], IDP_FLEX: ["DL", "LB", "DB"]};
const takes = slot => SLOT_TAKES[slot] || [slot];

// Season points per game of the best lineup: players on IR or taxi sit out, narrowest slots are filled first,
// each with the best player left who fits. Slots nobody fits score 0.
function bestLineup(players, slots) {
  const left = players.filter(p => !p.ir && !p.taxi).sort((a, b) => (b.ppg || 0) - (a.ppg || 0));
  const order = [...slots].sort((a, b) => takes(a).length - takes(b).length);
  let total = 0;
  for (const slot of order) {
    const i = left.findIndex(p => takes(slot).includes(p.pos));
    if (i >= 0) total += left.splice(i, 1)[0].ppg || 0;
  }
  return total;
}

// After minus before for one team: it loses the players it sends and gains the ones it receives. Picks and pieces
// no longer on the sending roster are ignored. A moved player keeps his IR or taxi status, so he scores for no one.
function lineupChange(rid, moves, teamsByRid, slots) {
  const team = teamsByRid[rid];
  if (!team) return 0;
  const playerOf = m => {
    if (!m.key.startsWith("p:") || !teamsByRid[m.from]) return null;
    return teamsByRid[m.from].players.find(p => String(p.id) === m.key.slice(2)) || null;
  };
  const out = new Set(moves.filter(m => m.from === rid).map(playerOf).filter(Boolean));
  const inn = moves.filter(m => m.to === rid && m.from !== rid).map(playerOf).filter(Boolean);
  const before = bestLineup(team.players, slots);
  const after = bestLineup([...team.players.filter(p => !out.has(p)), ...inn], slots);
  return Math.round((after - before) * 10) / 10;
}

function teamReturn(got, sent, lineupAmount) {
  if (!sent) return null;
  return Math.round(Math.max(0, got + (lineupAmount || 0)) / sent * 100);
}

if (typeof module !== "undefined") module.exports = {WEIGHT_DEFAULTS, TEAM_TYPES, normalizeWeights, curveValue, bestLineup, lineupChange, teamReturn};
