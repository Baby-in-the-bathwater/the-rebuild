"""Render the interactive trade board (one HTML file, no server) from the grade, ledger and deals."""
import json
import os
from collections import defaultdict

from .grade import SELL_AGE
from .metrics import TH

TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "trade_board.html")


def _item(i):
    if i["kind"] == "player":
        return {"kind": "player", "id": i["id"], "label": i["label"], "value": i["value"]}
    return {"kind": "pick", "key": i["key"], "label": i["label"], "value": i["value"]}


def deal_json(d):
    fixed_side = "sends" if d.get("sends") else "receives"
    return {"counterparty": d["counterparty"], "cp_rid": d["cp_rid"], "title": d["title"], "fixed_side": fixed_side,
            "fixed": [_item(i) for i in (d.get("sends") or d.get("receives"))],
            "vars": {k: {"items": [_item(i) for i in v["items"]], "value": v["value"]} for k, v in d["vars"].items()},
            "walk": d["walk"]}


SIGNAL_MIN_GP = 4      # games with points before production means anything
SIGNAL_MIN_GAP = 6     # rank spots between production and price before a tag
SIGNAL_SELL_VALUE = 900


def price_signals(teams):
    """Production vs price for every rostered player with enough games: rank by points per game and by value
    within the position (same pool for both), and the gap between them. Tags split on the position's sell age, the
    point where this format's value curve turns down: BUY LOW is a startable player under the sell age producing at
    least twice as well as he is priced (the price should rise to meet the production); SELL HIGH is a player at or
    past the sell age priced at least twice as well as he produces, worth selling and not on IR (the price should
    fall). An old player producing cheaply, or a young one priced on his future, shows in the gap but is not tagged."""
    by_pos = defaultdict(list)
    for t in teams:
        for p in t["players"]:
            if p["pos"] in TH and p["gp"] >= SIGNAL_MIN_GP:
                by_pos[p["pos"]].append(p)
    out = {}
    for pos, ps in by_pos.items():
        prod = {p["id"]: i + 1 for i, p in enumerate(sorted(ps, key=lambda p: (-p["ppg"], -p["value"])))}
        price = {p["id"]: i + 1 for i, p in enumerate(sorted(ps, key=lambda p: (-p["value"], -p["ppg"])))}
        for p in ps:
            pr, vr = prod[p["id"]], price[p["id"]]
            gap = vr - pr
            tag = None
            age = p["age"] or 0
            if gap >= max(SIGNAL_MIN_GAP, pr) and p["startable"] and age < SELL_AGE[pos]:
                tag = "buy"
            elif -gap >= max(SIGNAL_MIN_GAP, vr) and p["value"] >= SIGNAL_SELL_VALUE and age >= SELL_AGE[pos] and not p["ir"]:
                tag = "sell"
            out[p["id"]] = {"prod": pr, "price": vr, "gap": gap, "n": len(ps), "tag": tag}
    return out


def board_data(league, values, g, assets, deals, call_text, trade_history=None):
    teams = []
    for t in sorted(g["teams"].values(), key=lambda t: t["rank"]):
        teams.append({k: t[k] for k in ("rid", "name", "owner", "wins", "losses", "pf", "rank", "proj_slot", "player_value", "pick_value", "startable", "core_age")}
                     | {"players": [{k: p[k] for k in ("id", "name", "pos", "team", "age", "ppg", "gp", "value", "ir", "taxi", "inj", "starter", "startable")} for p in t["players"]],
                        "picks": [{k: p[k] for k in ("season", "round", "orig", "orig_rid", "own", "proj_slot", "value", "key")} for p in t["picks"]]})
    sig = price_signals(teams)
    for t in teams:
        for p in t["players"]:
            if p["id"] in sig:
                p["sig"] = sig[p["id"]]
    ledger = {p["id"]: "sell" for p in assets["sell"]} | {p["id"]: "hold" for p in assets["hold"]}
    nxt = league.pick_seasons[0] if league.pick_seasons else None
    pick_note = (f"picks priced by the original team's projected {nxt} slot from current standings (early, mid, late third), flat the year after, then 15% off per further year. "
                 if nxt else "redraft league: no future picks; the values are a dynasty market, so read them as relative size this season and ignore the age premium. ")
    note = (f"Values are DynastyProcess {'Superflex' if values.superflex else '1QB'} values as of {values.asof}; {pick_note}"
            f"PPG is this season through week {league.week}, games with points only. ST marks a startable average (QB 14, RB 9, WR 9, TE 7). "
            f"SELL and HOLD tags on your roster are the ledger from the brief. P/V is production vs price: a player's rank at his position by PPG "
            f"against his rank by value, among rostered players with {SIGNAL_MIN_GP}+ games (+ produces better than priced). BUY LOW: under the position's sell age "
            f"(QB {SELL_AGE['QB']}, RB {SELL_AGE['RB']}, WR {SELL_AGE['WR']}, TE {SELL_AGE['TE']}), startable, producing at least twice as well as priced. "
            f"SELL HIGH: at or past the sell age, priced at least twice as well as producing, worth {SIGNAL_SELL_VALUE}+, not on IR.")
    return {"league": league.lg.get("name"), "league_id": league.id, "season": league.season, "week": league.week, "asof": values.asof,
            "me_rid": g["team"]["rid"], "me_uid": league.roster(g["team"]["rid"]).get("owner_id"), "trade_history": trade_history, "mode": g["mode"], "reasons": g["reasons"], "call_text": call_text, "pick_seasons": league.pick_seasons,
            "teams": teams, "ledger": ledger, "deals": [deal_json(d) for d in deals], "note": note}


def render(data, out_path):
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__TITLE__", f"{data['league']} Trade Board").replace("/*__DATA__*/null", json.dumps(data))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
