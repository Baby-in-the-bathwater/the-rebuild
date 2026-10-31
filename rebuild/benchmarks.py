"""What wins in this format: pooled benchmarks from many league-seasons of the same family.

A. positional weights by season and champion profiles
B. rebuild trajectories (bottom-3 teams in a season: what they did, where they finished in N+1..N+3)
C. rookie pick hit rates by slot and position
The output is a plain dict (saved as JSON) with aggregate tables only: no manager names, no rosters."""
import json
import statistics as st
import time
from collections import Counter, defaultdict

from .crawl import classify
from .league import fmt_key, same_family
from .metrics import METRICS, TH, age_at, corr, ols, quantiles, rookie_in, team_rows, zwithin
from .sleeper import position

POS4 = ("QB", "RB", "WR", "TE")
BEHAVIOURS = ("sold for picks", "bought (sent picks)", "churned (no net picks)", "stood pat")


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def usable_rows(bundles, pdb, target_fmt, min_rosters=None):
    """Team rows for every bundle in the family with enough weeks; z-scored within league-season."""
    rows = []
    kept = 0
    for lid, b in bundles.items():
        cls = classify(target_fmt, b["league"])
        if not cls:
            continue
        n = min_rosters or target_fmt["teams"]
        if len(b.get("matchups") or {}) < 6 or len(b.get("rosters") or []) < n:
            continue
        rs = team_rows(b, pdb)
        if len(rs) >= n - 2:
            for r in rs:
                r["cls"] = cls
            rows.extend(rs)
            kept += 1
    zwithin(rows)
    return rows, kept


def behaviour(r1_net, pk_net, ntr):
    if ntr == 0:
        return "stood pat"
    if r1_net >= 1 or pk_net >= 2:
        return "sold for picks"
    if r1_net <= -1 or pk_net <= -2:
        return "bought (sent picks)"
    return "churned (no net picks)"


def trade_ledger(b, rid, pdb, min_week=1, max_week=18):
    season = b["league"]["season"]
    out = {"n": 0, "pl_in": [], "pl_out": [], "pk_in": 0, "pk_out": 0, "r1_in": 0, "r1_out": 0}
    for t in b.get("trades") or []:
        leg = t.get("leg") or 1
        if rid not in (t.get("roster_ids") or []) or leg < min_week or leg > max_week:
            continue
        out["n"] += 1
        for pid, r in (t.get("adds") or {}).items():
            if r == rid:
                out["pl_in"].append(pid)
        for pid, r in (t.get("drops") or {}).items():
            if r == rid:
                out["pl_out"].append(pid)
        for pk in t.get("draft_picks") or []:
            if pk.get("owner_id") == rid:
                out["pk_in"] += 1
                out["r1_in"] += int(pk.get("round") == 1)
            if pk.get("previous_owner_id") == rid:
                out["pk_out"] += 1
                out["r1_out"] += int(pk.get("round") == 1)

    def mage(pids):
        xs = [age_at(pdb, p, season) for p in pids if position(pdb, p) in TH and age_at(pdb, p, season)]
        return st.mean(xs) if xs else None
    out["age_in"], out["age_out"] = mage(out["pl_in"]), mage(out["pl_out"])
    return out


def lineages_from(bundles):
    """{root id: {season: league id}} following previous_league_id inside the loaded bundles."""
    out = {}
    children = {b["league"].get("previous_league_id") for b in bundles.values()}
    for lid, b in bundles.items():
        if lid in children:
            continue  # not a root (some later season points back to it)
        chain = {}
        cur = lid
        while cur and cur in bundles:
            chain[str(bundles[cur]["league"]["season"])] = cur
            cur = bundles[cur]["league"].get("previous_league_id")
        out[lid] = chain
    return out


def trajectories(bundles, rows, pdb, bottom=3):
    by_league = defaultdict(list)
    for r in rows:
        by_league[r["league"]].append(r)
    traj = []
    for root, bys in lineages_from(bundles).items():
        for s in sorted(bys):
            n1, n2, n3 = str(int(s) + 1), str(int(s) + 2), str(int(s) + 3)
            if n1 not in bys:
                continue
            rs_n = by_league.get(bys[s], [])
            if len(rs_n) < 10 or bundles[bys[s]]["league"]["status"] != "complete":
                continue
            ranked = sorted(rs_n, key=lambda r: (r["winpct"], r["ppg"]))
            ranks = {r["rid"]: i + 1 for i, r in enumerate(ranked)}

            def find(season, rid):
                if season not in bys:
                    return None, None
                rs = by_league.get(bys[season], [])
                srt = sorted(rs, key=lambda x: (-x["winpct"], -x["ppg"]))
                rk = {x["rid"]: i + 1 for i, x in enumerate(srt)}
                x = next((x for x in rs if x["rid"] == rid), None)
                return x, (rk.get(rid) if x else None)

            for r in ranked[:bottom]:
                rid = r["rid"]
                x1, rk1 = find(n1, rid)
                x2, rk2 = find(n2, rid)
                x3, rk3 = find(n3, rid)
                tN = trade_ledger(bundles[bys[s]], rid, pdb, min_week=8)
                tN1 = trade_ledger(bundles[bys[n1]], rid, pdb)
                tN1o = trade_ledger(bundles[bys[n1]], rid, pdb, max_week=1)  # offseason trades file under week 1
                pk_net = tN["pk_in"] - tN["pk_out"] + tN1["pk_in"] - tN1["pk_out"]
                r1_net = tN["r1_in"] - tN["r1_out"] + tN1["r1_in"] - tN1["r1_out"]
                ntr = tN["n"] + tN1["n"]
                pk_pre = tN["pk_in"] - tN["pk_out"] + tN1o["pk_in"] - tN1o["pk_out"]
                r1_pre = tN["r1_in"] - tN["r1_out"] + tN1o["r1_in"] - tN1o["r1_out"]
                ntr_pre = tN["n"] + tN1o["n"]
                traj.append({
                    "season": s, "rank_n": ranks[rid], "zppg_n": r["z_ppg"], "depth_n": r["depth"], "age_n": r["starter_age"],
                    "same_owner_n1": ((x1 or {}).get("owner") == r["owner"]) if x1 else None,
                    "trades": ntr, "pk_net": pk_net, "r1_net": r1_net, "behaviour": behaviour(r1_net, pk_net, ntr),
                    "trades_pre": ntr_pre, "pk_net_pre": pk_pre, "r1_net_pre": r1_pre, "behaviour_pre": behaviour(r1_pre, pk_pre, ntr_pre),
                    "age_in": _mean([tN["age_in"], tN1["age_in"]]), "age_out": _mean([tN["age_out"], tN1["age_out"]]),
                    "rank_n1": rk1, "win_n1": (x1 or {}).get("winpct"), "po_n1": (x1 or {}).get("playoff"), "champ_n1": (x1 or {}).get("champ"),
                    "rank_n2": rk2, "win_n2": (x2 or {}).get("winpct"), "po_n2": (x2 or {}).get("playoff"), "champ_n2": (x2 or {}).get("champ"),
                    "rank_n3": rk3, "win_n3": (x3 or {}).get("winpct"), "po_n3": (x3 or {}).get("playoff"), "champ_n3": (x3 or {}).get("champ"),
                })
    return traj


def summarize(cases):
    def m(k):
        xs = [c[k] for c in cases if c.get(k) is not None]
        return (st.mean(xs) if xs else None, len(xs))
    out = {"n": len(cases)}
    for h in ("1", "2", "3"):
        w, nw = m("win_n" + h)
        out["win" + h], out["n" + h] = w, nw
        out["rank" + h] = m("rank_n" + h)[0]
        out["po" + h] = m("po_n" + h)[0]
        out["champ" + h] = m("champ_n" + h)[0]
    return out


def trajectory_tables(traj):
    groups = [("All bottom-3 teams", traj),
              ("Same manager kept the team", [t for t in traj if t["same_owner_n1"] is True]),
              ("New manager took it over (orphan)", [t for t in traj if t["same_owner_n1"] is False])]
    groups += [(f"Behaviour late-N through N+1: {b}", [t for t in traj if t["behaviour"] == b]) for b in BEHAVIOURS]
    groups += [("Net +2 or more first-round picks acquired", [t for t in traj if t["r1_net"] >= 2]),
               ("Got younger (sent players 2+ years older than received)", [t for t in traj if t["age_out"] and t["age_in"] and t["age_out"] - t["age_in"] >= 2]),
               ("Got older (received players 2+ years older than sent)", [t for t in traj if t["age_out"] and t["age_in"] and t["age_in"] - t["age_out"] >= 2]),
               ("6+ trades", [t for t in traj if t["trades"] >= 6]),
               ("1 to 2 trades", [t for t in traj if 1 <= t["trades"] <= 2])]
    pre = [(f"Pre-season: {b}", [t for t in traj if t["behaviour_pre"] == b]) for b in BEHAVIOURS]
    pre += [("Pre-season: net +2 or more 1sts", [t for t in traj if t["r1_net_pre"] >= 2]),
            ("Pre-season: net +1 1st", [t for t in traj if t["r1_net_pre"] == 1]),
            ("Pre-season: 4+ trades", [t for t in traj if t["trades_pre"] >= 4])]
    orph = [t for t in traj if t["same_owner_n1"] is False]
    orphan = [(f"Orphan: {b}", [t for t in orph if t["behaviour"] == b]) for b in BEHAVIOURS]
    orphan += [("Orphan: 6+ trades", [t for t in orph if t["trades"] >= 6]),
               ("Orphan: 0 to 2 trades", [t for t in orph if t["trades"] <= 2]),
               ("Orphan: inherited starters under 26", [t for t in orph if t["age_n"] and t["age_n"] < 26]),
               ("Orphan: inherited starters 27+", [t for t in orph if t["age_n"] and t["age_n"] >= 27])]
    tables = {"main": [{"group": g, **summarize(c)} for g, c in groups],
              "pre": [{"group": g, **summarize(c)} for g, c in pre],
              "orphan": [{"group": g, **summarize(c)} for g, c in orphan]}
    for t in traj:
        t["orphan"] = int(t["same_owner_n1"] is False)
    c2 = [t for t in traj if t.get("win_n2") is not None and t["age_n"] is not None]
    coef, r2, n = ols(c2, ["zppg_n", "depth_n", "age_n", "r1_net", "pk_net", "trades", "orphan"], "win_n2")
    tables["ols_n2"] = {"coef": coef, "r2": r2, "n": n}
    c3 = [t for t in traj if t.get("win_n3") is not None and t["age_n"] is not None]
    coef3, r23, n3 = ols(c3, ["zppg_n", "depth_n", "age_n", "r1_net", "pk_net", "trades", "orphan"], "win_n3")
    tables["ols_n3"] = {"coef": coef3, "r2": r23, "n": n3}
    tables["cases"] = len(traj)
    return tables


def pick_hit_rates(bundles, rows, pdb, this_season, n_teams):
    by_season = {r["season"] for r in rows}
    ps = defaultdict(lambda: defaultdict(dict))  # season -> pid -> {week: pts} (max across leagues)
    for b in bundles.values():
        season = str(b["league"]["season"])
        for wk, ms in (b.get("matchups") or {}).items():
            for m in ms:
                for pid, p in (m.get("players_points") or {}).items():
                    prev = ps[season][pid].get(int(wk))
                    if prev is None or p > prev:
                        ps[season][pid][int(wk)] = p
    avg, posrank = {}, {}
    for season, d in ps.items():
        byp = defaultdict(list)
        for pid, wks in d.items():
            if len(wks) >= 6:
                ppg = sum(wks.values()) / len(wks)
                avg[(season, pid)] = ppg
                pz = position(pdb, pid)
                if pz in TH:
                    byp[pz].append((ppg, pid))
        for lst in byp.values():
            for i, (_, pid) in enumerate(sorted(lst, reverse=True)):
                posrank[(season, pid)] = i + 1

    def hit(pid, season, horizon, bar):
        p = position(pdb, pid)
        if p not in TH:
            return None
        seasons = [str(int(season) + k) for k in range(horizon)]
        if not any(s in by_season for s in seasons):
            return None
        if bar == "startable":
            return any(avg.get((s, pid), -1) >= TH[p] for s in seasons)
        lim = 12 if bar == "top12" else 24
        return any(posrank.get((s, pid), 999) <= lim for s in seasons)

    third = n_teams / 3.0
    picks = []
    for b in bundles.values():
        season = str(b["league"]["season"])
        if int(season) >= this_season:
            continue
        for d in b.get("drafts") or []:
            pk = (b.get("picks") or {}).get(d["draft_id"]) or []
            if not pk:
                continue
            rookies = [x for x in pk if x.get("player_id") and rookie_in(pdb, x["player_id"], season, this_season)]
            if len(rookies) < 0.7 * len(pk):
                continue  # startup draft
            for x in pk:
                pid = x.get("player_id")
                rd = x.get("round")
                if not pid or rd is None:
                    continue
                slot = x.get("pick_no") or 0
                if rd == 1:
                    bucket = "early 1st" if slot <= third else ("mid 1st" if slot <= 2 * third else "late 1st")
                elif rd in (2, 3):
                    bucket = f"round {rd}"
                else:
                    bucket = "round 4+"
                picks.append({"season": season, "bucket": bucket, "round": rd, "pos": position(pdb, pid),
                              "startable1": hit(pid, season, 1, "startable"), "startable3": hit(pid, season, 3, "startable"),
                              "top24_3": hit(pid, season, 3, "top24"), "top12_3": hit(pid, season, 3, "top12"), "top12_1": hit(pid, season, 1, "top12")})
    buckets = ("early 1st", "mid 1st", "late 1st", "round 2", "round 3")

    def rate(sub, k):
        xs = [p[k] for p in sub if p[k] is not None]
        return (st.mean(xs), len(xs)) if xs else (None, 0)
    table = []
    for bk in buckets:
        sub = [p for p in picks if p["bucket"] == bk]
        if not sub:
            continue
        pc = Counter(p["pos"] for p in sub)
        row = {"slot": bk, "n": len(sub)}
        for k in ("startable1", "startable3", "top24_3", "top12_3", "top12_1"):
            row[k] = rate(sub, k)[0]
        for p_ in POS4:
            row["share_" + p_] = pc[p_] / len(sub)
        table.append(row)
    by_pos = {}
    for bar in ("top12_3", "top24_3"):
        by_pos[bar] = {}
        for p_ in POS4:
            by_pos[bar][p_] = {}
            for bk in buckets:
                r, n = rate([p for p in picks if p["pos"] == p_ and p["bucket"] == bk], bar)
                by_pos[bar][p_][bk] = {"rate": r, "n": n}
    classes = sorted({p["season"] for p in picks})
    return {"n": len(picks), "classes": classes, "table": table, "by_pos": by_pos,
            "first_round_top24_by_class": {s: rate([p for p in picks if p["season"] == s and p["round"] == 1], "top24_3") for s in classes}}


def build(bundles, pdb, target_fmt, this_season, label=None, log=print):
    t0 = time.time()
    rows, nleagues = usable_rows(bundles, pdb, target_fmt)
    by_season = defaultdict(list)
    for r in rows:
        by_season[r["season"]].append(r)
    log(f"  benchmarks: {nleagues} league-seasons usable, {len(rows)} team-seasons, seasons {min(by_season) if by_season else '-'}..{max(by_season) if by_season else '-'}")
    bm = {"label": label or fmt_key(target_fmt), "format": target_fmt, "built": time.strftime("%Y-%m-%d"),
          "league_seasons": nleagues, "team_seasons": len(rows),
          "seasons": {s: {"leagues": len({r["league"] for r in rs}), "teams": len(rs), "weeks": st.median(r["weeks"] for r in rs)} for s, rs in sorted(by_season.items())}}
    pos_keys = ["z_QB", "z_RB", "z_WR", "z_TE", "z_DEF"]
    bm["coef_by_season"] = {}
    for s, rs in sorted(by_season.items()):
        coef, r2, n = ols(rs, pos_keys, "z_winpct")
        cs = {m: corr([r["z_" + m] if r.get("z_" + m) is not None else float("nan") for r in rs], [r["z_winpct"] for r in rs]) for m in ("QB", "RB", "WR", "TE", "depth", "sf_qb_rate", "floor", "starter_age")}
        bm["coef_by_season"][s] = {"n": n, "coef": {k[2:]: v for k, v in coef.items()}, "r2": r2, "corr": cs}
    coef, r2, n = ols(rows, pos_keys, "z_winpct")
    bm["coef_pooled"] = {"n": n, "coef": {k[2:]: v for k, v in coef.items()}, "r2": r2}
    coef2, r22, _ = ols(rows, pos_keys + ["z_depth", "z_sf_qb_rate"], "z_winpct")
    bm["coef_pooled_depth"] = {"coef": {k[2:]: v for k, v in coef2.items()}, "r2": r22}
    comp = [r for r in rows if int(r["season"]) < this_season and bundles[r["league"]]["league"]["status"] == "complete"]
    champs = [r for r in comp if r["champ"]]
    po = [r for r in comp if r["playoff"]]
    npo = [r for r in comp if not r["playoff"]]
    prof = {}
    for m in ("ppg", "QB", "RB", "WR", "TE", "DEF", "depth", "depQB", "depRB", "depWR", "depTE", "sf_qb_rate", "eff", "floor", "te_share", "starter_age"):
        prof[m] = {"champ_z": _mean([r.get("z_" + m) for r in champs]), "playoff_z": _mean([r.get("z_" + m) for r in po]), "nonplayoff_z": _mean([r.get("z_" + m) for r in npo]),
                   "champ_raw": _mean([r[m] for r in champs]), "field_raw": _mean([r[m] for r in comp])}
    bm["champions"] = {"n": len(champs), "field": len(comp), "profile": prof,
                       "carried_by": dict(Counter(max(POS4, key=lambda m: r.get("z_" + m) or -9) for r in champs))}
    bm["depth_buckets"] = [{"lo": lo, "hi": hi, "n": len(sub), "win": _mean([r["winpct"] for r in sub]), "playoff": _mean([r["playoff"] for r in sub]), "champ": _mean([r["champ"] for r in sub])}
                           for lo, hi in ((0, 5), (5, 7), (7, 9), (9, 11), (11, 99)) for sub in [[r for r in comp if lo <= r["depth"] < hi]] if sub]
    if target_fmt["superflex"]:
        bm["sf_qb_buckets"] = [{"label": lab, "n": len(sub), "win": _mean([r["winpct"] for r in sub]), "playoff": _mean([r["playoff"] for r in sub])}
                               for lo, hi, lab in ((0, .5, "QB in the Superflex under half the weeks"), (.5, .99, "half to most weeks"), (.99, 1.01, "every week"))
                               for sub in [[r for r in comp if lo <= r["sf_qb_rate"] < hi]] if sub]
    ages = [r for r in comp if r["starter_age"] is not None]
    bm["age_buckets"] = [{"label": lab, "lo": lo, "hi": hi, "n": len(sub), "win": _mean([r["winpct"] for r in sub]), "champ": _mean([r["champ"] for r in sub]), "playoff": _mean([r["playoff"] for r in sub])}
                         for lab, lo, hi in (("under 25", 0, 25), ("25 to 26", 25, 26), ("26 to 27", 26, 27), ("27 to 28", 27, 28), ("28 and up", 28, 99))
                         for sub in [[r for r in ages if lo <= r["starter_age"] < hi]] if sub]
    bm["age_corr"] = corr([r["z_starter_age"] for r in ages], [r["z_winpct"] for r in ages]) if ages else None
    bm["quantiles"] = {m: quantiles([r.get("z_" + m) for r in rows]) for m in METRICS}
    bm["raw_quantiles"] = {m: quantiles([r.get(m) for r in rows]) for m in METRICS}
    log("  benchmarks: trajectories")
    bm["trajectories"] = trajectory_tables(trajectories(bundles, rows, pdb))
    log("  benchmarks: rookie pick hit rates")
    bm["picks"] = pick_hit_rates(bundles, rows, pdb, this_season, target_fmt["teams"])
    bm["base_rates"] = {"playoff": target_fmt["playoff_teams"] / target_fmt["teams"] if target_fmt.get("playoff_teams") else None, "champ": 1 / target_fmt["teams"]}
    log(f"  benchmarks built in {time.time() - t0:.0f}s")
    return bm


def save(bm, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bm, f, indent=0)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_shipped(bm_dir, target_fmt):
    """A shipped benchmark that matches the league's format family, or None."""
    import glob
    import os
    best = None
    for p in glob.glob(os.path.join(bm_dir, "*.json")):
        try:
            bm = load(p)
        except (OSError, ValueError):
            continue
        f = bm.get("format") or {}
        if same_family(target_fmt, {**f, "best_ball": False}):
            if best is None or bm.get("team_seasons", 0) > best.get("team_seasons", 0):
                best = bm
                best["_path"] = p
    return best
