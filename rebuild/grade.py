"""Grade one roster against its league and against the pooled benchmark, then make the call: contend, retool, or rebuild."""
import statistics as st
from collections import defaultdict

from .metrics import TH, percentile, team_rows, zwithin

POS_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
# age at which a position's dynasty value starts falling fast; the sell list keys off this
SELL_AGE = {"QB": 30, "RB": 25, "WR": 27, "TE": 28}


def team_assets(league, values, rid):
    """Players (with age, ppg, value, startable flag) and picks (with values) for one roster."""
    r = league.roster(rid)
    reserve = set(r.get("reserve") or [])
    taxi = set(r.get("taxi") or [])
    starters = set(r.get("starters") or [])
    players = []
    for pid in (r.get("players") or []):
        p = league.player(pid)
        ppg, g = league.ppg(pid)
        pos = p.get("position") or "?"
        players.append({"id": pid, "name": p.get("full_name") or pid, "pos": pos, "team": p.get("team") or "FA", "age": p.get("age"),
                        "years_exp": p.get("years_exp"), "ppg": ppg, "gp": g, "value": values.player(p), "ir": pid in reserve, "taxi": pid in taxi,
                        "inj": p.get("injury_status") or "", "starter": pid in starters,
                        "startable": bool(pos in TH and g >= 3 and ppg >= TH[pos])})
    players.sort(key=lambda x: (POS_ORDER.get(x["pos"], 9), -x["value"]))
    picks = []
    for pk in league.picks.get(rid, []):
        slot = league.proj_slot[pk["orig_rid"]]
        picks.append({**pk, "proj_slot": slot if pk["season"] == league.pick_seasons[0] else None,
                      "value": values.pick(pk["season"], pk["round"], slot, league.n, league.season, league.draft_pending),
                      "key": f"{pk['season']}-{pk['round']}-{pk['orig_rid']}"})
    picks.sort(key=lambda x: (x["season"], x["round"], league.proj_slot[x["orig_rid"]]))
    w, l, pf = league.record[rid]
    return {"rid": rid, "name": league.team_name[rid], "owner": league.owner_name[rid], "wins": w, "losses": l, "pf": pf,
            "rank": league.rank[rid], "proj_slot": league.proj_slot[rid],
            "player_value": sum(p["value"] for p in players), "pick_value": sum(p["value"] for p in picks),
            "startable": sum(1 for p in players if p["startable"]),
            "firsts": {s: sum(1 for p in picks if p["season"] == s and p["round"] == 1) for s in league.pick_seasons},
            "players": players, "picks": picks}


def ordn(k):
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def core_age(players, n=8):
    core = sorted([p for p in players if p["pos"] in TH and p["age"]], key=lambda p: -p["value"])[:n]
    return st.mean(p["age"] for p in core) if core else None


def grade(league, values, rid, bm, own_bundle):
    teams = {t: team_assets(league, values, t) for t in league.team_name}
    me = teams[rid]
    rows = zwithin(team_rows(own_bundle, league.pdb)) if own_bundle.get("matchups") else []
    by_rid = {r["rid"]: r for r in rows}
    row = by_rid.get(rid)
    n = league.n
    # ranks within the league on the asset ledger
    def rank_of(key, reverse=True):
        order = sorted(teams.values(), key=lambda t: t[key], reverse=reverse)
        return next(i + 1 for i, t in enumerate(order) if t["rid"] == rid)
    me["core_age"] = core_age(me["players"])
    for t in teams.values():
        t["core_age"] = core_age(t["players"])
        t["total_value"] = t["player_value"] + t["pick_value"]
    ledger_rank = {"player_value": rank_of("player_value"), "pick_value": rank_of("pick_value"), "total_value": rank_of("total_value"),
                   "startable": rank_of("startable"), "core_age": sorted(t["core_age"] or 99 for t in teams.values()).index(me["core_age"] or 99) + 1}
    # percentiles against the pool (within-league z, so they are format-neutral)
    pct = {}
    if row and bm:
        for m in ("ppg", "QB", "RB", "WR", "TE", "depth", "depQB", "depRB", "depWR", "depTE", "floor", "above_med", "eff", "sf_qb_rate", "starter_age"):
            pct[m] = percentile(bm["quantiles"].get(m), row.get("z_" + m))
    # the call
    rank_pct = (n - me["rank"]) / (n - 1) if n > 1 else 0.5
    depth_pct = (pct.get("depth") if pct.get("depth") is not None else 50) / 100
    value_pct = (n - ledger_rank["total_value"]) / (n - 1)
    old = me["core_age"] is not None and me["core_age"] >= 27
    young = me["core_age"] is not None and me["core_age"] < 25.5
    reasons = []
    if league.redraft:
        mode = "contend"
        reasons.append(f"redraft league: there is no next season to build for, so every move is for {league.season}; "
                       f"{ordn(me['rank'])} of {n} with startable depth at the {int(depth_pct*100)}th percentile of the pool")
    elif rank_pct >= 0.6 and depth_pct >= 0.5:
        mode = "contend"
        reasons.append(f"top-{me['rank']} record with startable depth at the {int(depth_pct*100)}th percentile of the pool")
    elif rank_pct <= 0.35 or (depth_pct <= 0.35 and value_pct <= 0.5):
        mode = "rebuild"
        reasons.append(f"{ordn(me['rank'])} of {n} with startable depth at the {int(depth_pct*100)}th percentile" if rank_pct <= 0.35 else
                       f"thin depth ({int(depth_pct*100)}th percentile) on a roster ranked {ledger_rank['total_value']}th in total value")
    else:
        mode = "retool"
        reasons.append(f"mid-table ({ordn(me['rank'])}) with depth at the {int(depth_pct*100)}th percentile: neither window is open")
    if old and not league.redraft:
        reasons.append(f"core age {me['core_age']:.1f}: the top-8 assets are past the age where this format's value curve turns down")
        if mode == "retool":
            mode = "rebuild"
    if young and mode == "rebuild":
        reasons.append(f"core age {me['core_age']:.1f}: young enough that the rebuild should be short")
    if value_pct <= 0.25:
        reasons.append(f"asset base ranks {ledger_rank['total_value']}th of {n} (players + picks)")
    if league.pick_seasons and me["firsts"].get(league.pick_seasons[0], 0) == 0:
        reasons.append(f"holds no {league.pick_seasons[0]} first-round pick")
    # target window: how many seasons until a realistic playoff push
    if mode == "contend":
        window = league.season
    elif mode == "retool":
        window = league.season + 1
    else:
        window = league.season + (2 if young and league.pick_seasons and me["firsts"].get(league.pick_seasons[0], 0) >= 1 else 3)
    now = sum(1 for p in me["players"] if p["pos"] in TH and p["startable"])
    if now - row["depth"] >= 2:
        reasons.append(f"roster as built today has {now} startable players against {row['depth']} produced for this team so far: "
                       f"mid-season additions and returning players have not scored here yet, so the depth percentile understates it")

    return {"team": me, "teams": teams, "row": row, "rows": rows, "pct": pct, "ledger_rank": ledger_rank,
            "mode": mode, "reasons": reasons, "window": window, "n": n}
