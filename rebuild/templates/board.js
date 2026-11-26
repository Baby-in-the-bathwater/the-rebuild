const DATA = window.__BOARD_DATA__;
const ME = DATA.me_rid;
const T = Object.fromEntries(DATA.teams.map(t => [t.rid, t]));
const me = T[ME];
const fmt = n => (n || 0).toLocaleString("en-US");
const POS = ["QB", "RB", "WR", "TE", "K", "DEF"];
const PC = {QB: "var(--qb)", RB: "var(--rb)", WR: "var(--wr)", TE: "var(--te)", K: "var(--k)", DEF: "var(--def)"};
const ord = n => n + (["th","st","nd","rd"][(n%10>3||[11,12,13].includes(n%100))?0:n%10]);
const pad = s => "1." + String(s).padStart(2, "0");
// Text from the data (names, labels, notes) goes into HTML strings only through esc: a team name is text, never markup.
const esc = s => (s == null ? "" : String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]));
// Sleeper DMs go by username, so show it beside the team name unless the team has no custom name (then the name already is the username).
const handle = t => (t.owner && t.owner !== "(orphan)" && t.owner !== t.name ? t.owner : "");
const who = t => (handle(t) ? `<span class="who">(${esc(handle(t))})</span>` : "");
const SEASONS = DATA.pick_seasons;
const dealsFor = rid => DATA.deals.filter(d => d.cp_rid === rid);
const MULTI = DATA.multi || [];
const multiFor = rid => MULTI.map((m, i) => ({m, i})).filter(x => x.m.teams.includes(rid));
const withDeals = [...new Set([...DATA.deals.map(d => d.cp_rid), ...MULTI.flatMap(m => m.teams.filter(r => r !== ME))])];
const tname = rid => (T[rid] ? T[rid].name : "Team " + rid);
const others = [...withDeals, ...DATA.teams.map(t => t.rid).filter(r => r !== ME && !withDeals.includes(r))];

let sel = {team: others[0], deal: 0, v: null};
try { const s = JSON.parse(localStorage.getItem("rebuild-board-" + DATA.league_id) || "null"); if (s && T[s.team] && s.team !== ME) sel = s; } catch (e) {}
if (sel.custom && !Array.isArray(sel.custom.moves)) sel.custom = null;   // saved by an older board (send/recv lists)
// Custom league weights (off by default): sel.weights holds the toggle, the steepness, the lineup rates and team type
// overrides. px() is the only way a DP value reaches the screen: unchanged when off, re-priced on the chosen curve when on.
sel.weights = normalizeWeights(sel.weights);
const W = () => sel.weights || (sel.weights = normalizeWeights(null));
const px = v => (W().on ? curveValue(v || 0, W().steepness) : (v || 0));
const was = v => (W().on ? `<small>was ${fmt(v)}</small>` : "");
const save = () => { try { localStorage.setItem("rebuild-board-" + DATA.league_id, JSON.stringify(sel)); } catch (e) {} };

// Custom trades: sel.custom is null (show the drafted deal) or {moves: [{key, from, to}], base} built by clicking rows and pick chips.
// Keys are "p:<player id>" or "k:<pick key>". A click on your roster sends the piece to the team on screen; a click on theirs
// sends it to you; each piece's "to" can be changed to any team, which is how a third (or fourth) team joins. `base` names the
// drafted three-team deal the trade was loaded from ("m<index>"), so the rail can say whether it has been edited.
const keyOf = it => (it.kind === "player" ? "p:" + it.id : "k:" + it.key);
const movesOfDeal = m => m.moves.map(x => ({key: keyOf(x), from: x.from, to: x.to}));
const sameMoves = (a, b) => JSON.stringify(a.map(m => [m.key, m.from, m.to]).sort()) === JSON.stringify(b.map(m => [m.key, m.from, m.to]).sort());
const pickLabel = pk => `${pk.season} R${pk.round}` + (pk.own ? "" : ` via ${pk.orig}`) + (pk.proj_slot && pk.round === 1 ? ` (${pad(pk.proj_slot)})` : "");
function assetOf(team, key) {
  const id = key.slice(2);
  if (key.startsWith("p:")) {
    const p = team.players.find(p => String(p.id) === id);
    return p && {kind: "player", id: p.id, label: `${p.name} (${p.pos}, ${p.age ?? "?"})`, value: px(p.value), dp: p.value || 0};
  }
  const pk = team.picks.find(p => p.key === id);
  return pk && {kind: "pick", key: pk.key, label: pickLabel(pk), value: px(pk.value), dp: pk.value || 0};
}
let refocus = null;
let tabTeam = null;   // the team whose tab was last brought into view

// All-deals view: every drafted deal as a card, variants side by side, in the brief's ranked order by default.
const PL = Object.fromEntries(DATA.teams.flatMap(t => t.players.map(p => [String(p.id), p])));
const sum = items => items.reduce((a, b) => a + px(b.value), 0);   // items carry DP values
const dealAsset = d => d.fixed.map(x => x.label.replace(/ \(.*\)$/, "")).join(" + ");
// The moves of a drafted two-team deal's variant: what you send goes to the counterparty, what it sends comes to you.
function movesOfVariant(d, vname) {
  const varItems = d.vars[vname].items;
  const [sendItems, recvItems] = d.fixed_side === "sends" ? [d.fixed, varItems] : [varItems, d.fixed];
  return [...sendItems.map(i => ({key: keyOf(i), from: ME, to: d.cp_rid})), ...recvItems.map(i => ({key: keyOf(i), from: d.cp_rid, to: ME}))];
}
const dealPct = (d, vname) => {      // value you receive over value you send, for either deal direction
  if (W().on) return sideOf(ME, movesOfVariant(d, vname)).pct;   // re-priced, with your lineup cost
  const f = sum(d.fixed), v = sum(d.vars[vname].items);
  const [out, inn] = d.fixed_side === "sends" ? [f, v] : [v, f];
  return out ? Math.round(inn / out * 100) : null;
};
const dpNote = () => (W().on ? " (at DP values)" : "");
const pctClass = p => (p === null ? "" : p >= 100 ? "good" : p < 85 ? "bad" : "");
const tgtName = d => (d.vars.Target ? "Target" : Object.keys(d.vars)[0]);
function itemHtml(it) {
  if (it.kind === "player") {
    const p = PL[String(it.id)], pos = p ? p.pos : "";
    return `<li><span class="badge" style="background:${PC[pos] || "var(--k)"}">${esc(pos)}</span><span class="lb" title="${esc(it.label)}">${esc(it.label)}</span><span class="vv">${fmt(px(it.value))}</span></li>`;
  }
  const r = (it.label.match(/ R(\d)/) || [])[1] || "";
  return `<li><span class="badge" style="background:${r === "1" ? "var(--accent)" : "var(--pick)"}">R${r}</span><span class="lb" title="${esc(it.label)}">${esc(it.label)}</span><span class="vv">${fmt(px(it.value))}</span></li>`;
}
const weightsNote = () => {
  if (!W().on) return "";
  const w = W();
  return `<p class="wnote"><b>Custom league weights on:</b> steepness ${w.steepness.toFixed(4)}, lineup rates ${w.rates.contend} / ${w.rates.retool} / ${w.rates.rebuild} per point (contend / retool / rebuild). Returns include each team's lineup cost.<a class="wlink" role="button" tabindex="0">Change on the board</a></p>`;
};
function renderCompare() {
  const cmp = sel.cmp || (sel.cmp = {sort: "rank", asset: "all"});
  const assets = [...new Set([...DATA.deals.map(dealAsset), ...MULTI.map(m => m.asset)])];
  const nFor = a => DATA.deals.filter(d => dealAsset(d) === a).length + MULTI.filter(m => m.asset === a).length;
  if (cmp.asset !== "all" && !assets.includes(cmp.asset)) cmp.asset = "all";
  let rows = DATA.deals.map((d, i) => ({d, i}));
  if (cmp.asset !== "all") rows = rows.filter(r => dealAsset(r.d) === cmp.asset);
  if (cmp.sort === "return") rows.sort((a, b) => (dealPct(b.d, tgtName(b.d)) ?? -1) - (dealPct(a.d, tgtName(a.d)) ?? -1) || a.i - b.i);
  else if (cmp.sort === "team") rows.sort((a, b) => a.d.counterparty.localeCompare(b.d.counterparty) || a.i - b.i);
  else if (cmp.sort === "value") rows.sort((a, b) => sum(b.d.vars[tgtName(b.d)].items) - sum(a.d.vars[tgtName(a.d)].items) || a.i - b.i);

  const el = document.getElementById("compare");
  const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`;
  const h = [`<div class="ctl"><label>Sort ${`<select id="cmp-sort">${opt("rank", "Ranked (as in the brief)", cmp.sort)}${opt("return", "Target return, high to low", cmp.sort)}${opt("value", "Target value, high to low", cmp.sort)}${opt("team", "Team", cmp.sort)}</select>`}</label>
    <label>${DATA.deals.some(d => d.fixed_side === "sends") ? "Selling" : "Buying"} <select id="cmp-asset">${opt("all", `All (${DATA.deals.length + MULTI.length})`, cmp.asset)}${assets.map(a => opt(a, `${a} (${nFor(a)})`, cmp.asset)).join("")}</select></label>
    <span>Return is value received over value sent. Green at 100%+, red under 85%.</span></div>${weightsNote()}<div class="cards">`];
  for (const {d, i} of rows) {
    const t = T[d.cp_rid], sells = d.fixed_side === "sends";
    const vnames = Object.keys(d.vars), tn = tgtName(d);
    const fit = (d.title.match(/\(needs (\w+)\)/) || [])[1];
    h.push(`<article class="dcard"><header><span class="rk">#${i + 1}</span><div>
      <div class="dt">${sells ? `${esc(dealAsset(d))}<span class="arrow">→</span>${esc(t.name)}` : `${esc(dealAsset(d))}<span class="arrow">←</span>${esc(t.name)}`}${who(t)}</div>
      <div class="dm"><span>${sells ? "you send" : "you receive"} <b>${d.fixed.map(x => esc(x.label)).join(", ")}</b> · <b>${fmt(sum(d.fixed))}</b></span><span><b>${t.wins}-${t.losses}</b> · ${ord(t.rank)} of ${DATA.teams.length}</span>${fit ? `<span class="fit">needs ${fit}</span>` : ""}</div>
      </div><button class="open" type="button" data-i="${i}">Open on board</button></header><div class="vgrid">`);
    vnames.forEach((n, k) => {
      const v = d.vars[n], p = dealPct(d, n);
      const prev = k ? d.vars[vnames[k - 1]] : null;
      const same = prev && prev.items.map(keyOf).join() === v.items.map(keyOf).join();
      h.push(`<div class="vcol${n === tn ? " tgt" : ""}"><div class="vh"><span>${esc(n)}</span><span class="p ${pctClass(p)}">${p === null ? "–" : p + "%"}</span></div>
        ${same ? `<div class="same">Same package as ${esc(vnames[k - 1])}</div>` : `<ul>${v.items.map(itemHtml).join("")}</ul>`}
        <div class="vt"><span>${sells ? "you receive" : "you send"}</span><b>${fmt(sum(v.items))}</b></div></div>`);
    });
    h.push(`</div><footer><b>Walk away if</b> ${esc(d.walk)}${dpNote()}.</footer></article>`);
  }
  h.push(`</div>`);
  const ms = MULTI.map((m, i) => ({m, i})).filter(x => cmp.asset === "all" || x.m.asset === cmp.asset);
  if (ms.length) {
    h.push(`<h2 class="sect">Three-team deals (${ms.length})</h2><p class="hint">A buyer that cannot pay in what you want sends players you do not want to a third team, which pays you instead. Kept only when both other teams land between 87% and 115% of what they send and your return beats the buyer's best two-team package. Ranked by the quality of your return.</p><div class="cards">`);
    for (const {m, i} of ms) {
      const [, A, B] = m.teams;
      const got = rid => m.moves.filter(x => x.to === rid), gave = rid => m.moves.filter(x => x.from === rid);
      h.push(`<article class="dcard"><header><span class="rk">T${i + 1}</span><div>
        <div class="dt">${esc(m.asset)}<span class="arrow">→</span>${esc(tname(A))}${who(T[A])}<span class="arrow">+</span>${esc(tname(B))}${who(T[B])}</div>
        <div class="dm"><span>${esc(m.why)}</span></div></div><button class="open" type="button" data-m="${i}">Open on board</button></header><div class="vgrid">`);
      for (const rid of m.teams) {
        const g = sum(got(rid)), sv = sum(gave(rid)), p = W().on ? sideOf(rid, movesOfDeal(m)).pct : (sv ? Math.round(g / sv * 100) : null);
        h.push(`<div class="vcol${rid === ME ? " tgt" : ""}"><div class="vh"><span>${rid === ME ? "You get" : esc(tname(rid)) + " gets"}</span><span class="p ${pctClass(p)}">${p === null ? "–" : p + "%"}</span></div>
          <ul>${got(rid).map(x => itemHtml(x).replace("</span><span class=\"vv\">", `<small>from ${x.from === ME ? "you" : esc(tname(x.from))}</small></span><span class="vv">`)).join("")}</ul>
          <div class="vt"><span>gets / sends</span><b>${fmt(g)} / ${fmt(sv)}</b></div></div>`);
      }
      h.push(`</div></article>`);
    }
    h.push(`</div>`);
  }
  el.innerHTML = h.join("");
  const wl = el.querySelector(".wlink");
  if (wl) wl.onclick = wl.onkeydown = e => { if (e.type === "keydown" && e.key !== "Enter") return; sel.view = "board"; save(); render(); document.getElementById("weights").scrollIntoView({block: "center"}); };
  el.querySelector("#cmp-sort").onchange = e => { cmp.sort = e.target.value; save(); render(); };
  el.querySelector("#cmp-asset").onchange = e => { cmp.asset = e.target.value; save(); render(); };
  el.querySelectorAll(".open[data-m]").forEach(b => b.onclick = () => {
    const m = MULTI[+b.dataset.m];
    sel = {team: m.teams[1], deal: 0, v: null, custom: {moves: movesOfDeal(m), base: "m" + b.dataset.m}, view: "board", cmp, hist: sel.hist, weights: sel.weights};
    save(); render();
    document.getElementById("board").scrollIntoView({behavior: "smooth", block: "start"});
  });
  el.querySelectorAll(".open[data-i]").forEach(b => b.onclick = () => {
    const d = DATA.deals[+b.dataset.i];
    sel = {team: d.cp_rid, deal: dealsFor(d.cp_rid).indexOf(d), v: null, custom: null, view: "board", cmp, hist: sel.hist, weights: sel.weights};
    save(); render();
    document.getElementById("board").scrollIntoView({behavior: "smooth", block: "start"});
  });
}

// A team's type: the user's override if set, else the app's grade. Its lineup rate prices each weekly point a trade adds or costs.
const typeOf = rid => W().types[rid] || (T[rid] && T[rid].type) || "retool";
// One team's side of a trade given its moves ({key, from, to}): value in and out (priced), the change in its best lineup's
// weekly points, that change priced at its type's rate, and its return. With weights off there is no lineup amount.
function sideOf(rid, moves) {
  const live = moves.map(m => ({...m, a: T[m.from] && assetOf(T[m.from], m.key)})).filter(m => m.a);
  const got = live.filter(m => m.to === rid).reduce((t, m) => t + m.a.value, 0);
  const sent = live.filter(m => m.from === rid).reduce((t, m) => t + m.a.value, 0);
  const change = W().on ? lineupChange(rid, live, T, DATA.slots || []) : 0;
  const amount = Math.round(change * (W().rates[typeOf(rid)] || 0));
  return {got, sent, change, amount, pct: teamReturn(got, sent, amount)};
}
const lineupLine = sd => (W().on ? `<div class="mt lu">lineup <b class="${sd.change > 0 ? "good" : sd.change < 0 ? "bad" : ""}">${sd.change ? (sd.change > 0 ? "+" : "−") + Math.abs(sd.change).toFixed(1) + " pts/wk" : "no change"}</b>${sd.amount ? `, ${sgn(sd.amount)}` : ""}</div>` : "");
const typeSel = team => {
  if (!W().on) return "";
  const t = typeOf(team.rid), ovr = !!W().types[team.rid], name = {contend: "Contend", retool: "Retool", rebuild: "Rebuild"};
  return `<select class="ttype${ovr ? " ovr" : ""}" data-rid="${team.rid}" aria-label="${esc(team.name)} team type" title="${ovr ? "Set by you; choose the (app) option to go back to the app's grade" : "The app's grade; change it if the owner sees it differently"}">${TEAM_TYPES.map(k => `<option value="${k}"${k === t ? " selected" : ""}>${name[k]}${k === team.type ? " (app)" : ""}</option>`).join("")}</select>`;
};
const pickTotal = team => (W().on ? team.picks.reduce((a, p) => a + px(p.value), 0) : team.pick_value);
function panel(team, hl, isMe, opts = {}) {
  const h = [];
  h.push(`<div class="phead">${opts.removable ? `<button class="unpin" type="button" data-rid="${team.rid}" aria-label="Hide ${esc(team.name)}" title="Hide this roster">×</button>` : ""}<h2>${esc(team.name)}${who(team)}${isMe ? ' <span style="color:var(--accent)">· you</span>' : ""}${opts.focus ? '<span class="focus">selected</span>' : ""}${typeSel(team)}</h2><div class="meta"><span><b>${team.wins}-${team.losses}</b> · ${ord(team.rank)} of ${DATA.teams.length}</span>${SEASONS.length ? `<span>proj. ${esc(SEASONS[0])} pick <b>${pad(team.proj_slot)}</b></span>` : ""}<span>startable <b>${team.startable}</b></span><span>core age <b>${team.core_age ? team.core_age.toFixed(1) : "–"}</b></span><span>players <b>${fmt(W().on ? team.players.reduce((a, p) => a + px(p.value), 0) : team.player_value)}</b></span><span>picks <b>${fmt(pickTotal(team))}</b></span></div></div>`);
  h.push(`<div class="cols"><span>Pos</span><span>Player</span><span>Team</span><span>Age</span><span>PPG</span><span title="Production vs price: rank at the position by PPG against rank by value. + produces better than priced.">P/V</span><span>Value</span></div>`);
  for (const pos of POS) {
    const ps = team.players.filter(p => p.pos === pos);
    if (!ps.length) continue;
    h.push(`<div class="group"><div class="gh">${pos}<span class="bar" style="background:${PC[pos]}"></span><span>${ps.length}</span></div>`);
    for (const p of ps) {
      const m = hl.players[p.id];
      const cls = isMe && DATA.ledger[p.id] ? " " + esc(DATA.ledger[p.id]) : "";
      h.push(`<div class="row${m ? " hl " + m : ""}${cls}" data-id="${esc(p.id)}" data-key="p:${esc(p.id)}" role="button" tabindex="0" aria-pressed="${!!m}"><span class="badge" style="background:${PC[pos]}">${pos}</span><span class="nm">${esc(p.name)}${p.ir ? '<span class="tag ir">IR</span>' : (p.inj ? `<small>${esc(p.inj)}</small>` : "")}${p.taxi ? '<span class="tag tx">TAXI</span>' : ""}${p.startable ? '<span class="tag st">ST</span>' : ""}${p.sig && p.sig.tag === "buy" ? '<span class="tag bl">BUY LOW</span>' : ""}${p.sig && p.sig.tag === "sell" ? '<span class="tag sh">SELL HIGH</span>' : ""}</span><span class="stats"><span class="num">${esc(p.team)}</span><span class="num">${p.age != null ? `<span class="u">age </span>${esc(p.age)}` : ""}</span><span class="num ppg${p.startable ? " good" : ""}">${p.gp ? p.ppg.toFixed(1) : "–"}<span class="u"> ppg</span></span>${pvCell(p)}</span><span class="num val">${p.value ? fmt(px(p.value)) + was(p.value) : "–"}</span></div>`);
    }
    h.push(`</div>`);
  }
  if (SEASONS.length) {
  h.push(`<div class="picks"><div class="gh">Draft picks<span class="bar" style="background:var(--pick)"></span><span>${fmt(pickTotal(team))}</span></div>`);
  for (const yr of SEASONS) {
    const ps = team.picks.filter(p => p.season === yr);
    h.push(`<div class="season"><div class="yr">${esc(yr)}</div><div class="chips">`);
    if (!ps.length) h.push(`<span class="none">none</span>`);
    for (const p of ps) {
      const m = hl.picks[p.key];
      h.push(`<span class="chip${m ? " hl " + m : ""}" data-key="k:${esc(p.key)}" role="button" tabindex="0" aria-pressed="${!!m}"><span class="r r${p.round}">R${p.round}</span>${p.own ? "own" : "via " + esc(p.orig)}${p.proj_slot && p.round === 1 ? `<small>${pad(p.proj_slot)}</small>` : ""}<span class="v">${fmt(px(p.value))}${was(p.value)}</span></span>`);
    }
    h.push(`</div></div>`);
  }
  h.push(`</div>`);
  }
  return h.join("");
}

function pvCell(p) {
  const s = p.sig;
  if (!s) return `<span class="num pv" title="Fewer than 4 games with points: no production read yet"><span class="u">P/V </span>–</span>`;
  const dir = s.gap > 0 ? " up" : (s.gap < 0 ? " down" : "");
  const tip = `${p.pos}${s.prod} by PPG, ${p.pos}${s.price} by value (of ${s.n} rostered ${p.pos}s with 4+ games)`;
  return `<span class="num pv${dir}${s.tag ? " tagged" : ""}" title="${esc(tip)}"><span class="u">P/V </span>${s.gap > 0 ? "+" : ""}${s.gap}</span>`;
}

// League trades view: how the league prices things, who trades well, and every trade priced then and now.
const sgn = n => (n > 0 ? "+" : n < 0 ? "−" : "") + fmt(Math.abs(Math.round(n)));
const pctCls = p => (p === null || p === undefined ? "mid" : p >= 108 ? "good" : p <= 92 ? "bad" : "mid");
function renderHistory() {
  const H = DATA.trade_history, st = sel.hist || (sel.hist = {sort: "net_now", dir: -1, uid: "all", season: "all"});
  const el = document.getElementById("history");
  const h = [];

  // 1. how the league prices things
  const M = H.market;
  const mrow = (label, r) => `<tr><td class="l">${esc(label)}</td><td data-l="Trades">${r.trades}</td><td data-l="Value sold">${r.value !== undefined ? fmt(r.value) : ""}</td><td data-l="Got back" class="${pctCls(r.pct)}">${r.pct === null ? "–" : r.pct + "%"}</td><td data-l="Read" class="l">${esc(r.read)}</td></tr>`;
  h.push(`<div class="hsec"><h2>How this league trades</h2>
    <p class="hint">For each kind of asset, what sellers got back, against the DynastyProcess value the week of the trade (${M.trades} two-team trades). Over 100%: this league pays more than market, so it is a good thing to sell here. Under 100%: it goes cheap here, so it is a good thing to buy. Fewer than 5 trades is marked thin.</p>
    <div class="tw"><table class="ht"><thead><tr><th>When someone sells</th><th>Trades</th><th>Value sold</th><th>Got back</th><th class="l">Read</th></tr></thead><tbody>
    ${M.rows.map(r => mrow(r.label, r)).join("")}
    ${mrow("A stud for 2+ smaller pieces", {...M.consolidation, value: undefined})}
    </tbody></table></div>
    <p class="hint">Later-round picks are mostly throw-ins, so their number moves with whatever deal they were added to. Each side's return is spread over what it sent by value, so one lopsided trade can tilt a small category.</p></div>`);

  // 2. who trades well
  const cols = [["manager", "Manager", 1], ["trades", "Trades", -1], ["won", "Won-lost-even", -1], ["pct_then", "Return at trade", -1], ["net_then", "Net value at trade", -1], ["net_now", "Net value today", -1], ["pts", "Net starter pts", -1]];
  const rows = [...H.managers].sort((a, b) => {
    const k = st.sort, av = a[k] ?? -Infinity, bv = b[k] ?? -Infinity;
    return (typeof av === "string" ? av.localeCompare(bv) : (av - bv)) * st.dir;
  });
  h.push(`<div class="hsec"><h2>Who trades well</h2>
    <p class="hint">Won-lost-even uses today's values: a side wins when it got 10% and 150+ value more than it gave. Return at trade is everything received over everything sent, at the values of each trade's week. Net starter points: what a manager's acquisitions scored in their starting lineup since, minus what they gave up scored in the other team's. Click a manager to filter the trades below.</p>
    <div class="tw"><table class="ht lb"><thead><tr>${cols.map(([k, l, d]) => `<th${st.sort === k ? ` aria-sort="${st.dir > 0 ? "ascending" : "descending"}"` : ""}><button type="button" data-k="${k}" data-d="${d}">${l}${st.sort === k ? (st.dir > 0 ? " ▲" : " ▼") : ""}</button></th>`).join("")}</tr></thead><tbody>
    ${rows.map(r => `<tr data-uid="${esc(r.uid)}" class="${r.uid === DATA.me_uid ? "me" : ""}${st.uid === r.uid ? " on" : ""}"><td class="l"><b>${esc(r.manager)}</b>${r.uid === DATA.me_uid ? ' <span style="color:var(--accent)">· you</span>' : ""}<small>${r.teams.filter(t => t !== r.manager).map(t => esc(t)).join(" · ")}</small></td>
      <td data-l="Trades">${r.trades}</td><td data-l="Won-lost-even">${r.won}-${r.lost}-${r.even}</td><td data-l="Return at trade" class="${pctCls(r.pct_then)}">${r.pct_then === null ? "–" : r.pct_then + "%"}</td>
      <td data-l="Net value at trade" class="${r.net_then > 0 ? "good" : r.net_then < 0 ? "bad" : "mid"}">${sgn(r.net_then)}</td><td data-l="Net value today" class="${r.net_now > 0 ? "good" : r.net_now < 0 ? "bad" : "mid"}">${sgn(r.net_now)}</td>
      <td data-l="Net starter pts" class="${r.pts > 0 ? "good" : r.pts < 0 ? "bad" : "mid"}">${sgn(r.pts)}</td></tr>`).join("")}
    </tbody></table></div></div>`);

  // 3. every trade
  const seasons = [...new Set(H.trades.map(t => t.season))].sort((a, b) => b - a);
  const opt = (v, label, cur) => `<option value="${esc(v)}"${String(v) === String(cur) ? " selected" : ""}>${esc(label)}</option>`;
  let list = H.trades;
  if (st.uid !== "all") list = list.filter(t => t.sides.some(s => s.uid === st.uid));
  if (st.season !== "all") list = list.filter(t => String(t.season) === String(st.season));
  const mgrs = [...H.managers].sort((a, b) => a.manager.localeCompare(b.manager));
  h.push(`<div class="hsec"><h2>Trades</h2><div class="ctl">
    <label>Manager <select id="h-uid">${opt("all", "Everyone", st.uid)}${mgrs.map(m => opt(m.uid, `${m.manager} (${m.trades})`, st.uid)).join("")}</select></label>
    <label>Season <select id="h-season">${opt("all", "All", st.season)}${seasons.map(y => opt(y, y, st.season)).join("")}</select></label>
    <span>${list.length} trade${list.length === 1 ? "" : "s"} · values shown as then → today</span></div><div class="tlist">`);
  const itemLi = a => {
    if (a.kind === "player") return `<li><span class="badge" style="background:${PC[a.pos] || "var(--k)"}">${esc(a.pos)}</span><span class="lb">${esc(a.label)}${a.age ? `<small>${Math.floor(a.age)}</small>` : ""}</span><span class="vv">${fmt(a.then)} → <b>${fmt(a.now)}</b></span></li>`;
    return `<li><span class="badge" style="background:${a.round === 1 ? "var(--accent)" : "var(--pick)"}">R${a.round}</span><span class="lb">${esc(a.label)}${a.became ? `<small>→ ${esc(a.became)}</small>` : ""}</span><span class="vv">${fmt(a.then)} → <b>${fmt(a.now)}</b></span></li>`;
  };
  for (const t of list) {
    const byRid = Object.fromEntries(t.sides.map(s => [s.rid, s]));
    const wNow = t.winner_now != null ? byRid[t.winner_now] : null, wThen = t.winner_then != null ? byRid[t.winner_then] : null;
    const early = t.days_ago < 56;
    const mine = t.sides.some(s => s.uid === DATA.me_uid);
    h.push(`<article class="tcard${mine ? " mine" : ""}"><header><span><b>${esc(t.date)}</b> · ${esc(t.season)} week ${t.week} · ${t.values_asof ? `values of ${esc(t.values_asof)}` : "no values from then"}</span>
      <span>${!t.values_asof ? "Unpriced at the time" : wThen ? `${esc(wThen.manager)} won at the time` : "Fair at the time"} · <span class="vbadge${wNow ? " win" : ""}">${wNow ? `${esc(wNow.manager)} wins today` : "Even today"}${early ? " (early)" : ""}</span></span></header><div class="tsides">`);
    for (const s of t.sides) {
      h.push(`<div class="tside${wNow && wNow === s ? " won" : ""}"><div class="tsh"><b>${esc(s.team)}</b>${s.team !== s.manager ? ` <small>(${esc(s.manager)})</small>` : ""} <small>gets</small></div>
        <ul>${s.gets.map(itemLi).join("") || '<li><span></span><span class="lb" style="color:var(--muted)">nothing</span><span></span></li>'}</ul>
        ${s.faab ? `<div class="hint">${s.faab > 0 ? "+" : "−"}$${Math.abs(s.faab)} FAAB (not valued)</div>` : ""}
        <div class="tst"><span>At the time</span><span><b>${fmt(s.got_then)}</b> for ${fmt(s.gave_then)} · <span class="${pctCls(s.pct_then)}">${s.pct_then === null ? "–" : s.pct_then + "%"}</span></span>
        <span>Today</span><span><b>${fmt(s.got_now)}</b> for ${fmt(s.gave_now)} · <span class="${pctCls(s.pct_now)}">${s.pct_now === null ? "–" : s.pct_now + "%"}</span></span>
        <span>Starter pts</span><span><b>${s.pts.toFixed(1)}</b> since, for this team</span></div></div>`);
    }
    h.push(`</div></article>`);
  }
  h.push(`</div><p class="hint">Picks are priced at the time by their exact slot when that draft was next, mid-round the season after, flat beyond. Today a drafted pick is worth the player taken with it; an undrafted one is priced like the board's picks. FAAB is not valued. Trades from before the values feed began (February 2019) are shown but not priced at the time. Values only: a deal that won a title can still lose on today's values.</p></div>`);
  el.innerHTML = h.join("");

  el.querySelectorAll(".ht.lb th button").forEach(b => b.onclick = () => {
    const k = b.dataset.k;
    st.dir = st.sort === k ? -st.dir : +b.dataset.d;
    st.sort = k; save(); render();
  });
  el.querySelectorAll(".ht.lb tbody tr").forEach(r => r.onclick = () => { st.uid = st.uid === r.dataset.uid ? "all" : r.dataset.uid; save(); render(); });
  el.querySelector("#h-uid").onchange = e => { st.uid = e.target.value; save(); render(); };
  el.querySelector("#h-season").onchange = e => { st.season = e.target.value; save(); render(); };
}

function render() {
  const other = T[sel.team];
  document.getElementById("h1").innerHTML = `${esc(DATA.league)} Trade Board <span class="call">${esc(DATA.mode)}</span>`;
  document.getElementById("sub").textContent = `${DATA.season} · week ${DATA.week} · values as of ${DATA.asof} · ${me.name} vs ${other.name}${handle(other) ? ` (${handle(other)})` : ""}`;
  document.getElementById("summary").innerHTML = `<b>The call: ${esc(DATA.mode)}.</b> ${esc(DATA.call_text)}<ul>${DATA.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>`;
  document.getElementById("note").textContent = DATA.note;

  const TH_ = DATA.trade_history, nHist = TH_ ? TH_.trades.length : 0;
  const nDeals = DATA.deals.length + MULTI.length;
  const view = (sel.view === "compare" && nDeals) ? "compare" : (sel.view === "history" && nHist) ? "history" : "board";
  const views = document.getElementById("views");
  views.hidden = !nDeals && !nHist;
  views.innerHTML = `<button class="view" role="tab" aria-selected="${view === "board"}" data-view="board">Trade board</button>`
    + (nDeals ? `<button class="view" role="tab" aria-selected="${view === "compare"}" data-view="compare">All deals (${nDeals})</button>` : "")
    + (nHist ? `<button class="view" role="tab" aria-selected="${view === "history"}" data-view="history">League trades (${nHist})</button>` : "");
  views.querySelectorAll(".view").forEach(b => b.onclick = () => { sel.view = b.dataset.view; save(); render(); });
  const tabs = document.getElementById("tabs");
  tabs.hidden = document.getElementById("board").hidden = document.getElementById("weights").hidden = view !== "board";
  document.getElementById("compare").hidden = view !== "compare";
  document.getElementById("history").hidden = view !== "history";
  if (view === "compare") {
    document.getElementById("sub").textContent = `${DATA.season} · week ${DATA.week} · values as of ${DATA.asof} · ${DATA.deals.length} two-team and ${MULTI.length} three-team deals across ${withDeals.length} teams`;
    renderCompare();
    return;
  }
  if (view === "history") {
    const yrs = [...new Set(TH_.trades.map(t => t.season))].sort();
    document.getElementById("sub").textContent = `${nHist} trades, ${yrs[0]} to ${yrs[yrs.length - 1]} · each priced with the DynastyProcess values of its week, and with today's (${TH_.values_now})`;
    renderHistory();
    return;
  }

  // Which rosters are on screen: yours, the selected team, any pinned with the tab's + button, and every team in the trade.
  const pins = (sel.pins || []).filter(r => T[r] && r !== ME);
  const custom = sel.custom || null;
  const inTrade = custom ? [...new Set(custom.moves.flatMap(m => [m.from, m.to]))].filter(r => T[r] && r !== ME) : [];
  const shown = [ME, other.rid, ...pins, ...inTrade].filter((r, k, a) => a.indexOf(r) === k);
  // A narrow screen shows one of them at a time (sel.ros, yours by default), chosen in the bar above the rosters.
  const cur = shown.includes(sel.ros) ? sel.ros : ME;

  const tabsX = tabs.scrollLeft;
  tabs.innerHTML = others.map(r => `<span class="tabw"><button class="tab${shown.includes(r) ? " shown" : ""}" role="tab" aria-selected="${r === sel.team}" data-team="${r}">${esc(T[r].name)}${who(T[r])}${withDeals.includes(r) ? '<span class="dot"></span>' : ""}</button><button class="pin" type="button" data-pin="${r}" aria-pressed="${pins.includes(r)}" title="${pins.includes(r) ? "Unpin this roster" : "Show this roster alongside"}" aria-label="${pins.includes(r) ? "Unpin" : "Pin"} ${esc(T[r].name)}">${pins.includes(r) ? "−" : "+"}</button></span>`).join("");
  // On a narrow screen the tabs are one row that scrolls sideways: keep its place, and bring a newly selected team into view.
  tabs.scrollLeft = tabsX;
  const onTab = tabs.querySelector('.tab[aria-selected="true"]');
  if (onTab && tabTeam !== sel.team) tabs.scrollLeft = onTab.parentElement.offsetLeft - (tabs.clientWidth - onTab.parentElement.offsetWidth) / 2;
  tabTeam = sel.team;
  // selecting a team keeps pins and any trade in progress (that is how more teams' pieces get added); an empty trade is dropped.
  // If the old team's roster was the one on a narrow screen, the new team's takes its place.
  tabs.querySelectorAll(".tab").forEach(b => b.onclick = () => {
    const keep = sel.custom && sel.custom.moves.length ? sel.custom : null;
    sel = {...sel, team: +b.dataset.team, deal: 0, v: null, view: "board", custom: keep, ros: sel.ros === sel.team ? +b.dataset.team : sel.ros};
    save(); render();
  });
  const togglePin = rid => {
    const ps = (sel.pins || []).filter(r => r !== rid);
    if (ps.length === (sel.pins || []).length) ps.push(rid);
    sel.pins = ps; save(); render();
  };
  tabs.querySelectorAll(".pin").forEach(b => b.onclick = () => togglePin(+b.dataset.pin));

  const deals = dealsFor(other.rid), mlist = multiFor(other.rid);
  const deal = deals[sel.deal] || null;
  const vnames = deal ? Object.keys(deal.vars) : [];
  const v = deal ? (vnames.includes(sel.v) ? sel.v : (vnames.includes("Target") ? "Target" : vnames[0])) : null;
  let moves = [];
  if (custom) moves = custom.moves;
  else if (deal) {
    moves = movesOfVariant(deal, v);
  }
  const R = moves.map((mv, idx) => ({...mv, idx, a: T[mv.from] && assetOf(T[mv.from], mv.key)})).filter(x => x.a);
  const hl = {players: {}, picks: {}};
  for (const x of R) {
    const cls = x.from === ME ? "send" : (x.to === ME ? "recv" : "other");
    if (x.a.kind === "player") hl.players[x.a.id] = cls; else hl.picks[x.a.key] = cls;
  }
  document.getElementById("board").classList.toggle("duo", shown.length <= 2);
  const ros = document.getElementById("rosters"), scrollX = ros.scrollLeft;
  ros.innerHTML = shown.map(rid => `<section class="panel${rid === cur ? " cur" : ""}" data-rid="${rid}" aria-label="${esc(T[rid].name)} roster">${panel(T[rid], hl, rid === ME, {focus: rid === other.rid, removable: pins.includes(rid) && !inTrade.includes(rid) && rid !== other.rid})}</section>`).join("");
  ros.scrollLeft = scrollX;
  ros.querySelectorAll(".ttype").forEach(sl => sl.onchange = () => {
    const rid = +sl.dataset.rid;
    if (sl.value === T[rid].type) delete W().types[rid]; else W().types[rid] = sl.value;
    save(); render();
  });
  ros.querySelectorAll(".unpin").forEach(b => b.onclick = () => togglePin(+b.dataset.rid));

  // Clicking an asset forks the shown proposal into a custom trade (or edits the one in progress). From your roster it goes
  // to the selected team; from anyone else's it comes to you. Each piece's "to" can then send it anywhere.
  const toggle = (rid, key) => {
    if (!sel.custom) sel.custom = {moves: moves.map(m => ({key: m.key, from: m.from, to: m.to})), base: null};
    const ms = sel.custom.moves, i = ms.findIndex(m => m.key === key && m.from === rid);
    if (i >= 0) ms.splice(i, 1); else ms.push({key, from: rid, to: rid === ME ? other.rid : ME});
    refocus = {rid, key};
    save(); render();
  };
  ros.querySelectorAll("section[data-rid]").forEach(sec => {
    const rid = +sec.dataset.rid;
    sec.querySelectorAll("[data-key]").forEach(n => {
      n.onclick = () => toggle(rid, n.dataset.key);
      n.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(rid, n.dataset.key); } };
    });
  });
  if (refocus) {
    const n = ros.querySelector(`section[data-rid="${refocus.rid}"] [data-key="${CSS.escape(refocus.key)}"]`);
    if (n && document.activeElement === document.body) n.focus({preventScroll: true});
    refocus = null;
  }

  // The deal strip: deals with the selected team on the left, the current trade on the right, one block per team in it.
  const rail = document.getElementById("rail");
  const baseIdx = custom && custom.base ? +custom.base.slice(1) : null;
  const isBase = baseIdx !== null && MULTI[baseIdx] && sameMoves(custom.moves, movesOfDeal(MULTI[baseIdx]));
  const teamsIn = [...new Set(R.flatMap(x => [x.from, x.to]))];
  const order = [ME, other.rid, ...teamsIn, ...shown].filter((r, k, a) => a.indexOf(r) === k && T[r]);
  const multi = teamsIn.length > 2;   // three or more teams: the trade takes the strip's full width and the deal list steps aside
  const gotOf = rid => R.filter(x => x.to === rid), gaveOf = rid => R.filter(x => x.from === rid);
  const tot = xs => xs.reduce((a, x) => a + x.a.value, 0);
  const sides = Object.fromEntries([...new Set([...shown, ...R.flatMap(x => [x.from, x.to])])].map(rid => [rid, sideOf(rid, moves)]));
  const pctOf = rid => (sides[rid] ? sides[rid].pct : null);
  const pcls = p => (p === null ? "" : (p >= 100 ? "good" : (p < 85 ? "bad" : "")));
  const li = x => `<li draggable="true" data-i="${x.idx}" data-from="${x.from}" title="Drag onto another team to send it there"><span class="il">${esc(x.a.label)}<small>from ${x.from === ME ? "you" : esc(tname(x.from))}</small></span><span class="iv">${fmt(x.a.value)}</span>${custom ? `<button class="rm" type="button" data-i="${x.idx}" aria-label="Remove ${esc(x.a.label)}">×</button>` : ""}</li>`;
  const empty = `<li class="empty">nothing yet</li>`;

  const left = `<div class="panel"><h3>Deals with ${esc(other.name)}${who(other)}</h3>
    ${deals.length || mlist.length ? `<div class="deals">${deals.map((d, i) => `<button class="deal" aria-selected="${!custom && i === sel.deal}" data-i="${i}">${esc(d.title)}<small>${d.fixed_side === "sends" ? d.fixed.map(x => esc(x.label)).join(", ") + " out" : d.fixed.map(x => esc(x.label)).join(", ") + " in"}</small></button>`).join("")}
      ${mlist.map(({m, i}) => `<button class="deal multi" aria-selected="${isBase && baseIdx === i}" data-m="${i}">${esc(m.title)}<small>${m.teams.filter(r => r !== ME).map(r => esc(tname(r))).join(" + ")}</small></button>`).join("")}</div>`
      : `<p class="note">Nothing drafted with ${esc(other.name)}: ${DATA.mode === "contend" ? "no older producer at your weak spots" : "not a contender with pick capital, or nothing on your sell list fits"}.</p>`}
    ${deal ? `<div class="vars${custom ? " custom" : ""}">${vnames.map(n => `<button class="var" aria-selected="${!custom && n === v}" data-v="${esc(n)}">${esc(n)}</button>`).join("")}</div>` : ""}
    <p class="hint">Use a tab's <b>+</b> to put more rosters on screen<span class="wide">; scroll sideways to see them all</span><span class="narrow">, then switch between them in the bar above the roster</span>.</p></div>`;

  let right;
  if (!R.length && !custom) {
    right = `<div class="panel"><h3>Trade</h3><p class="hint">Pick a deal, or click players and picks on any roster below to build your own. A piece from your roster goes to the selected team; a piece from any other roster comes to you.</p></div>`;
  } else {
    const title = custom ? (isBase ? "Three-team deal" : (baseIdx !== null ? "Custom trade (from a three-team deal)" : (teamsIn.length > 2 ? "Custom multi-team trade" : "Custom trade"))) : (deal ? `${esc(deal.title)} · ${esc(v)}` : "Trade");
    const blocks = order.map(rid => {
      const p = pctOf(rid), got = gotOf(rid);
      return `<div class="mside${rid === ME ? " me" : ""}" data-drop="${rid}"><div class="mh"><span><b>${rid === ME ? "You" : esc(tname(rid))}</b>${rid !== ME ? who(T[rid]) : ""} get${rid === ME ? "" : "s"}</span><span class="p ${pcls(p)}">${p === null ? "–" : p + "%"}</span></div>
        <ul class="side" style="list-style:none;margin:4px 0 0;padding:0;display:flex;flex-direction:column;gap:3px">${got.map(li).join("") || empty}</ul>
        <div class="mt">gets <b>${fmt(tot(got))}</b> for <b>${fmt(tot(gaveOf(rid)))}</b> sent</div>${sides[rid] ? lineupLine(sides[rid]) : ""}</div>`;
    }).join("");
    const myP = pctOf(ME);
    const dpOut = R.filter(x => x.from === ME).reduce((t, x) => t + x.a.dp, 0), dpIn = R.filter(x => x.to === ME).reduce((t, x) => t + x.a.dp, 0);
    const pure = W().on && dpOut ? `<span class="pure">Pure DP: ${Math.round(dpIn / dpOut * 100)}%</span>` : "";
    const foot = custom
      ? `<p class="hint">Click rows on any roster to add or remove pieces. Drag a piece onto another team, here or on its roster, to send it there. ${multi ? "Clear brings the deal list back." : (deal ? "Ask, Target or Floor go back to the drafted deal." : "")}</p>`
      : `<div class="walk"><b>Walk away if</b> ${esc(deal.walk)}${dpNote()}.</div>`;
    right = `<div class="panel"><div class="custom-head" style="margin-top:0"><span>${title}</span>${custom ? `<button class="clear" type="button">Clear</button>` : ""}</div>
      <div class="mgrid">${blocks}</div>
      <div class="tfoot"><span>Your return on what you send</span>${pure}<span class="big ${pcls(myP)}">${myP === null ? "–" : myP + "%"}</span></div>
      ${isBase ? `<p class="why">${esc(MULTI[baseIdx].why)}</p>` : ""}${foot}</div>`;
  }
  rail.innerHTML = multi ? right : left + right;
  // The bar above the rosters (narrow screens only): which roster is on screen, and the trade's return with a way back up to it.
  const rbar = document.getElementById("rbar"), barP = pctOf(ME);
  rbar.innerHTML = `<div class="rsw" role="tablist" aria-label="Roster on screen">${shown.map(rid => `<button class="rs" type="button" role="tab" aria-selected="${rid === cur}" data-ros="${rid}">${rid === ME ? "You" : esc(tname(rid))}</button>`).join("")}</div>
    <button class="rgo ${R.length ? pcls(barP) : ""}" type="button" aria-label="Go to the trade${R.length && barP !== null ? `, your return ${barP}%` : ""}">Trade${R.length ? ` <b>${barP === null ? "–" : barP + "%"}</b>` : ""}</button>`;
  rbar.querySelectorAll(".rs").forEach(b => b.onclick = () => { sel.ros = +b.dataset.ros; save(); render(); });
  rbar.querySelector(".rgo").onclick = () => rail.lastElementChild.scrollIntoView({behavior: "smooth", block: "start"});
  rail.classList.toggle("solo", multi);
  rail.querySelectorAll(".deal[data-i]").forEach(b => b.onclick = () => { sel.deal = +b.dataset.i; sel.v = null; sel.custom = null; save(); render(); });
  rail.querySelectorAll(".deal[data-m]").forEach(b => b.onclick = () => { sel.custom = {moves: movesOfDeal(MULTI[+b.dataset.m]), base: "m" + b.dataset.m}; save(); render(); });
  rail.querySelectorAll(".var").forEach(b => b.onclick = () => { sel.v = b.dataset.v; sel.custom = null; save(); render(); });
  rail.querySelectorAll(".rm").forEach(b => b.onclick = () => { sel.custom.moves.splice(+b.dataset.i, 1); save(); render(); });

  // Drag a piece in the trade onto any team's block above or its roster below to send it there instead.
  ros.querySelectorAll("section[data-rid]").forEach(sec => sec.dataset.drop = sec.dataset.rid);
  const targets = () => document.querySelectorAll("#board [data-drop]");
  const sendTo = (i, rid) => {
    if (!sel.custom) sel.custom = {moves: moves.map(m => ({key: m.key, from: m.from, to: m.to})), base: null};
    const m = sel.custom.moves[i];
    if (!m || rid === m.from || rid === m.to) return;
    m.to = rid; save(); render();
  };
  let drag = null;
  rail.querySelectorAll(".side li[draggable]").forEach(n => {
    n.ondragstart = e => {
      drag = {i: +n.dataset.i, from: +n.dataset.from};
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", n.dataset.i);
      n.classList.add("dragging");
      targets().forEach(t => { if (+t.dataset.drop !== drag.from) t.classList.add("drop-ok"); });
    };
    n.ondragend = () => { drag = null; n.classList.remove("dragging"); targets().forEach(t => t.classList.remove("drop-ok", "drop-over")); };
  });
  targets().forEach(t => {
    const rid = +t.dataset.drop;
    t.ondragover = e => { if (drag && rid !== drag.from) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; t.classList.add("drop-over"); } };
    t.ondragleave = e => { if (!t.contains(e.relatedTarget)) t.classList.remove("drop-over"); };
    t.ondrop = e => { if (!drag || rid === drag.from) return; e.preventDefault(); const i = drag.i; drag = null; sendTo(i, rid); };
  });
  const clear = rail.querySelector(".clear");
  if (clear) clear.onclick = () => { sel.custom = {moves: [], base: null}; save(); render(); };
  sel.v = v;
}
// The weights strip is built once and never re-rendered: rebuilding it would drop a slider out from under the pointer.
function buildWeights() {
  const el = document.getElementById("weights"), w = W();
  el.innerHTML = `<label class="tog"><input type="checkbox" id="w-on"${w.on ? " checked" : ""}>Custom league weights</label>
    <span class="wctl wset" title="How fast value falls off down the rankings. Lower narrows the gap between stars and depth, higher widens it. DynastyProcess uses 0.0235; every value on the board is re-priced on this curve."><label for="w-steep">Steepness</label><input type="range" id="w-steep" min="0.005" max="0.035" step="0.0005" value="${w.steepness}"><b id="w-steep-v"></b><span class="dp">DP 0.0235</span></span>
    ${TEAM_TYPES.map(t => `<span class="wctl rate wset" title="Value per weekly point a trade adds to or costs a ${t} team's best lineup"><label for="w-rate-${t}">${t[0].toUpperCase() + t.slice(1)}</label><input type="range" id="w-rate-${t}" min="0" max="1000" step="10" value="${w.rates[t]}"><b id="w-rate-${t}-v"></b></span>`).join("")}
    <span class="dp wset">per lineup point</span>
    <button type="button" class="reset wset" id="w-reset">Reset</button>`;
  const sync = () => {
    const w = W();
    el.classList.toggle("on", w.on);
    el.querySelectorAll(".wset").forEach(n => n.hidden = !w.on);
    document.getElementById("w-steep").value = w.steepness;
    document.getElementById("w-steep-v").textContent = w.steepness.toFixed(4);
    for (const t of TEAM_TYPES) { document.getElementById(`w-rate-${t}`).value = w.rates[t]; document.getElementById(`w-rate-${t}-v`).textContent = w.rates[t]; }
  };
  const apply = () => { sync(); save(); render(); };
  document.getElementById("w-on").onchange = e => { W().on = e.target.checked; apply(); };
  document.getElementById("w-steep").oninput = e => { W().steepness = +e.target.value; apply(); };
  for (const t of TEAM_TYPES) document.getElementById(`w-rate-${t}`).oninput = e => { W().rates[t] = +e.target.value; apply(); };
  // Reset restores the sliders only: team type overrides record what owners said and are cleared one team at a time
  document.getElementById("w-reset").onclick = () => { W().steepness = WEIGHT_DEFAULTS.steepness; W().rates = {...WEIGHT_DEFAULTS.rates}; apply(); };
  sync();
}
buildWeights();
render();
