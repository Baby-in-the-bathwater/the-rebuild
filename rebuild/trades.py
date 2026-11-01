"""Turn the grade into moves: a sell / hold / keep ledger and concrete deals with ask, target and floor packages.

Rebuild mode sells production that will not survive the window (older startable players) to contenders for
first-round picks in the next two drafts and for players under 25. Contend mode does the reverse: it spends
far-out picks and non-producing youth on older producers at the weakest starting position. Retool sits between:
sell anything past its sell age, keep the own first in the next draft and the core, and spend surplus picks and
non-core youth on one young starter at the weakest position."""
from .grade import SELL_AGE
from .metrics import TH

ASK, TARGET, FLOOR = 1.15, 1.0, 0.88
MIN_SELL_VALUE = 900       # below this nobody pays in picks; it is depth, not an asset
MIN_PACKAGE_PIECE = 150    # smallest piece worth listing in a package


def classify_assets(team, mode, league):
    sell, hold, keep, filler = [], [], [], []
    for p in team["players"]:
        pos = p["pos"]
        if pos not in TH or p["value"] <= 0:
            filler.append(p)
            continue
        age = p["age"] or 0
        sell_age = SELL_AGE[pos]
        if mode == "rebuild":
            if p["value"] >= MIN_SELL_VALUE and age >= sell_age - (1 if pos == "RB" else 0):
                sell.append(p)
            elif p["value"] >= MIN_SELL_VALUE and age >= sell_age - 2 and p["startable"]:
                sell.append(p)          # one tier younger but already producing: a contender pays now
            elif age < sell_age - 1 and p["value"] >= 600:
                hold.append(p)
            elif age <= 24 or (p["years_exp"] or 9) <= 1:
                keep.append(p)
            else:
                filler.append(p)
        elif mode == "contend":
            if not p["startable"] and age <= 23 and p["value"] >= 800 and (p["years_exp"] or 0) <= 1:
                sell.append(p)          # rookie-year upside a rebuilder pays for; the contender needs points now
            elif p["startable"] or p["value"] >= 1500:
                hold.append(p)
            else:
                filler.append(p)
        else:  # retool
            if p["value"] >= MIN_SELL_VALUE and age >= sell_age + 1:
                sell.append(p)
            elif p["value"] >= 600:
                hold.append(p)
            elif age <= 24:
                keep.append(p)
            else:
                filler.append(p)
    sell.sort(key=lambda p: -p["value"])
    hold.sort(key=lambda p: -p["value"])
    keep.sort(key=lambda p: -p["value"])
    reason = {}
    for p in sell:
        reason[p["id"]] = (f"{p['pos']} age {p['age']}: past the {SELL_AGE[p['pos']]} turn in this format's value curve" if (p["age"] or 0) >= SELL_AGE[p["pos"]]
                           else f"{p['pos']} age {p['age']}, producing {p['ppg']} ppg: peak sale window, a contender pays now")
        if mode == "contend":
            reason[p["id"]] = f"{p['pos']} age {p['age']}, {p['ppg']} ppg: upside a rebuilder values more than a contender does"
    return {"sell": sell, "hold": hold, "keep": keep, "filler": filler, "reason": reason}


def positional_need(rows, rid):
    """Which starting positions a team is weakest at, by within-league z of positional points."""
    row = next((r for r in rows if r["rid"] == rid), None)
    if not row:
        return []
    zs = [(row.get("z_" + m) if row.get("z_" + m) is not None else 0.0, m) for m in ("QB", "RB", "WR", "TE")]
    return [m for z, m in sorted(zs)]


def counterparties(g, league, mode):
    """Ordered list of (team, needs) to approach. Rebuild: contenders with pick capital. Contend: bottom teams with older producers."""
    n = g["n"]
    out = []
    for rid, t in g["teams"].items():
        if rid == g["team"]["rid"]:
            continue
        needs = positional_need(g["rows"], rid)
        if mode in ("rebuild", "retool"):
            if t["rank"] > max(league.playoff_teams, n // 2) + 1:
                continue
            firsts = sum(t["firsts"].values())
            young = sum(p["value"] for p in t["players"] if (p["age"] or 99) <= 25 and p["pos"] in TH)
            score = (n - t["rank"]) * 400 + firsts * 600 + young / 10
            out.append((score, t, needs))
        else:
            if t["rank"] <= n // 2:
                continue
            old_prod = sum(p["value"] for p in t["players"] if p["startable"] and (p["age"] or 0) >= SELL_AGE[p["pos"]] - 1) if any(p["pos"] in TH for p in t["players"]) else 0
            score = t["rank"] * 300 + old_prod / 10
            out.append((score, t, needs))
    out.sort(key=lambda x: -x[0])
    return [(t, needs) for _, t, needs in out]


def tradeable(team, mode, league, want_pos=None):
    """What a counterparty can send, scored by how much the asking side wants it. Higher is better."""
    items = []
    first_seasons = league.pick_seasons[:2]
    for pk in team["picks"]:
        if pk["value"] < MIN_PACKAGE_PIECE:
            continue
        if mode in ("rebuild", "retool"):
            pref = 3.0 if (pk["round"] == 1 and pk["season"] in first_seasons) else (1.6 if pk["round"] == 1 else (1.2 if pk["round"] == 2 else 0.8))
            if pk["round"] == 1 and pk["season"] == first_seasons[0] and pk.get("proj_slot") and pk["proj_slot"] <= league.n / 3:
                pref += 0.6   # projected early first: the slot that actually hits
        else:
            pref = 0.3
        items.append({"kind": "pick", "key": pk["key"], "value": pk["value"], "pref": pref, "pos": None, "age": None,
                      "label": f"{pk['season']} R{pk['round']}" + ("" if pk["own"] else f" via {pk['orig']}") + (f" (1.{pk['proj_slot']:02d})" if pk.get("proj_slot") and pk["round"] == 1 else "")})
    for p in team["players"]:
        if p["value"] < MIN_PACKAGE_PIECE or p["pos"] not in TH:
            continue
        age = p["age"] or 30
        if mode in ("rebuild", "retool"):
            if age > 25:
                continue
            pref = 2.2 if age <= 23 else 1.5
            if p["startable"]:
                pref += 0.4
            if p["ir"]:
                pref -= 0.3
        else:
            if not p["startable"] and p["value"] < 2500:
                continue
            pref = 2.5 if (want_pos and p["pos"] == want_pos) else 1.0
            pref += min(p["ppg"], 25) / 25
            if age >= SELL_AGE[p["pos"]] + 3:
                pref -= 0.6
        items.append({"kind": "player", "id": p["id"], "value": p["value"], "pref": pref, "pos": p["pos"], "age": p["age"],
                      "label": f"{p['name']} ({p['pos']}, {p['age'] or '?'})"})
    return items


def build_package(items, target, max_pieces=4, exclude=(), slack=0.03):
    """Smallest-overshoot package: every combination of up to `max_pieces` pieces that clears the target
    (within `slack` under it), scored by overshoot minus a preference bonus. Exhaustive over the 16 most
    preferred pieces plus anything that fits, which is a few thousand combinations at most."""
    from itertools import combinations
    pool = [i for i in items if (i.get("key") or i.get("id")) not in exclude]
    pool = sorted(pool, key=lambda i: (-i["pref"], -i["value"]))
    cands = pool[:16]
    floor = target * (1 - slack)
    best, best_cost = None, None
    for k in range(1, max_pieces + 1):
        for combo in combinations(cands, k):
            total = sum(i["value"] for i in combo)
            if total < floor:
                continue
            over = (total - target) / target
            cost = max(over, 0) * 1.0 + max(-over, 0) * 2.0 - 0.06 * sum(i["pref"] for i in combo if i["value"] >= 0.1 * target) + 0.02 * k
            if best_cost is None or cost < best_cost:
                best, best_cost = list(combo), cost
        if best is not None and k >= 2:
            break   # a 2-piece answer beats a 3-piece one unless none exists
    if best is None:
        # nothing clears the target: send the most valuable pieces we have
        best = sorted(pool, key=lambda i: -i["value"])[:max_pieces]
    return best, sum(i["value"] for i in best)


def buy_counterparties(g, league, pos, mode):
    """Teams to buy a player at `pos` from. Contend: bottom-half teams holding older producers.
    Retool: any team with surplus at the position, pick-hungry teams first."""
    n = g["n"]
    out = []
    for rid, t in g["teams"].items():
        if rid == g["team"]["rid"]:
            continue
        needs = positional_need(g["rows"], rid)
        if mode == "contend":
            if t["rank"] <= n // 2:
                continue
            old_prod = sum(p["value"] for p in t["players"] if p["startable"] and (p["age"] or 0) >= SELL_AGE[p["pos"]] - 1)
            score = t["rank"] * 300 + old_prod / 10
        else:
            surplus = sum(1 for p in t["players"] if p["pos"] == pos and p["startable"])
            firsts = sum(t["firsts"].values())
            score = surplus * 500 - firsts * 300 + (200 if pos not in needs[:2] else 0)
        out.append((score, t, needs))
    out.sort(key=lambda x: -x[0])
    return [(t, needs) for _, t, needs in out]


def coverage(me, league):
    """Starters needed per position (Superflex counts as a QB) and startable players held today."""
    f = league.fmt
    need_n = {"QB": (f.get("qb") or 1) + (f.get("sf") or 0), "RB": f.get("rb") or 2, "WR": f.get("wr") or 3, "TE": f.get("te") or 1}
    have = {pos: sum(1 for p in me["players"] if p["pos"] == pos and p["startable"]) for pos in need_n}
    return need_n, have


def buy_positions(g, me, league):
    """The two weakest positions by this season's z, skipping any the roster already covers when healthy
    (two startable QBs in Superflex, two RBs, three WRs, one TE): that weakness is availability, not talent."""
    need_n, have = coverage(me, league)
    ranked = positional_need(g["rows"], me["rid"])
    return [pos for pos in ranked if have.get(pos, 0) < need_n[pos]][:2] or ranked[:2] or ["RB", "WR"]


def buy_deals(g, league, me, mode, max_counterparties=6):
    """Buy a starter at the two weakest positions. Contend buys older production with picks and youth;
    retool buys a young starter (one who is still there when the window opens) with surplus picks and
    non-core youth, keeping the own first in the next draft and every core asset."""
    out = []
    want = buy_positions(g, me, league)
    my_items = tradeable(me, "rebuild", league)  # picks and youth, scored the way a rebuilder wants them
    if league.redraft:
        # no picks exist and age is irrelevant: spend bench depth, and starters at a position with two spare
        need_n, have = coverage(me, league)
        my_items = [{"kind": "player", "id": p["id"], "value": p["value"], "pref": 1.5 if not p["startable"] else 0.8, "pos": p["pos"], "age": p["age"],
                     "label": f"{p['name']} ({p['pos']}, {p['age'] or '?'})"}
                    for p in me["players"] if p["pos"] in TH and p["value"] >= MIN_PACKAGE_PIECE
                    and (not p["startable"] or have.get(p["pos"], 0) - need_n.get(p["pos"], 9) >= 2)]
    if mode == "retool":
        own_next_first = {pk["key"] for pk in me["picks"] if pk["round"] == 1 and pk["own"] and pk["season"] == league.pick_seasons[0]}
        core = {p["id"] for p in sorted((p for p in me["players"] if p["pos"] in TH), key=lambda p: -p["value"])[:8]}
        my_items = [i for i in my_items if not (i["kind"] == "pick" and i["key"] in own_next_first) and not (i["kind"] == "player" and i["id"] in core)]
    budget = sum(i["value"] for i in my_items)
    for pos in want:
        for t, _ in buy_counterparties(g, league, pos, mode)[:(max_counterparties if mode == "contend" else None)]:
            if mode == "contend":
                targets = sorted([p for p in t["players"] if p["pos"] == pos and p["startable"] and p["value"] >= MIN_SELL_VALUE
                                  and (league.redraft or (p["age"] or 0) >= SELL_AGE[pos] - 2)], key=lambda p: -p["ppg"])[:1]
            else:
                targets = sorted([p for p in t["players"] if p["pos"] == pos and p["startable"] and p["value"] >= 1500
                                  and (p["age"] or 99) <= SELL_AGE[pos] - 1 and p["value"] * ASK <= budget], key=lambda p: -p["value"])[:1]
            for tp in targets:
                if tp["value"] * ASK > budget:
                    continue
                vars_ = {}
                for name, mult in (("Open", FLOOR), ("Target", TARGET), ("Ceiling", ASK)):
                    pk, tot = build_package(my_items, tp["value"] * mult)
                    vars_[name] = {"items": pk, "value": tot}
                if vars_["Target"]["value"] < tp["value"] * TARGET * 0.97:
                    continue
                label = f"your weakest spot: {pos}" if mode == "contend" else f"young starter at {pos}, your weakest spot"
                score = tp["ppg"] / 20 + 0.2 + (0.3 if mode == "retool" and (tp["age"] or 99) <= 25 else 0.0)
                out.append({"counterparty": t["name"], "cp_rid": t["rid"], "title": f"Buy {tp['name']} from {t['name']} ({label})",
                            "sends": None, "receives": [{"kind": "player", "id": tp["id"], "label": f"{tp['name']} ({pos}, {tp['age']})", "value": tp["value"]}],
                            "vars": vars_, "walk": f"they want more than {int(tp['value'] * ASK):,} of your picks and youth",
                            "need_fit": True, "score": score, "asset": tp["name"]})
    return out


def deals(g, league, assets, mode, max_counterparties=6, deals_per_cp=2):
    me = g["team"]
    out = []
    if mode in ("rebuild", "retool"):
        cps = counterparties(g, league, mode)[:max_counterparties]
        for sell in assets["sell"][:4]:
            for t, needs in cps:
                items = tradeable(t, mode, league)
                if sum(i["value"] for i in items) < sell["value"] * FLOOR:
                    continue
                vars_ = {}
                for name, mult in (("Ask", ASK), ("Target", TARGET), ("Floor", FLOOR)):
                    pk, tot = build_package(items, sell["value"] * mult)
                    vars_[name] = {"items": pk, "value": tot}
                if vars_["Floor"]["value"] < sell["value"] * FLOOR * 0.97:
                    continue
                best = max(vars_["Target"]["items"], key=lambda i: (i["pref"], i["value"]))
                fit = 1.0 if sell["pos"] in needs[:2] else 0.0
                tgt = vars_["Target"]["items"]
                # quality of the return, not its size: preference per piece, need fit, firsts in the next two drafts
                score = (sum(i["pref"] for i in tgt) / len(tgt) + 0.4 * fit
                         + 0.15 * sum(1 for i in tgt if i["kind"] == "pick" and i["pref"] >= 3.0)
                         + 0.05 * min(vars_["Target"]["value"] / sell["value"], 1.1))
                out.append({"counterparty": t["name"], "cp_rid": t["rid"], "title": f"{sell['name']} to {t['name']}" + (f" (needs {sell['pos']})" if fit else ""),
                            "sends": [{"kind": "player", "id": sell["id"], "label": f"{sell['name']} ({sell['pos']}, {sell['age']})", "value": sell["value"]}],
                            "vars": vars_, "walk": f"the {best['label']} is not in it, or the return falls under {int(sell['value'] * FLOOR):,}",
                            "need_fit": bool(fit), "score": score, "asset": sell["name"]})
    if mode in ("contend", "retool"):
        out.extend(buy_deals(g, league, me, mode, max_counterparties))
    # biggest asset first, then the best counterparty for it; cap deals per counterparty so the board stays readable
    asset_value = {d["asset"]: sum(x["value"] for x in (d.get("sends") or d.get("receives"))) for d in out}
    out.sort(key=lambda d: (-asset_value[d["asset"]], -d["score"]))
    kept, per_cp, per_asset = [], {}, {}
    for d in out:
        if per_cp.get(d["counterparty"], 0) >= deals_per_cp or per_asset.get(d["asset"], 0) >= 4:
            continue
        per_cp[d["counterparty"]] = per_cp.get(d["counterparty"], 0) + 1
        per_asset[d["asset"]] = per_asset.get(d["asset"], 0) + 1
        kept.append(d)
    return kept
