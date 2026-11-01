"""The target league: settings, rosters, picks, standings, this season's points, and the team lookup."""
import difflib
from collections import defaultdict

from .sleeper import position


def fmt_of(lg):
    """Format fingerprint of a league. The pooled benchmark is built from leagues sharing this family."""
    s = lg.get("settings") or {}
    sc = lg.get("scoring_settings") or {}
    rp = lg.get("roster_positions") or []
    return {
        "teams": lg.get("total_rosters"),
        "dynasty": s.get("type") == 2,
        "keeper": s.get("type") == 1,
        "superflex": "SUPER_FLEX" in rp or rp.count("QB") >= 2,
        "rec": round(float(sc.get("rec") or 0), 2),
        "te_prem": round(float(sc.get("bonus_rec_te") or 0), 2),
        "pass_td": sc.get("pass_td"),
        "flex": rp.count("FLEX"),
        "qb": rp.count("QB"), "rb": rp.count("RB"), "wr": rp.count("WR"), "te": rp.count("TE"),
        "sf": rp.count("SUPER_FLEX"), "def": rp.count("DEF"), "k": rp.count("K"),
        "best_ball": bool(s.get("best_ball")),
        "rounds": s.get("draft_rounds") or 0,
        "playoff_teams": s.get("playoff_teams"),
    }


def fmt_key(f):
    kind = "dynasty" if f["dynasty"] else ("keeper" if f["keeper"] else "redraft")
    rec = {1.0: "ppr", 0.5: "halfppr", 0.0: "std"}.get(f["rec"], f"{f['rec']}rec")
    return f"{kind}-{f['teams']}team-{'sf' if f['superflex'] else '1qb'}-{rec}" + ("-tep" if f["te_prem"] else "")


def same_family(a, b):
    """Loose match: same size, same dynasty/keeper type, same QB structure, same reception scoring, TE premium or not."""
    return (a["teams"] == b["teams"] and a["dynasty"] == b["dynasty"] and a["keeper"] == b["keeper"]
            and a["superflex"] == b["superflex"] and abs(a["rec"] - b["rec"]) < 0.01
            and bool(a["te_prem"]) == bool(b["te_prem"]) and not b["best_ball"])


def strict_match(a, b):
    return same_family(a, b) and a["pass_td"] == b["pass_td"] and a["flex"] == b["flex"] and (a["qb"], a["rb"], a["wr"], a["te"]) == (b["qb"], b["rb"], b["wr"], b["te"])


class League:
    def __init__(self, api, league_id, log=print):
        self.api = api
        self.id = str(league_id)
        self.lg = api.league(self.id)
        if not self.lg:
            raise SystemExit(f"League {league_id} not found on Sleeper.")
        self.pdb = api.players()
        self.rosters = api.rosters(self.id)
        self.users = api.users(self.id)
        self.traded = api.traded_picks(self.id)
        self.fmt = fmt_of(self.lg)
        self.n = self.lg.get("total_rosters") or len(self.rosters)
        self.season = int(self.lg["season"])
        self.rp = self.lg.get("roster_positions") or []
        self.settings = self.lg.get("settings") or {}
        self.rounds = int(self.settings.get("draft_rounds") or 4)
        self.playoff_teams = int(self.settings.get("playoff_teams") or 6)
        self.trade_deadline = self.settings.get("trade_deadline")
        self.status = self.lg.get("status")
        state = api.state()
        self.state_week = int(state.get("week") or 1) if str(state.get("season")) == str(self.season) else None
        pws = int(self.settings.get("playoff_week_start") or 15)
        self.reg_weeks = pws - 1
        if self.status == "complete":
            self.week = self.reg_weeks
        elif self.status == "in_season" and self.state_week:
            self.week = min(self.state_week, self.reg_weeks)
        else:
            self.week = 0
        # the current season's rookie draft is still ahead only before the season starts
        self.draft_pending = self.status in ("pre_draft", "drafting")

        self.user_name = {u["user_id"]: (u.get("display_name") or u.get("username") or f"User {u['user_id']}") for u in self.users}
        self.user_handle = {u["user_id"]: (u.get("username") or "") for u in self.users}
        # Sleeper keeps the custom team name on the USER record (users[].metadata.team_name), not the roster
        self.user_team = {u["user_id"]: ((u.get("metadata") or {}).get("team_name") or "").strip() for u in self.users}
        self.team_name = {}
        self.owner_name = {}
        for r in self.rosters:
            rid = r["roster_id"]
            meta = (r.get("metadata") or {}).get("team_name") or self.user_team.get(r.get("owner_id"))
            owner = self.user_name.get(r.get("owner_id"))
            self.team_name[rid] = meta or owner or f"Team {rid}"
            self.owner_name[rid] = owner or "(orphan)"
        self.rid_by_name = {v: k for k, v in self.team_name.items()}

        # standings: best first; projected draft slot: worst first, ties by points for
        def rec(r):
            s = r.get("settings") or {}
            return (s.get("wins", 0) + 0.5 * s.get("ties", 0), s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100)
        self.standings = [r["roster_id"] for r in sorted(self.rosters, key=rec, reverse=True)]
        self.rank = {rid: i + 1 for i, rid in enumerate(self.standings)}
        self.proj_slot = {rid: self.n - self.rank[rid] + 1 for rid in self.rank}
        self.record = {r["roster_id"]: ((r.get("settings") or {}).get("wins", 0), (r.get("settings") or {}).get("losses", 0),
                                        (r.get("settings") or {}).get("fpts", 0)) for r in self.rosters}

        # picks: every (season, round, original roster) with its current holder
        holder = {(str(p["season"]), int(p["round"]), int(p["roster_id"])): int(p["owner_id"]) for p in self.traded}
        first = self.season if self.draft_pending else self.season + 1
        self.redraft = not (self.fmt["dynasty"] or self.fmt["keeper"])
        self.pick_seasons = [] if self.redraft else [str(y) for y in range(first, first + 3)]
        self.picks = defaultdict(list)
        for season in self.pick_seasons:
            for rnd in range(1, self.rounds + 1):
                for orig in self.team_name:
                    own = holder.get((season, rnd, orig), orig)
                    self.picks[own].append({"season": season, "round": rnd, "orig_rid": orig, "orig": self.team_name[orig], "own": own == orig})

        # this season's points per player from weekly matchups
        self.matchups = {}
        self.pts, self.gp = defaultdict(float), defaultdict(int)
        for wk in range(1, self.week + 1):
            ms = api.matchups(self.id, wk)
            if not ms or sum(sum((m.get("players_points") or {}).values()) for m in ms) == 0:
                continue
            self.matchups[wk] = ms
            for m in ms:
                for pid, p in (m.get("players_points") or {}).items():
                    if p and p > 0:
                        self.pts[pid] += p
                        self.gp[pid] += 1
        self.trades = []
        for wk in range(1, 19):
            for t in api.transactions(self.id, wk):
                if t.get("type") == "trade" and t.get("status") == "complete":
                    self.trades.append(t)
        self.bracket = api.winners_bracket(self.id)
        log(f"league: {self.lg.get('name')} | {fmt_key(self.fmt)} | season {self.season} {self.status} | week {self.week} | {api.calls} calls")

    # ------------------------------------------------------------------ helpers
    def ppg(self, pid):
        g = self.gp.get(pid, 0)
        return (round(self.pts[pid] / g, 1) if g else 0.0), g

    def pos(self, pid):
        return position(self.pdb, pid)

    def player(self, pid):
        p = dict(self.pdb.get(pid) or {})
        p["player_id"] = pid
        if not p.get("full_name"):
            p["full_name"] = p.get("last_name") or pid
        if not p.get("position"):
            p["position"] = self.pos(pid)
        return p

    def roster(self, rid):
        return next(r for r in self.rosters if r["roster_id"] == rid)

    def find_team(self, query):
        """Resolve a team name, display name, username, or roster id to a roster id."""
        def fold(x):
            # case-fold and normalise curly quotes so "We’re So Back" matches "we're so back"
            return (x or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"').strip().lower()
        q = (query or "").strip()
        if q.isdigit() and int(q) in self.team_name and len(q) <= 2:
            return int(q)
        names = {}
        for rid in self.team_name:
            r = self.roster(rid)
            for cand in (self.team_name[rid], self.owner_name[rid], self.user_handle.get(r.get("owner_id"), "")):
                if cand:
                    names.setdefault(fold(cand), rid)
        ql = fold(q)
        if ql in names:
            return names[ql]
        subs = {n: rid for n, rid in names.items() if ql and ql in n}
        if len(set(subs.values())) == 1:
            return next(iter(subs.values()))
        close = difflib.get_close_matches(ql, list(names), n=1, cutoff=0.6)
        if close:
            return names[close[0]]
        opts = "\n".join(f"  {rid:2d}  {self.team_name[rid]}  ({self.owner_name[rid]})" for rid in self.standings)
        raise SystemExit(f"No team matches '{query}'. Teams in this league:\n{opts}")

    def bundle(self):
        """This league-season in the same shape the crawler stores, so metrics treat it like any pooled season."""
        drafts = self.api.drafts(self.id)
        return {"league": self.lg, "users": self.users, "rosters": self.rosters, "matchups": {str(k): v for k, v in self.matchups.items()},
                "winners_bracket": self.bracket, "drafts": drafts, "picks": {d["draft_id"]: self.api.draft_picks(d["draft_id"]) for d in drafts},
                "traded_picks": self.traded, "trades": self.trades, "through_week": self.week}
