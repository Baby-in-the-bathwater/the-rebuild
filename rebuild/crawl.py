"""Crawlers: pooled-league discovery (snowball through managers) and league-history walks (previous_league_id).

Every league-season lands as one JSON bundle in <cache>/leagues/<league_id>.json. Completed seasons never
change, so the cache is permanent for them; in-season bundles are refreshed when the NFL week advances."""
import json
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from .league import fmt_of, same_family, strict_match


def classify(target_fmt, lg):
    if not lg or lg.get("sport") != "nfl":
        return None
    if lg.get("status") not in ("in_season", "complete"):
        return None
    f = fmt_of(lg)
    if not same_family(target_fmt, f):
        return None
    return "strict" if strict_match(target_fmt, f) else "loose"


def bundle_path(cache_dir, lid):
    return os.path.join(cache_dir, "leagues", f"{lid}.json")


def load_bundle(cache_dir, lid):
    p = bundle_path(cache_dir, lid)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fetch_season(api, cache_dir, lid, lg=None, state_week=None, state_season=None):
    """Pull one league-season (settings, users, rosters, weekly matchups, bracket, drafts, traded picks, trades)."""
    os.makedirs(os.path.join(cache_dir, "leagues"), exist_ok=True)
    existing = load_bundle(cache_dir, lid)
    if existing:
        lg_e = existing["league"]
        if lg_e.get("status") == "complete":
            return existing
        # in-season bundle: reuse unless the week moved on
        if state_week and str(lg_e.get("season")) == str(state_season) and existing.get("through_week", 0) >= min(state_week, 18) - 1:
            return existing
    lg = lg or api.league(lid)
    if not lg:
        return None
    pws = int((lg.get("settings") or {}).get("playoff_week_start") or 15)
    if lg.get("status") == "complete":
        last_wk = pws - 1
    elif state_week and str(lg.get("season")) == str(state_season):
        last_wk = min(state_week, pws - 1)
    else:
        last_wk = 0
    matchups = {}
    for wk in range(1, last_wk + 1):
        m = api.matchups(lid, wk)
        if m and sum(sum((x.get("players_points") or {}).values()) for x in m) > 0:
            matchups[str(wk)] = m
    trades = []
    for wk in range(1, 19):
        trades.extend([t for t in api.transactions(lid, wk) if t.get("type") == "trade" and t.get("status") == "complete"])
    drafts = api.drafts(lid)
    b = {
        "league": lg,
        "users": api.users(lid),
        "rosters": api.rosters(lid),
        "matchups": matchups,
        "winners_bracket": api.winners_bracket(lid),
        "drafts": drafts,
        "picks": {d["draft_id"]: api.draft_picks(d["draft_id"]) for d in drafts},
        "traded_picks": api.traded_picks(lid),
        "trades": trades,
        "through_week": last_wk,
        "fetched": time.strftime("%Y-%m-%d"),
    }
    with open(bundle_path(cache_dir, lid), "w", encoding="utf-8") as f:
        json.dump(b, f)
    return b


def walk_lineage(api, cache_dir, root, state_week=None, state_season=None, max_seasons=12):
    """Follow previous_league_id back one season per hop. Returns the chain of league ids, newest first."""
    chain = []
    lid = str(root)
    while lid and lid != "0" and len(chain) < max_seasons:
        b = fetch_season(api, cache_dir, lid, state_week=state_week, state_season=state_season)
        if not b:
            break
        chain.append(lid)
        lid = b["league"].get("previous_league_id")
    return chain


def discover_pool(api, league, target=150, seconds=600, threads=12, log=print):
    """Snowball from the target league's managers through their other leagues, keeping those in the same format family
    and the same season. Managers of matching leagues are expanded first, so the pool fills with the right format fast."""
    season = str(league.season)
    fmt = league.fmt
    seen_users, seen_leagues = set(), set()
    matched = {}
    hi, lo = deque(), deque()
    for u in league.users:
        hi.append(u["user_id"])
    t0 = time.time()
    pool = ThreadPoolExecutor(threads)

    def pop_batch(n):
        out = []
        while len(out) < n and (hi or lo):
            uid = hi.popleft() if hi else lo.popleft()
            if uid not in seen_users:
                seen_users.add(uid)
                out.append(uid)
        return out

    def fam(lg):
        return lg.get("status") in ("in_season", "complete", "pre_draft", "drafting") and same_family(fmt, fmt_of(lg))

    tick = 0
    while (hi or lo) and len(matched) < target and time.time() - t0 < seconds:
        batch = pop_batch(threads * 3)
        if not batch:
            break
        new_leagues = []
        for uid, leagues in zip(batch, pool.map(lambda u: api.user_leagues(u, season), batch)):
            for lg in leagues or []:
                lid = lg["league_id"]
                if lid in seen_leagues:
                    continue
                seen_leagues.add(lid)
                cls = classify(fmt, lg)
                if cls and lid != league.id:
                    matched[lid] = cls
                new_leagues.append((lid, fam(lg)))
        expand = [(lid, p) for lid, p in new_leagues if p or len(hi) < 200]
        for (lid, p), us in zip(expand, pool.map(lambda x: api.users(x[0]), expand)):
            for u in us or []:
                if u["user_id"] not in seen_users:
                    (hi if p else lo).append(u["user_id"])
        tick += 1
        if tick % 5 == 0:
            log(f"  discovery: users {len(seen_users)} | leagues seen {len(seen_leagues)} | matched {len(matched)} "
                f"({sum(1 for v in matched.values() if v == 'strict')} strict) | {api.calls} calls | {time.time() - t0:.0f}s")
    pool.shutdown(wait=True)
    log(f"  discovery done: {len(matched)} leagues in {time.time() - t0:.0f}s")
    return matched


def crawl_lineages(api, cache_dir, roots, threads=12, state_week=None, state_season=None, log=print):
    """Walk every root league's history in parallel. Returns {root: [season ids newest first]}."""
    t0 = time.time()
    lineages = {}
    done = 0
    with ThreadPoolExecutor(threads) as pool:
        for root, chain in zip(roots, pool.map(lambda r: walk_lineage(api, cache_dir, r, state_week, state_season), roots)):
            lineages[root] = chain
            done += 1
            if done % 20 == 0:
                log(f"  history: {done}/{len(roots)} lineages | {sum(len(c) for c in lineages.values())} seasons | {api.calls} calls | {time.time() - t0:.0f}s")
    log(f"  history done: {len(lineages)} lineages, {sum(len(c) for c in lineages.values())} league-seasons in {time.time() - t0:.0f}s")
    return lineages


def load_bundles(cache_dir, ids):
    out = {}
    for lid in ids:
        b = load_bundle(cache_dir, lid)
        if b:
            out[lid] = b
    return out
