"""The league's own trade history, priced twice: with the DynastyProcess values from the week of each trade
(was it fair when it was made?) and with today's values (who came out ahead?), plus the starter points each
side got from what it received. Then what the league's trades say about how it prices positions, picks and age.

Historical values come from the git history of the DynastyProcess data repo (one values.csv commit a week
since 2019). Each snapshot is immutable, so it is downloaded once and cached under cache/dp_history/."""
import csv
import datetime as dt
import io
import json
import os
import time
from collections import defaultdict

import requests

from .values import Values

COMMITS_URL = "https://api.github.com/repos/dynastyprocess/data/commits"
RAW_URL = "https://raw.githubusercontent.com/dynastyprocess/data/{sha}/files/values.csv"
EVEN_BAND = 0.10      # a side within 10% of the other on received value is an even trade
MIN_EDGE = 150        # and an edge under this many value points is noise (two near-worthless sides are even)
PREMIUM_BAND = 0.08   # league pays at least 8% over (or under) market before we call it a premium (or discount)
THIN = 5              # fewer trades than this in a category: show it, but flag it as thin


# ------------------------------------------------------------------ DynastyProcess snapshots
def snapshot_index(cache_dir, ttl=6 * 24 * 3600):
    """[(iso date, sha)] for every values.csv commit, oldest first. Cached for most of a week."""
    d = os.path.join(cache_dir, "dp_history")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "commits.json")
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    out, page = [], 1
    while True:
        r = requests.get(COMMITS_URL, params={"path": "files/values.csv", "per_page": 100, "page": page}, timeout=30,
                         headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        batch = r.json()
        out += [(c["commit"]["committer"]["date"], c["sha"]) for c in batch]
        if len(batch) < 100:
            break
        page += 1
    out.sort()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def snapshot_values(cache_dir, sha, superflex):
    p = os.path.join(cache_dir, "dp_history", f"{sha}.csv")
    if not os.path.exists(p):
        r = requests.get(RAW_URL.format(sha=sha), timeout=60)
        r.raise_for_status()
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(r.text)
    with open(p, encoding="utf-8") as f:
        return Values(list(csv.DictReader(io.StringIO(f.read()))), superflex)


def snapshot_for(index, when):
    """Latest snapshot committed on or before `when` (a datetime in UTC); the oldest one if the trade predates them all."""
    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    best = None
    for date, sha in index:
        if date <= iso:
            best = (date, sha)
        else:
            break
    return best or (index[0] if index else None)


# ------------------------------------------------------------------ league plumbing
def _draft_maps(bundle):
    """For the season's rookie draft: {(round, original roster): drafted player id} and the draft start (ms), or ({}, None)."""
    drafts = [d for d in (bundle.get("drafts") or []) if d.get("status") == "complete"]
    if not drafts:
        return {}, None
    d = drafts[0]
    picks = (bundle.get("picks") or {}).get(d["draft_id"]) or []
    owner_rid = {r.get("owner_id"): r["roster_id"] for r in bundle.get("rosters") or [] if r.get("owner_id")}
    slot_rid = {int(k): int(v) for k, v in (d.get("slot_to_roster_id") or {}).items()}
    if not slot_rid:
        for uid, slot in (d.get("draft_order") or {}).items():
            if uid in owner_rid:
                slot_rid[int(slot)] = owner_rid[uid]
        # one slot whose manager left before the bundle was pulled: the one roster nobody else claims
        slots = {int(p["draft_slot"]) for p in picks}
        free_slots = sorted(slots - set(slot_rid))
        free_rids = sorted({r["roster_id"] for r in bundle.get("rosters") or []} - set(slot_rid.values()))
        if len(free_slots) == 1 and len(free_rids) == 1:
            slot_rid[free_slots[0]] = free_rids[0]
    out = {}
    for p in picks:
        orig = slot_rid.get(int(p["draft_slot"]))
        if orig is not None and p.get("player_id"):
            out[(int(p["round"]), orig)] = p["player_id"]
    return out, d.get("start_time")


def _slot_of(bundle, rnd, orig):
    """Draft slot the original roster held in this season's draft (1-based), if known."""
    drafts = bundle.get("drafts") or []
    if not drafts:
        return None
    d = drafts[0]
    owner_rid = {r.get("owner_id"): r["roster_id"] for r in bundle.get("rosters") or [] if r.get("owner_id")}
    for uid, slot in (d.get("draft_order") or {}).items():
        if owner_rid.get(uid) == orig:
            return int(slot)
    for k, v in (d.get("slot_to_roster_id") or {}).items():
        if int(v) == orig:
            return int(k)
    return None


def _starter_points(bundles):
    """{(roster id, player id): [(season, week, points)]} for every week a player started for a roster."""
    out = defaultdict(list)
    for b in bundles:
        season = int(b["league"]["season"])
        for wk, ms in (b.get("matchups") or {}).items():
            for m in ms or []:
                pts = m.get("players_points") or {}
                for pid in m.get("starters") or []:
                    if pid and pid != "0":
                        out[(m["roster_id"], pid)].append((season, int(wk), pts.get(pid) or 0.0))
    return out


# ------------------------------------------------------------------ the history
def build(cache_dir, bundles, league, values, log=print):
    """Every completed trade across the league's seasons, priced then and now. `bundles` are the league's own
    season bundles (any order); `league` and `values` are today's. Returns the board's trade_history block."""
    seasons = sorted(bundles.values(), key=lambda b: int(b["league"]["season"]))
    trades = [(b, t) for b in seasons for t in (b.get("trades") or []) if t.get("status") == "complete"]
    if not trades:
        return None
    index = snapshot_index(cache_dir)
    superflex = league.fmt["superflex"]
    by_season = {int(b["league"]["season"]): b for b in seasons}
    drafted = {s: _draft_maps(b) for s, b in by_season.items()}
    started = _starter_points(seasons)
    pdb = league.pdb
    snaps = {}

    def snap(sha):
        if sha not in snaps:
            snaps[sha] = snapshot_values(cache_dir, sha, superflex)
        return snaps[sha]

    def pname(pid):
        p = pdb.get(pid) or {}
        return p.get("full_name") or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x) or pid

    def ppos(pid):
        p = pdb.get(pid) or {}
        fantasy = [x for x in p.get("fantasy_positions") or [] if x in ("QB", "RB", "WR", "TE")]
        return p.get("position") if p.get("position") in ("QB", "RB", "WR", "TE") else (fantasy[0] if fantasy else p.get("position") or "?")

    def pval(v, pid):
        p = dict(pdb.get(pid) or {})
        if not p.get("full_name"):
            p["full_name"] = pname(pid)
        # two-way players (Travis Hunter is a DB in Sleeper, a WR in the values feed): try each listed position
        for pos in [p.get("position")] + [x for x in p.get("fantasy_positions") or [] if x != p.get("position")]:
            val = v.player({**p, "position": pos})
            if val:
                return val
        return 0

    def age_on(pid, when):
        bd = (pdb.get(pid) or {}).get("birth_date")
        try:
            y, m, d = map(int, bd.split("-"))
            return round((when.date() - dt.date(y, m, d)).days / 365.25, 1)
        except (AttributeError, ValueError):
            return None

    def pts_after(rid, pid, season, week):
        return round(sum(p for s, w, p in started.get((rid, pid), []) if (s, w) >= (season, week)), 1)

    out = []
    for b, t in trades:
        season = int(b["league"]["season"])
        when = dt.datetime.fromtimestamp(t["created"] / 1000, tz=dt.timezone.utc)
        week = int(t.get("leg") or 1)
        users = {u["user_id"]: (u.get("display_name") or u.get("username") or "?") for u in b.get("users") or []}
        team = {u["user_id"]: ((u.get("metadata") or {}).get("team_name") or "").strip() for u in b.get("users") or []}
        owner = {r["roster_id"]: r.get("owner_id") for r in b.get("rosters") or []}
        n = len(b.get("rosters") or []) or league.n
        sd = snapshot_for(index, when)
        then = snap(sd[1]) if sd else None
        _, draft_start = drafted.get(season, ({}, None))
        draft_pending = draft_start is None or t["created"] < draft_start

        sides = {rid: {"rid": rid, "uid": owner.get(rid) or f"roster-{rid}", "manager": users.get(owner.get(rid), f"Team {rid}"),
                       "team": team.get(owner.get(rid)) or users.get(owner.get(rid), f"Team {rid}"),
                       "gets": [], "faab": 0} for rid in t.get("roster_ids") or []}
        for pid, rid in (t.get("adds") or {}).items():
            if rid not in sides:
                continue
            a = {"kind": "player", "id": pid, "from": (t.get("drops") or {}).get(pid), "label": pname(pid), "pos": ppos(pid), "age": age_on(pid, when),
                 "then": pval(then, pid) if then else 0, "now": pval(values, pid), "pts": pts_after(rid, pid, season, week)}
            sides[rid]["gets"].append(a)
        for pk in t.get("draft_picks") or []:
            rid = pk.get("owner_id")
            if rid not in sides:
                continue
            ps, rnd, orig = int(pk["season"]), int(pk["round"]), int(pk["roster_id"])
            # value then: exact slot for this season's pending draft, Mid tier for next season, flat or discounted beyond
            slot = _slot_of(by_season[ps], rnd, orig) if ps == season and ps in by_season else None
            v_then = then.pick(ps, rnd, slot or (n + 1) // 2, n, season, draft_pending) if then else 0
            dmap = drafted.get(ps, ({}, None))[0]
            took = dmap.get((rnd, orig))
            orig_owner = owner.get(orig)
            via = "" if orig == rid else f" via {team.get(orig_owner) or users.get(orig_owner) or f'Team {orig}'}"
            a = {"kind": "pick", "from": pk.get("previous_owner_id"), "label": f"{ps} R{rnd}{via}", "season": ps, "round": rnd, "then": v_then}
            if took:
                a.update({"became": pname(took), "became_pos": ppos(took), "now": pval(values, took),
                          "pts": pts_after(rid, took, ps, 1)})
            elif ps >= league.season and ps in [int(s) for s in league.pick_seasons]:
                a.update({"now": values.pick(ps, rnd, league.proj_slot.get(orig, (league.n + 1) // 2), league.n, league.season, league.draft_pending), "pts": 0.0})
            else:
                a.update({"now": 0, "pts": 0.0})   # a pick whose draft we cannot see (startup or missing): no value claimed
            sides[rid]["gets"].append(a)
        for wb in t.get("waiver_budget") or []:
            if wb.get("receiver") in sides:
                sides[wb["receiver"]]["faab"] += wb.get("amount") or 0
            if wb.get("sender") in sides:
                sides[wb["sender"]]["faab"] -= wb.get("amount") or 0

        # what a side gave is whatever left its roster (Sleeper's drops / previous_owner_id), so 3-team trades work too
        every = [a for s in sides.values() for a in s["gets"]]
        for rid, s in sides.items():
            gave = [a for a in every if a["from"] == rid] if len(sides) > 2 else [a for a in every if a not in s["gets"]]
            s["got_then"] = sum(a["then"] for a in s["gets"])
            s["got_now"] = sum(a["now"] for a in s["gets"])
            s["gave_then"] = sum(a["then"] for a in gave)
            s["gave_now"] = sum(a["now"] for a in gave)
            s["pts"] = round(sum(a["pts"] for a in s["gets"]), 1)
        for s in sides.values():
            s["pct_then"] = round(s["got_then"] / s["gave_then"] * 100) if s["gave_then"] else None
            s["pct_now"] = round(s["got_now"] / s["gave_now"] * 100) if s["gave_now"] else None

        def verdict(key_got, key_gave):
            best = max(sides.values(), key=lambda s: s[key_got] - s[key_gave])
            edge = best[key_got] - best[key_gave]
            return best["rid"] if edge >= MIN_EDGE and edge > EVEN_BAND * max(best[key_got], best[key_gave]) else None

        out.append({"id": t.get("transaction_id"), "date": when.strftime("%Y-%m-%d"), "season": season, "week": week,
                    "values_asof": sd[0][:10] if sd else None, "sides": list(sides.values()),
                    "winner_then": verdict("got_then", "gave_then"), "winner_now": verdict("got_now", "gave_now"),
                    "days_ago": (dt.datetime.now(dt.timezone.utc) - when).days})
    out.sort(key=lambda x: x["date"], reverse=True)
    log(f"trade history: {len(out)} trades across {len(seasons)} seasons, priced with {len(snaps)} weekly value snapshots")
    return {"trades": out, "managers": managers(out), "market": market(out), "values_now": values.asof}


# ------------------------------------------------------------------ who trades well
def managers(trades):
    """One row per Sleeper account (display names change; user ids do not), named by its most recent display name."""
    m = defaultdict(lambda: {"trades": 0, "won": 0, "lost": 0, "even": 0, "net_then": 0, "net_now": 0, "got_then": 0, "gave_then": 0,
                             "pts": 0.0, "teams": set(), "last": "", "manager": ""})
    for t in trades:   # newest first, so the first name seen is the current one
        for s in t["sides"]:
            r = m[s["uid"]]
            r["manager"] = r["manager"] or s["manager"]
            r["trades"] += 1
            r["teams"].add(s["team"])
            r["last"] = max(r["last"], t["date"])
            r["got_then"] += s["got_then"]
            r["gave_then"] += s["gave_then"]
            r["net_then"] += s["got_then"] - (s["gave_then"] or 0)
            r["net_now"] += s["got_now"] - (s["gave_now"] or 0)
            r["pts"] += s["pts"]
            if t["winner_now"] is None:
                r["even"] += 1
            elif t["winner_now"] == s["rid"]:
                r["won"] += 1
            else:
                r["lost"] += 1
    # points: what a manager's acquisitions scored for them minus what their outgoing pieces scored for the other side
    for t in trades:
        if len(t["sides"]) == 2:
            a, b = t["sides"]
            m[a["uid"]]["pts"] -= b["pts"]
            m[b["uid"]]["pts"] -= a["pts"]
    rows = [{"uid": k, **{kk: (sorted(v) if kk == "teams" else (round(v, 1) if kk == "pts" else v)) for kk, v in r.items()},
             "pct_then": round(r["got_then"] / r["gave_then"] * 100) if r["gave_then"] else None} for k, r in m.items()]
    rows.sort(key=lambda r: -r["net_now"])
    return rows


# ------------------------------------------------------------------ how the league prices things
CATEGORIES = [
    ("QB", "Quarterbacks", lambda a: a["kind"] == "player" and a["pos"] == "QB"),
    ("RB", "Running backs", lambda a: a["kind"] == "player" and a["pos"] == "RB"),
    ("WR", "Wide receivers", lambda a: a["kind"] == "player" and a["pos"] == "WR"),
    ("TE", "Tight ends", lambda a: a["kind"] == "player" and a["pos"] == "TE"),
    ("R1", "First-round picks", lambda a: a["kind"] == "pick" and a["round"] == 1),
    ("R2+", "Later-round picks", lambda a: a["kind"] == "pick" and a["round"] >= 2),
    ("young", "Players 24 and under", lambda a: a["kind"] == "player" and a["age"] is not None and a["age"] < 25),
    ("vet", "Players 28 and over", lambda a: a["kind"] == "player" and a["age"] is not None and a["age"] >= 28),
]


def market(trades):
    """What the league pays, relative to the DynastyProcess market at the time, for each kind of asset.

    For every two-team trade side, the return it got (value received / value sent, both at trade time) is credited
    to each asset it sent in proportion to that asset's share of the value sent. Averaging that by category gives
    the return a seller of the category gets: above 100% means this league pays more than market for it."""
    acc = {k: {"value": 0.0, "weighted": 0.0, "trades": set()} for k, _, _ in CATEGORIES}
    cons = {"value": 0.0, "weighted": 0.0, "trades": 0}
    two = [t for t in trades if len(t["sides"]) == 2]
    for t in two:
        a, b = t["sides"]
        for seller, buyer in ((a, b), (b, a)):
            sent, got = buyer["gets"], seller["got_then"]
            total = sum(x["then"] for x in sent)
            if total <= 0 or got <= 0:
                continue
            ratio = got / total
            for k, _, test in CATEGORIES:
                v = sum(x["then"] for x in sent if test(x))
                if v > 0:
                    acc[k]["value"] += v
                    acc[k]["weighted"] += v * ratio
                    acc[k]["trades"].add(t["id"])
        # consolidation: the side that sold the single best asset for more, smaller pieces. What it got back,
        # over market, is what this league pays to consolidate (above 100%: studs fetch a premium)
        best_a = max((x["then"] for x in a["gets"]), default=0)
        best_b = max((x["then"] for x in b["gets"]), default=0)
        star, depth = (a, b) if best_a >= best_b else (b, a)
        if len(depth["gets"]) >= 2 and len(star["gets"]) < len(depth["gets"]) and depth["gave_then"]:
            cons["value"] += depth["gave_then"]
            cons["weighted"] += depth["got_then"]
            cons["trades"] += 1
    rows = []
    for k, label, _ in CATEGORIES:
        r = acc[k]
        pct = round(r["weighted"] / r["value"] * 100) if r["value"] else None
        rows.append({"key": k, "label": label, "trades": len(r["trades"]), "value": round(r["value"]), "pct": pct,
                     "read": _read(pct, len(r["trades"]))})
    cpct = round(cons["weighted"] / cons["value"] * 100) if cons["value"] else None
    return {"rows": rows, "trades": len(two),
            "consolidation": {"trades": cons["trades"], "pct": cpct, "read": _read(cpct, cons["trades"])}}


def _read(pct, n):
    if pct is None or n == 0:
        return "no trades"
    tag = " (thin)" if n < THIN else ""
    if pct >= 100 * (1 + PREMIUM_BAND):
        return "league pays a premium" + tag
    if pct <= 100 * (1 - PREMIUM_BAND):
        return "league pays below market" + tag
    return "about market" + tag
