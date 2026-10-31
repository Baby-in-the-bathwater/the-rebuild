"""Team-season metrics from a league bundle (league + rosters + weekly matchups + bracket).

Everything downstream (benchmarks, grading, history) works from the rows this module produces, so a
team in the target league and a team in a 2019 pooled league are measured the same way."""
import datetime as dt
import statistics as st
from collections import defaultdict

import numpy as np

from .sleeper import position

# Per-game thresholds for a "startable" player in a 12-team lineup. Flex-level production.
TH = {"QB": 14.0, "RB": 9.0, "WR": 9.0, "TE": 7.0}
METRICS = ["ppg", "QB", "RB", "WR", "TE", "DEF", "te_share", "eff", "sf_qb_rate", "floor", "above_med",
           "depQB", "depRB", "depWR", "depTE", "depth", "starter_age"]
MIN_WEEKS = 6


def age_at(pdb, pid, season):
    bd = (pdb.get(pid) or {}).get("birth_date")
    if not bd:
        return None
    try:
        y, m, d = map(int, bd.split("-"))
        return (dt.date(int(season), 9, 1) - dt.date(y, m, d)).days / 365.25
    except ValueError:
        return None


def rookie_in(pdb, pid, season, this_season):
    ye = (pdb.get(pid) or {}).get("years_exp")
    return ye is not None and ye - (this_season - int(season)) == 0


def optimal_points(rp, pp, pos):
    """Best possible lineup score for a week given roster_positions and {pid: points}."""
    bp = defaultdict(list)
    for pid, p in pp.items():
        bp[pos(pid)].append(p)
    for k in bp:
        bp[k].sort(reverse=True)

    def take(k, n):
        out = bp[k][:n]
        del bp[k][:n]
        return sum(out)

    opt = sum(take(k, rp.count(k)) for k in ("QB", "RB", "WR", "TE", "DEF", "K"))
    nflex = rp.count("FLEX")
    nsf = rp.count("SUPER_FLEX")
    rest = sorted(bp["RB"] + bp["WR"] + bp["TE"], reverse=True)
    qbs = bp["QB"]
    # each SUPER_FLEX slot takes a QB if one is left and beats the next flex option
    sf_pts = 0.0
    for _ in range(nsf):
        q = qbs.pop(0) if qbs else None
        nxt = rest[nflex] if len(rest) > nflex else 0.0
        if q is not None and q >= nxt:
            sf_pts += q
        else:
            sf_pts += rest.pop(nflex) if len(rest) > nflex else 0.0
    return opt + sum(rest[:nflex]) + sf_pts


def team_rows(bundle, pdb):
    lg = bundle["league"]
    season = str(lg["season"])
    rp = lg.get("roster_positions") or []
    pos = lambda pid: position(pdb, pid)  # noqa: E731
    sf_idx = [i for i, p in enumerate(rp) if p == "SUPER_FLEX"]
    rosters = {r["roster_id"]: r for r in (bundle.get("rosters") or [])}
    weekly = defaultdict(list)
    pp_hist = defaultdict(lambda: defaultdict(list))
    starter_age = defaultdict(list)
    for wk, ms in (bundle.get("matchups") or {}).items():
        for m in ms:
            rid = m["roster_id"]
            pp = m.get("players_points") or {}
            starters = m.get("starters") or []
            if not pp or not starters or sum(pp.values()) == 0:
                continue
            bypos = defaultdict(float)
            for s in starters:
                if s and s != "0":
                    bypos[pos(s)] += pp.get(s, 0.0)
                    a = age_at(pdb, s, season)
                    if a and pos(s) in TH:
                        starter_age[rid].append(a)
            sf_qb = False
            if sf_idx and len(starters) > sf_idx[0]:
                sp = starters[sf_idx[0]]
                sf_qb = bool(sp and sp != "0" and pos(sp) == "QB")
            tot = sum(pp.get(s, 0.0) for s in starters if s and s != "0")
            weekly[rid].append({"wk": int(wk), "pts": tot, "bypos": dict(bypos), "opt": optimal_points(rp, pp, pos), "sf_qb": sf_qb})
            for pid in (m.get("players") or []):
                pp_hist[rid][pid].append(pp.get(pid, 0.0))
    if not weekly:
        return []
    weeks = sorted({w["wk"] for ws in weekly.values() for w in ws})
    med = {wk: st.median([w["pts"] for ws in weekly.values() for w in ws if w["wk"] == wk]) for wk in weeks}
    bracket = bundle.get("winners_bracket") or []
    champ = next((x.get("w") for x in bracket if x.get("p") == 1), None)
    playoff_rids = {x.get(k) for x in bracket for k in ("t1", "t2") if isinstance(x.get(k), int)}
    rows = []
    for rid, ws in weekly.items():
        n = len(ws)
        if n < MIN_WEEKS:
            continue
        tot = sum(w["pts"] for w in ws)
        if tot <= 0:
            continue
        agg = defaultdict(float)
        for w in ws:
            for k, v in w["bypos"].items():
                agg[k] += v
        r = rosters.get(rid, {})
        s = r.get("settings", {})
        g = s.get("wins", 0) + s.get("losses", 0) + s.get("ties", 0)
        if g == 0:
            continue
        dep = defaultdict(int)
        for pid in (r.get("players") or []):
            p = pos(pid)
            h = pp_hist[rid].get(pid) or []
            if p in TH and h and (sum(h) / len(h)) >= TH[p]:
                dep[p] += 1
        pts = [w["pts"] for w in ws]
        rows.append({
            "league": lg["league_id"], "season": season, "rid": rid, "owner": r.get("owner_id"),
            "wins": s.get("wins", 0), "losses": s.get("losses", 0), "ties": s.get("ties", 0),
            "winpct": (s.get("wins", 0) + 0.5 * s.get("ties", 0)) / g,
            "champ": int(champ == rid), "playoff": int(rid in playoff_rids),
            "ppg": tot / n, "QB": agg["QB"] / n, "RB": agg["RB"] / n, "WR": agg["WR"] / n, "TE": agg["TE"] / n, "DEF": agg["DEF"] / n,
            "te_share": agg["TE"] / tot, "eff": tot / sum(w["opt"] for w in ws) if sum(w["opt"] for w in ws) else 0.0,
            "sf_qb_rate": sum(1 for w in ws if w["sf_qb"]) / n,
            "floor": min(pts), "above_med": sum(1 for w in ws if w["pts"] > med[w["wk"]]) / n,
            "depQB": dep["QB"], "depRB": dep["RB"], "depWR": dep["WR"], "depTE": dep["TE"], "depth": sum(dep.values()),
            "starter_age": st.mean(starter_age[rid]) if starter_age[rid] else None,
            "weeks": n,
        })
    return rows


def zwithin(rows, keys=None):
    """Add z_<metric> columns, standardized within each league-season."""
    keys = keys or METRICS + ["winpct"]
    by = defaultdict(list)
    for r in rows:
        by[r["league"]].append(r)
    for rs in by.values():
        for m in keys:
            xs = [r[m] for r in rs if r.get(m) is not None]
            if not xs:
                for r in rs:
                    r["z_" + m] = None
                continue
            mu = st.mean(xs)
            sd = st.pstdev(xs) or 1.0
            for r in rs:
                r["z_" + m] = (r[m] - mu) / sd if r.get(m) is not None else None
    return rows


def corr(xs, ys):
    xs, ys = np.array(xs, float), np.array(ys, float)
    ok = ~np.isnan(xs) & ~np.isnan(ys)
    return float(np.corrcoef(xs[ok], ys[ok])[0, 1]) if ok.sum() > 3 else float("nan")


def ols(rows, xkeys, ykey):
    """Least squares with intercept; returns (coefficients by key, r2, n)."""
    rs = [r for r in rows if all(r.get(k) is not None for k in xkeys + [ykey])]
    if len(rs) < len(xkeys) + 3:
        return {k: float("nan") for k in xkeys}, float("nan"), len(rs)
    X = np.array([[1.0] + [r[k] for k in xkeys] for r in rs])
    y = np.array([r[ykey] for r in rs], float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ((y - pred) ** 2).sum() / ss if ss else float("nan")
    return dict(zip(xkeys, map(float, beta[1:]))), float(r2), len(rs)


def quantiles(xs, n=101):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return []
    return [xs[min(len(xs) - 1, int(round(i / (n - 1) * (len(xs) - 1))))] for i in range(n)]


def percentile(q, x):
    """Percentile (0-100) of x against a stored quantile ladder."""
    if not q or x is None:
        return None
    return round(100 * sum(1 for v in q if v < x) / len(q))
