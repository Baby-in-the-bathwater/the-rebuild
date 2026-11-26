"""A made-up 12-team Superflex half-PPR dynasty league for tests, in the engine's inputs shape, plus a fake Sleeper client.

Nothing here comes from a real league: ids are short strings ("L1", "U3", "D1", "1001"), managers are "Manager N",
teams "Team N", players "Player <code>". `make_inputs` is deterministic: every call returns the same data."""
import csv
import datetime as dt
import io
import json
import os
import random

SEASON = 2026
N = 12
REG_WEEKS = 14
ROSTER_POSITIONS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "FLEX", "FLEX", "SUPER_FLEX", "DEF"] + ["BN"] * 8
STARTER_SLOTS = 12
NFL_TEAMS = ["ALP", "BRV", "CRD", "DLT", "EGL", "FLC", "GNT", "HWK"]
BENCHMARK = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "benchmarks", "dynasty-12team-sf-halfppr.json")
CSV_HEADER = ["player", "pos", "team", "age", "draft_year", "ecr_1qb", "ecr_2qb", "ecr_pos", "value_1qb", "value_2qb", "scrape_date", "fp_id"]

# per position: players in the pool, best and worst weekly points, oldest age, and how many of each rookie class
POOL = {"QB": (36, 25.0, 8.0, 34, 4), "RB": (72, 18.0, 3.0, 30, 12), "WR": (84, 17.0, 3.0, 32, 14), "TE": (36, 13.0, 3.0, 33, 6)}
CONSONANTS, VOWELS = "bcdfghjklmnpqrstvwxz", "aeiou"


def _ms(when):
    return int(when.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _code(i):
    """Three letters, consonant-vowel-consonant: distinct per player and never a suffix word the value matcher strips."""
    return (CONSONANTS[i % 20] + VOWELS[(i // 20) % 5] + CONSONANTS[(i // 100) % 20]).title()


# ------------------------------------------------------------------ the players
def _players(rng):
    """Every skill player in the league's world: {pid: {...}} with a hidden `base` (points a week) and `cls` (rookie class year)."""
    pool = []
    for pos, (n, hi, lo, oldest, per_class) in POOL.items():
        picked = rng.sample(range(n), per_class * 2)
        for i in range(n):
            base = (hi - (hi - lo) * (i / (n - 1)) ** 0.9) * rng.uniform(0.95, 1.05)
            cls = "2026" if i in picked[:per_class] else ("2025" if i in picked[per_class:] else None)
            age = {"2026": rng.choice([21, 22]), "2025": rng.choice([22, 23])}.get(cls) or rng.randint(23, oldest)
            yexp = {"2026": 0, "2025": 1}.get(cls, max(2, age - 22))
            pool.append({"pos": pos, "base": round(base, 1), "cls": cls, "age": age, "years_exp": yexp, "frac": rng.random()})
    rng.shuffle(pool)
    out = {}
    for i, p in enumerate(pool):
        pid = str(1001 + i)
        birth = dt.date(SEASON, 9, 1) - dt.timedelta(days=int((p["age"] + p["frac"]) * 365.25))
        out[pid] = {**p, "player_id": pid, "first_name": "Player", "last_name": _code(i), "full_name": f"Player {_code(i)}",
                    "fantasy_positions": [p["pos"]], "position": p["pos"], "birth_date": birth.isoformat(), "team": NFL_TEAMS[i % len(NFL_TEAMS)],
                    "status": "Active", "active": True, "sport": "nfl", "injury_status": None, "injury_body_part": None, "injury_notes": None}
    return out


def _defenses():
    return {chr(65 + k) * 3: {"player_id": chr(65 + k) * 3, "position": "DEF", "fantasy_positions": ["DEF"], "full_name": f"{chr(65 + k) * 3} Defense",
                              "first_name": chr(65 + k) * 3, "last_name": "Defense", "team": chr(65 + k) * 3, "sport": "nfl", "active": True}
            for k in range(N)}


def _public(p):
    return {k: v for k, v in p.items() if k not in ("base", "cls", "frac", "pos")}


# ------------------------------------------------------------------ rosters, drafts, trades
def _build(rng, players):
    """Initial rosters ({rid: [pids]}), both rookie drafts, the draft slot order and each team's strength rank (0 = best)."""
    rids = list(range(1, N + 1))
    strength = {rid: i for i, rid in enumerate(rng.sample(rids, N))}
    slot_to_rid = dict(enumerate(rng.sample(rids, N), 1))
    comp = {rid: [] for rid in rids}
    drafts = {}
    for cls in ("2025", "2026"):
        klass = sorted((p for p in players.values() if p["cls"] == cls), key=lambda p: -p["base"])
        drafts[cls] = [{"round": i // N + 1, "draft_slot": i % N + 1, "pick_no": i + 1, "player_id": p["player_id"], "roster_id": slot_to_rid[i % N + 1]}
                       for i, p in enumerate(klass)]
    for cls, picks in drafts.items():
        for pk in picks:
            comp[pk["roster_id"]].append(pk["player_id"])
    for pos in POOL:
        vets = sorted((p for p in players.values() if p["pos"] == pos and p["cls"] is None), key=lambda p: -p["base"])
        have = {rid: sum(1 for pid in comp[rid] if players[pid]["pos"] == pos) for rid in rids}
        for p in vets:
            rid = min(rids, key=lambda r: (have[r], strength[r] if have[r] % 2 == 0 else -strength[r]))
            comp[rid].append(p["player_id"])
            have[rid] += 1
    for rid, d in zip(rng.sample(rids, N), _defenses()):
        comp[rid].append(d)
    return comp, drafts, slot_to_rid, strength


def _lineup(comp_pids, players, out):
    """The best twelve starters by base points: QB, 2 RB, 3 WR, TE, 3 FLEX, SUPER_FLEX, DEF. `out` are players who cannot play."""
    left = sorted((players[p] for p in comp_pids if p in players and p not in out), key=lambda p: -p["base"])
    by = {pos: [p for p in left if p["pos"] == pos] for pos in POOL}
    take = lambda pos, n: [by[pos].pop(0)["player_id"] for _ in range(min(n, len(by[pos])))]  # noqa: E731
    starters = take("QB", 1) + take("RB", 2) + take("WR", 3) + take("TE", 1)
    flex = sorted((p for pos in ("RB", "WR", "TE") for p in by[pos]), key=lambda p: -p["base"])[:3]
    for p in flex:
        by[p["pos"]].remove(p)
    sf = sorted((p for pos in POOL for p in by[pos]), key=lambda p: -p["base"] * (1.3 if p["pos"] == "QB" else 1))[:1]
    sf_id = sf[0]["player_id"] if sf else "0"
    d = next((p for p in comp_pids if p.isalpha()), "0")
    return starters + [p["player_id"] for p in flex] + [sf_id, d]


def _swap(comp, trade):
    comp = {rid: list(pids) for rid, pids in comp.items()}
    for pid, rid in trade["adds"].items():
        comp[trade["drops"][pid]].remove(pid)
        comp[rid].append(pid)
    return comp


def _trades(comp, players, strength, week):
    """Two completed trades: a player-for-player swap with a pick on top, and a player for a future first. Plus the traded-picks rows."""
    leg1, leg2 = max(1, min(2, week)), max(1, min(3, week))
    base = dt.datetime(2026, 9, 10, 15) if week else dt.datetime(2026, 6, 12, 15)
    tops = lambda rid, pos: sorted((p for p in comp[rid] if p in players and players[p]["pos"] == pos and players[p]["cls"] is None),  # noqa: E731
                                   key=lambda p: -players[p]["base"])
    a, b, c, d = tops(2, "WR")[1], tops(5, "RB")[1], tops(7, "WR")[2], tops(3, "RB")[3]
    pick1 = {"season": "2027", "round": 2, "roster_id": 2, "previous_owner_id": 2, "owner_id": 5}
    pick2 = {"season": "2028", "round": 1, "roster_id": 3, "previous_owner_id": 3, "owner_id": 7}
    t1 = {"type": "trade", "status": "complete", "transaction_id": "T1", "leg": leg1, "roster_ids": [2, 5], "creator": "U2",
          "created": _ms(base + dt.timedelta(days=7 * (leg1 - 1) + 2)), "status_updated": _ms(base + dt.timedelta(days=7 * (leg1 - 1) + 3)),
          "adds": {a: 5, b: 2}, "drops": {a: 2, b: 5}, "draft_picks": [pick1], "waiver_budget": []}
    t2 = {"type": "trade", "status": "complete", "transaction_id": "T2", "leg": leg2, "roster_ids": [3, 7], "creator": "U3",
          "created": _ms(base + dt.timedelta(days=7 * (leg2 - 1) + 4)), "status_updated": _ms(base + dt.timedelta(days=7 * (leg2 - 1) + 5)),
          "adds": {c: 3, d: 7}, "drops": {c: 7, d: 3}, "draft_picks": [pick2], "waiver_budget": []}
    return [t1, t2], [pick1, pick2]


# ------------------------------------------------------------------ games
def _schedule(wk):
    """Round-robin pairings for the week (circle method): [(rid, rid)] over 12 rosters."""
    ring = list(range(2, N + 1))
    k = (wk - 1) % (N - 1)
    ring = ring[-k:] + ring[:-k] if k else ring
    row = [1] + ring
    return [(row[i], row[N - 1 - i]) for i in range(N // 2)]


def _play(season_rng, weeks, comp_at, players, out_at):
    """Matchups {"1": [...]} for each week and the roster `settings` that result."""
    matchups = {}
    rec = {rid: {"wins": 0, "losses": 0, "ties": 0, "pf": 0.0, "pa": 0.0} for rid in range(1, N + 1)}
    for wk in range(1, weeks + 1):
        comp = comp_at(wk)
        scored = {}
        for rid, pids in comp.items():
            out = out_at(wk)
            pp = {p: (0.0 if p in out else round((players[p]["base"] if p in players else 6.0) * season_rng.uniform(0.5, 1.5), 1)) for p in pids}
            starters = _lineup(pids, players, out)
            scored[rid] = {"roster_id": rid, "points": round(sum(pp[s] for s in starters if s in pp), 2), "starters": starters,
                           "starters_points": [pp.get(s, 0.0) for s in starters], "players": sorted(pids), "players_points": pp, "custom_points": None}
        for mid, (x, y) in enumerate(_schedule(wk), 1):
            scored[x]["matchup_id"], scored[y]["matchup_id"] = mid, mid
            for u, v in ((x, y), (y, x)):
                rec[u]["pf"] += scored[u]["points"]
                rec[u]["pa"] += scored[v]["points"]
                key = "wins" if scored[u]["points"] > scored[v]["points"] else ("losses" if scored[u]["points"] < scored[v]["points"] else "ties")
                rec[u][key] += 1
        matchups[str(wk)] = [scored[rid] for rid in sorted(scored)]
    settings = {rid: {"wins": r["wins"], "losses": r["losses"], "ties": r["ties"], "fpts": int(r["pf"]), "fpts_decimal": int(round(r["pf"] % 1 * 100)),
                      "fpts_against": int(r["pa"]), "fpts_against_decimal": int(round(r["pa"] % 1 * 100)), "total_moves": 0} for rid, r in rec.items()}
    return matchups, settings


# ------------------------------------------------------------------ values
def _values_csv(players, rng, scrape_date, scale=1.0):
    rows = []
    for p in sorted(players.values(), key=lambda p: p["player_id"]):
        agefac = 1.15 if p["age"] <= 24 else (1.0 if p["age"] <= 27 else (0.8 if p["age"] <= 29 else 0.55))
        v = min(9999, int(p["base"] ** 2 * 12 * agefac * scale * rng.uniform(0.9, 1.1)))
        v1 = int(v * 0.55) if p["pos"] == "QB" else v
        rows.append([p["full_name"], p["pos"], p["team"], p["age"], SEASON - p["years_exp"], "", "", "", v1, v, scrape_date, p["player_id"]])
    ordinals = {1: "1st", 2: "2nd", 3: "3rd"}
    worth = {1: 5200, 2: 1500, 3: 500}
    for rnd, name in ordinals.items():
        for slot in range(1, N + 1):
            v = int(worth[rnd] * scale * (1.45 - 0.9 * (slot - 1) / (N - 1)))
            rows.append([f"{SEASON} Pick {rnd}.{slot:02d}", "PICK", "", "", "", "", "", "", v, v, scrape_date, ""])
        for year in range(SEASON, SEASON + 4):
            far = 0.85 ** max(0, year - SEASON)
            for tier, mult in (("Early", 1.3), ("Mid", 1.0), ("Late", 0.75)):
                v = int(worth[rnd] * scale * mult * far)
                rows.append([f"{year} {tier} {name}", "PICK", "", "", "", "", "", "", v, v, scrape_date, ""])
            v = int(worth[rnd] * scale * far)
            rows.append([f"{year} {name}", "PICK", "", "", "", "", "", "", v, v, scrape_date, ""])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_HEADER)
    w.writerows(rows)
    return buf.getvalue()


# ------------------------------------------------------------------ the inputs
def _draft(league_id, draft_id, season, status, start, slot_to_rid, picks):
    users = {f"U{rid}": slot for slot, rid in slot_to_rid.items()}
    return {"draft_id": draft_id, "league_id": league_id, "season": str(season), "status": status, "type": "linear", "start_time": start,
            "draft_order": users, "slot_to_roster_id": {str(s): r for s, r in slot_to_rid.items()}, "settings": {"rounds": 3, "teams": N}}, \
        [{**pk, "draft_id": draft_id, "picked_by": f"U{pk['roster_id']}"} for pk in picks]


def make_inputs(*, week=6, history=True, trades=True):
    """A full inputs dict. `week` is the NFL week the league is in (0 = before the rookie draft); `history` adds one completed
    previous season; `trades` adds two completed trades and a value snapshot dated before them."""
    rng = random.Random(2026)
    skill = _players(rng)
    players = {**skill}
    comp0, drafts, slot_to_rid, strength = _build(rng, players)
    pre_draft = week == 0
    if pre_draft:   # this year's rookies are still waiting for the draft
        rookies = {pk["player_id"] for pk in drafts["2026"]}
        comp0 = {rid: [p for p in pids if p not in rookies] for rid, pids in comp0.items()}
    moves, traded = _trades(comp0, players, strength, week)
    comp_end = comp0
    for t in moves:
        comp_end = _swap(comp_end, t)
    injured = {}
    if week >= 4:   # one star on injured reserve for three teams, from week 4 on
        for rid in (3, 6, 9):
            pid = next(p for p in sorted(comp_end[rid], key=lambda p: -players[p]["base"] if p in players else 0)
                       if p in players and players[p]["pos"] != "QB" and players[p]["cls"] is None and players[p]["age"] >= 25)
            injured[pid] = rid
            players[pid] = {**players[pid], "injury_status": "IR", "injury_body_part": "Knee", "injury_notes": "Out for the season"}
    questionable = [p for p in sorted(players) if players[p]["pos"] == "WR" and p not in injured][:2] if week else []
    for pid in questionable:
        players[pid] = {**players[pid], "injury_status": "Questionable"}

    def comp_for(wk, trade_list):
        comp = comp0
        for t in trade_list:
            if t["leg"] < wk:
                comp = _swap(comp, t)
        return comp

    # the current season
    users = [{"user_id": f"U{rid}", "username": f"manager{rid}", "display_name": f"Manager {rid}", "avatar": None,
              "metadata": {"team_name": f"Team {rid}"}} for rid in range(1, N + 1)]
    status = "pre_draft" if pre_draft else "in_season"
    matchups, settings = _play(random.Random(11), week, lambda wk: comp_for(wk, moves if trades else []), skill,
                               lambda wk: set(injured) if wk >= 4 else set())
    this_trades = moves if trades else []
    final = comp_end if trades else comp0
    rosters = [{"roster_id": rid, "owner_id": f"U{rid}", "league_id": "L1", "players": sorted(final[rid]),
                "starters": _lineup(final[rid], players, set(injured)), "reserve": sorted(p for p in injured if injured[p] == rid), "taxi": [],
                "settings": settings[rid], "metadata": {}} for rid in range(1, N + 1)]
    league = {"league_id": "L1", "name": "Synthetic Dynasty League", "sport": "nfl", "season": str(SEASON), "status": status,
              "previous_league_id": "L0" if history else "0", "draft_id": "D1", "total_rosters": N, "roster_positions": ROSTER_POSITIONS,
              "scoring_settings": {"rec": 0.5, "pass_td": 4.0, "pass_yd": 0.04, "rush_yd": 0.1, "rec_yd": 0.1, "rush_td": 6.0, "rec_td": 6.0},
              "settings": {"type": 2, "best_ball": 0, "draft_rounds": 3, "playoff_teams": 4, "playoff_week_start": REG_WEEKS + 1, "trade_deadline": 11,
                           "num_teams": N, "leg": week}}
    d1, d1_picks = _draft("L1", "D1", SEASON, "pre_draft" if pre_draft else "complete", None if pre_draft else _ms(dt.datetime(2026, 5, 10, 18)),
                          slot_to_rid, [] if pre_draft else drafts["2026"])
    transactions = {str(wk): [] for wk in range(1, 19)}
    if week >= 2:
        transactions["2"].append({"type": "free_agent", "status": "complete", "transaction_id": "T0", "leg": 2, "roster_ids": [1], "adds": {}, "drops": {},
                                  "draft_picks": [], "waiver_budget": []})
    for t in this_trades:
        transactions[str(t["leg"])].append(t)
    pull = {"league": league, "rosters": rosters, "users": users, "traded_picks": traded if trades else [], "matchups": matchups,
            "transactions": transactions, "winners_bracket": [], "drafts": [d1], "picks": {"D1": d1_picks}}

    # the previous season, complete: the same managers, last year's draft, 14 weeks and a four-team bracket
    chain, hist = ["L1"], {}
    if history:
        old = {pid: p for pid, p in skill.items() if p["cls"] != "2026"}
        prev_comp = {rid: [p for p in pids if p in old or p.isalpha()] for rid, pids in comp0.items()}
        m0, s0 = _play(random.Random(5), REG_WEEKS, lambda wk: prev_comp, skill, lambda wk: set())
        order = sorted(s0, key=lambda r: (-s0[r]["wins"], -s0[r]["fpts"]))
        top = order[:4]
        bracket = [{"r": 1, "m": 1, "t1": top[0], "t2": top[3], "w": top[0], "l": top[3]},
                   {"r": 1, "m": 2, "t1": top[1], "t2": top[2], "w": top[1], "l": top[2]},
                   {"r": 2, "m": 3, "t1": {"w": 1}, "t2": {"w": 2}, "w": top[0], "l": top[1], "p": 1},
                   {"r": 2, "m": 4, "t1": {"l": 1}, "t2": {"l": 2}, "w": top[3], "l": top[2], "p": 3}]
        d0, d0_picks = _draft("L0", "D0", SEASON - 1, "complete", _ms(dt.datetime(2025, 5, 10, 18)), slot_to_rid, drafts["2025"])
        prev_league = {**league, "league_id": "L0", "season": str(SEASON - 1), "status": "complete", "previous_league_id": "0", "draft_id": "D0",
                       "name": "Synthetic Dynasty League"}
        prev_rosters = [{"roster_id": rid, "owner_id": f"U{rid}", "league_id": "L0", "players": sorted(prev_comp[rid]), "starters": [], "reserve": [],
                         "taxi": [], "settings": s0[rid], "metadata": {}} for rid in range(1, N + 1)]
        chain.append("L0")
        hist["L0"] = {"league": prev_league, "users": users, "rosters": prev_rosters, "matchups": m0, "winners_bracket": bracket, "drafts": [d0],
                     "picks": {"D0": d0_picks}, "traded_picks": [], "trades": [], "through_week": REG_WEEKS, "fetched": "2026-11-16"}

    # the values feed now, and one snapshot from before the trades
    index, snaps = [], {}
    if trades:
        first = min(t["created"] for t in moves)
        snap_day = dt.datetime.fromtimestamp(first / 1000, tz=dt.timezone.utc) - dt.timedelta(days=3)
        index = [[snap_day.strftime("%Y-%m-%dT%H:%M:%SZ"), "5a1c0de"]]
        snaps = {"5a1c0de": _values_csv(skill, random.Random(3), snap_day.strftime("%Y-%m-%d"), scale=0.9)}
    with open(BENCHMARK, encoding="utf-8") as f:
        benchmark = json.load(f)
    return {"version": 1, "run_at": "2026-11-16T12:00:00Z", "options": {"history": history, "trade_history": trades},
            "state": {"season": str(SEASON), "week": week, "season_type": "pre" if pre_draft else "regular", "display_week": week},
            "players": {**{pid: _public(p) for pid, p in players.items()}, **_defenses()}, "pull": pull, "chain": chain, "history": hist,
            "values_csv": _values_csv(skill, random.Random(4), "2026-11-16"), "snapshot_index": index, "snapshots": snaps, "benchmark": benchmark,
            "benchmark_note": f" (shipped benchmark built {benchmark['built']}; run with --pool to crawl a fresh one)"}


# ------------------------------------------------------------------ the fake API
class FakeSleeper:
    """Answers the `rebuild.sleeper.Sleeper` methods from an inputs dict, counting each call like the real client counts requests."""

    def __init__(self, inputs):
        self.inputs = inputs
        self.calls = 0
        pull = inputs["pull"]
        self._seasons = {pull["league"]["league_id"]: pull}
        self._seasons.update(inputs["history"])
        self._picks = {did: picks for s in self._seasons.values() for did, picks in (s.get("picks") or {}).items()}

    def _season(self, lid):
        self.calls += 1
        return self._seasons.get(str(lid))

    def league(self, lid):
        s = self._season(lid)
        return s["league"] if s else None

    def rosters(self, lid):
        return (self._season(lid) or {}).get("rosters") or []

    def users(self, lid):
        return (self._season(lid) or {}).get("users") or []

    def traded_picks(self, lid):
        return (self._season(lid) or {}).get("traded_picks") or []

    def matchups(self, lid, week):
        return ((self._season(lid) or {}).get("matchups") or {}).get(str(week)) or []

    def transactions(self, lid, week):
        s = self._season(lid) or {}
        if "transactions" in s:
            return s["transactions"].get(str(week)) or []
        return [t for t in s.get("trades") or [] if t.get("leg") == week]

    def winners_bracket(self, lid):
        return (self._season(lid) or {}).get("winners_bracket") or []

    def drafts(self, lid):
        return (self._season(lid) or {}).get("drafts") or []

    def draft_picks(self, draft_id):
        self.calls += 1
        return self._picks.get(draft_id) or []

    def players(self):
        self.calls += 1
        return self.inputs["players"]

    def state(self):
        self.calls += 1
        return self.inputs["state"]

    def user_leagues(self, uid, season):
        self.calls += 1
        return []

    def user(self, name_or_id):
        self.calls += 1
        return next((u for u in self.inputs["pull"]["users"] if name_or_id in (u["user_id"], u["username"])), None)
