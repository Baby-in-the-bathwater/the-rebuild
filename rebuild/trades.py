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


def ledger_sells(pos, age, value, startable, mode):
    """Whether a team graded `mode` puts this player on its sell list. Rebuild sells at the position's turn (a year
    early for RBs), and one tier younger once he is producing, since a contender pays now; retool sells a year past
    the turn. The same rule decides what a third team in a three-team deal will take."""
    if value < MIN_SELL_VALUE:
        return False
    turn = SELL_AGE[pos]
    if mode == "rebuild":
        return age >= turn - (1 if pos == "RB" else 0) or (age >= turn - 2 and startable)
    if mode == "retool":
        return age >= turn + 1
    return False


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
            if ledger_sells(pos, age, p["value"], p["startable"], mode):
                sell.append(p)
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
            if ledger_sells(pos, age, p["value"], p["startable"], mode):
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
    uncovered = [pos for pos in ranked if have.get(pos, 0) < need_n[pos]][:2]
    if uncovered:
        return uncovered
    row = next((r for r in g["rows"] if r["rid"] == me["rid"]), None) or {}
    below = [pos for pos in ranked if (row.get("z_" + pos) or 0) < 0][:2]
    return below or ranked[:1] or ["RB"]


def retool_spendable(team, items, league):
    """What a retooling team will pay with: everything but its own first in the next draft and its eight most
    valuable players (its core). Used for your retool buys and for a retooling third team in a three-team deal."""
    own_next_first = {pk["key"] for pk in team["picks"] if pk["round"] == 1 and pk["own"] and pk["season"] == league.pick_seasons[0]}
    core = {p["id"] for p in sorted((p for p in team["players"] if p["pos"] in TH), key=lambda p: -p["value"])[:8]}
    return [i for i in items if not (i["kind"] == "pick" and i["key"] in own_next_first) and not (i["kind"] == "player" and i["id"] in core)]


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
        my_items = retool_spendable(me, my_items, league)
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


def return_quality(items, sell_value, fit):
    """Quality of a sell return, not its size: preference per piece, need fit, firsts in the next two drafts."""
    total = sum(i["value"] for i in items)
    return (sum(i["pref"] for i in items) / len(items) + 0.4 * fit
            + 0.15 * sum(1 for i in items if i["kind"] == "pick" and i["pref"] >= 3.0)
            + 0.05 * min(total / sell_value, 1.1))


def deals(g, league, assets, mode, max_counterparties=6, deals_per_cp=None, deals_per_asset=4):
    me = g["team"]
    out = []
    if mode in ("rebuild", "retool"):
        cps = counterparties(g, league, mode)[:max_counterparties]
        for sell in assets["sell"]:
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
                score = return_quality(tgt, sell["value"], fit)
                out.append({"counterparty": t["name"], "cp_rid": t["rid"], "title": f"{sell['name']} to {t['name']}" + (f" (needs {sell['pos']})" if fit else ""),
                            "sends": [{"kind": "player", "id": sell["id"], "label": f"{sell['name']} ({sell['pos']}, {sell['age']})", "value": sell["value"]}],
                            "vars": vars_, "walk": f"the {best['label']} is not in it, or the return falls under {int(sell['value'] * FLOOR):,}",
                            "need_fit": bool(fit), "score": score, "asset": sell["name"]})
    if mode in ("contend", "retool"):
        out.extend(buy_deals(g, league, me, mode, max_counterparties))
    # biggest asset first, then the best counterparty for it. Every sell asset gets its deals; the per-asset cap keeps
    # one player from flooding the list, and deals_per_cp (off by default) can cap how many land on one team.
    asset_value = {d["asset"]: sum(x["value"] for x in (d.get("sends") or d.get("receives"))) for d in out}
    out.sort(key=lambda d: (-asset_value[d["asset"]], -d["score"]))
    kept, per_cp, per_asset = [], {}, {}
    for d in out:
        if (deals_per_cp and per_cp.get(d["counterparty"], 0) >= deals_per_cp) or per_asset.get(d["asset"], 0) >= deals_per_asset:
            continue
        per_cp[d["counterparty"]] = per_cp.get(d["counterparty"], 0) + 1
        per_asset[d["asset"]] = per_asset.get(d["asset"], 0) + 1
        kept.append(d)
    return kept


# ------------------------------------------------------------------ three-team deals
THREE_MIN_SHARE = 0.15   # the third team must pay at least this share of the sell asset, or it is a two-team deal
THREE_FAIR = (0.87, 1.15)  # every other team's return (received / sent) must land in this band
THREE_EDGE = 0.10        # and the return must beat the best two-team package from the same buyer by this much


def _bridge_items(team, mode, league, wanted_keys):
    """A buyer's players a rebuilder does not want back (past 25, or simply not in its wanted list): the pieces
    a third team might take instead."""
    out = []
    for p in team["players"]:
        if p["pos"] not in TH or p["value"] < MIN_PACKAGE_PIECE or p["id"] in wanted_keys:
            continue
        out.append({"kind": "player", "id": p["id"], "value": p["value"], "pos": p["pos"], "age": p["age"], "startable": p["startable"],
                    "label": f"{p['name']} ({p['pos']}, {p['age'] or '?'})"})
    return out


def bridge_fits(item, b_type, b_needs):
    """Whether third team B, graded `b_type`, would take this player from A: never one its own sell list would hold
    (ledger_sells, graded the same way), and never one past the position's turn unless B is retooling and he fills
    one of its two weakest spots. A contender, or an ungraded team, takes anyone. Unknown age counts as old."""
    if b_type not in ("rebuild", "retool"):
        return True
    age = item.get("age") or 99
    if ledger_sells(item["pos"], age, item["value"], item.get("startable"), b_type):
        return False
    return age < SELL_AGE[item["pos"]] or (b_type == "retool" and item["pos"] in b_needs[:2])


def three_team_deals(g, league, assets, mode, per_asset=2, max_total=8, max_buyers=6, types=None):
    """Sell deals routed through a third team. You send a sell asset to buyer A; A pays part of it in what you want
    (near-term firsts, young players) and sends players you do not want to team B; B, which wants them, pays you
    the rest in picks or youth. Kept only when every other team comes out near fair at market value and your
    return is better than the best two-team package A alone could send. `types` (rid -> contend/retool/rebuild,
    from grade.team_types) limits what B takes to players that suit it; without it B is judged by standings alone."""
    if mode not in ("rebuild", "retool"):
        return []
    me = g["team"]
    n = g["n"]
    buyers = counterparties(g, league, mode)[:max_buyers]
    found = []
    for sell in assets["sell"]:
        S = sell["value"]
        for A, a_needs in buyers:
            a_want = tradeable(A, mode, league)
            wanted = {i.get("id") for i in a_want if i["kind"] == "player"}
            bridge_base = _bridge_items(A, mode, league, wanted)
            if not bridge_base:
                continue
            fit_a = 1.0 if sell["pos"] in a_needs[:2] else 0.0
            # the best A can do alone, scored the same way, is the bar a three-team deal has to clear
            two, two_v = build_package(a_want, S) if a_want else ([], 0)
            bar = return_quality(two, S, fit_a) if two and two_v >= S * FLOOR else -1.0
            # what you take from A: its one or two most-wanted pieces, as long as they leave room for a third team
            top = sorted(a_want, key=lambda i: (-i["pref"], -i["value"]))[:8]
            xs = [[i] for i in top] + [[a, b] for k, a in enumerate(top) for b in top[k + 1:]]
            xs = [x for x in xs if sum(i["value"] for i in x) <= S * (1 - THREE_MIN_SHARE)]
            for B in g["teams"].values():
                if B["rid"] in (me["rid"], A["rid"]):
                    continue
                b_needs = positional_need(g["rows"], B["rid"])
                b_type = (types or {}).get(B["rid"])
                contending = b_type == "contend" if b_type else B["rank"] <= n // 2 + 1
                b_want = tradeable(B, mode, league)
                if b_type == "retool":
                    b_want = retool_spendable(B, b_want, league)   # a team trying to win next year keeps its own next first and its core
                if not b_want:
                    continue
                # what B takes from A: only players that suit B's grade, scored by B's weakest spots, a contender's
                # taste for producers, and A's redundancy at the sell position
                bridge = [dict(i, pref=1.0 + (1.0 if i["pos"] in b_needs[:2] else 0.0) + (0.4 if contending and i["startable"] else 0.0)
                               + (0.5 if i["pos"] == sell["pos"] else 0.0)) for i in bridge_base if bridge_fits(i, b_type, b_needs)]
                if not bridge:
                    continue
                best = None
                for X in xs:
                    vX = sum(i["value"] for i in X)
                    Y, vY = build_package(b_want, S - vX, max_pieces=2)
                    if not Y or vX + vY < S * 0.97 or vX + vY > S * 1.2:
                        continue
                    Z, vZ = build_package(bridge, vY, max_pieces=3)
                    if not Z or not (THREE_FAIR[0] <= vZ / vY <= THREE_FAIR[1]):
                        continue
                    a_ret = S / (vX + vZ)
                    if not (THREE_FAIR[0] <= a_ret <= THREE_FAIR[1]):
                        continue
                    if not contending and not any(i["pos"] in b_needs[:2] for i in Z):
                        continue   # B takes A's players only if it is contending or they fill a hole
                    mine = X + Y
                    # the bar is your return alone; the bonus for filling B's hole only ranks deals that already clear it
                    quality = return_quality(mine, S, fit_a)
                    if quality < bar + THREE_EDGE:
                        continue
                    score = quality + 0.2 * (1.0 if any(i["pos"] in b_needs[:2] for i in Z) else 0.0)
                    if best is None or score > best[0]:
                        best = (score, X, vX, Y, vY, Z, vZ)
                if best:
                    found.append((sell, A, B, b_needs, fit_a, bar) + best)
    # rank by the quality of your return; keep a few per sell asset, each with a different buyer
    found.sort(key=lambda f: -f[6])
    out, per, seen = [], {}, set()
    for sell, A, B, b_needs, fit_a, bar, score, X, vX, Y, vY, Z, vZ in found:
        if per.get(sell["id"], 0) >= per_asset or (sell["id"], A["rid"]) in seen:
            continue
        per[sell["id"]] = per.get(sell["id"], 0) + 1
        seen.add((sell["id"], A["rid"]))
        S = sell["value"]
        mv = lambda i, frm, to: {k: i[k] for k in ("kind", "label", "value") if k in i} | ({"id": i["id"]} if i["kind"] == "player" else {"key": i["key"]}) | {"from": frm, "to": to}  # noqa: E731
        sell_item = {"kind": "player", "id": sell["id"], "label": f"{sell['name']} ({sell['pos']}, {sell['age']})", "value": S}
        moves = ([mv(sell_item, me["rid"], A["rid"])] + [mv(i, A["rid"], me["rid"]) for i in X]
                 + [mv(i, B["rid"], me["rid"]) for i in Y] + [mv(i, A["rid"], B["rid"]) for i in Z])
        holes = sorted({i["pos"] for i in Z if i["pos"] in b_needs[:2]})
        why = (f"{A['name']} can cover {round(vX / S * 100)}% of {sell['name']} in what you want. "
               f"{B['name']} pays the rest for {', '.join(i['label'].split(' (')[0] for i in Z)}"
               + (f", filling its {'/'.join(holes)} hole." if holes else ", depth for a contender.")
               + (" Beats the best two-team package from " + A["name"] + "." if bar >= 0 else f" {A['name']} cannot reach {sell['name']}'s value alone in pieces you want."))
        out.append({"multi": True, "title": f"{sell['name']} to {A['name']}, with {B['name']}", "asset": sell["name"],
                    "teams": [me["rid"], A["rid"], B["rid"]], "moves": moves, "why": why, "score": round(score, 3)})
        if len(out) >= max_total:
            break
    return out
