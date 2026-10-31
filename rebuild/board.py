"""Render the interactive trade board (one HTML file, no server) from the grade, ledger and deals."""
import json
import os

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


def board_data(league, values, g, assets, deals, call_text):
    teams = []
    for t in sorted(g["teams"].values(), key=lambda t: t["rank"]):
        teams.append({k: t[k] for k in ("rid", "name", "wins", "losses", "pf", "rank", "proj_slot", "player_value", "pick_value", "startable", "core_age")}
                     | {"players": [{k: p[k] for k in ("id", "name", "pos", "team", "age", "ppg", "gp", "value", "ir", "taxi", "inj", "starter", "startable")} for p in t["players"]],
                        "picks": [{k: p[k] for k in ("season", "round", "orig", "orig_rid", "own", "proj_slot", "value", "key")} for p in t["picks"]]})
    ledger = {p["id"]: "sell" for p in assets["sell"]} | {p["id"]: "hold" for p in assets["hold"]}
    nxt = league.pick_seasons[0]
    note = (f"Values are DynastyProcess {'Superflex' if values.superflex else '1QB'} values as of {values.asof}; picks priced by the original team's projected {nxt} slot "
            f"from current standings (early, mid, late third), flat the year after, then 15% off per further year. PPG is this season through week {league.week}, "
            f"games with points only. ST marks a startable average (QB 14, RB 9, WR 9, TE 7). SELL and HOLD tags on your roster are the ledger from the brief.")
    return {"league": league.lg.get("name"), "league_id": league.id, "season": league.season, "week": league.week, "asof": values.asof,
            "me_rid": g["team"]["rid"], "mode": g["mode"], "reasons": g["reasons"], "call_text": call_text, "pick_seasons": league.pick_seasons,
            "teams": teams, "ledger": ledger, "deals": [deal_json(d) for d in deals], "note": note}


def render(data, out_path):
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__TITLE__", f"{data['league']} Trade Board").replace("/*__DATA__*/null", json.dumps(data))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
