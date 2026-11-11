"""the-rebuild: league id + team name in, graded brief and interactive trade board out.

    python -m rebuild --league 123456789 --team "My Team"

Steps: pull the league, price every asset, walk the league's own history, load (or crawl) the format benchmark,
grade the roster, make the call, draft the deals, write brief.md + trade-board.html + data JSON."""
import argparse
import json
import os
import sys
import time
import webbrowser

from . import benchmarks as bmod
from . import pdf as pdfmod
from . import board, report
from . import trade_history as thmod
from .crawl import crawl_lineages, discover_pool, load_bundles, walk_lineage
from .grade import grade, team_types
from .league import League, fmt_key
from .sleeper import Sleeper
from .trades import classify_assets, deals, three_team_deals
from .values import Values

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rebuild", description="Grade a Sleeper dynasty roster against what wins its format and draft the trades.")
    ap.add_argument("--league", required=True, help="Sleeper league id (the number in the league URL)")
    ap.add_argument("--team", required=True, help="team name, manager display name, username, or roster id")
    ap.add_argument("--out", default=None, help="output folder (default out/<league id>)")
    ap.add_argument("--cache-dir", default=os.path.join(HERE, "cache"), help="where Sleeper pulls and crawled seasons are cached")
    ap.add_argument("--benchmarks", default=None, help="path to a benchmark JSON to use instead of the shipped/crawled one")
    ap.add_argument("--pool", action="store_true", help="crawl a fresh benchmark pool for this format even if a shipped one matches")
    ap.add_argument("--pool-target", type=int, default=150, help="leagues to find in the pool crawl (default 150)")
    ap.add_argument("--crawl-seconds", type=int, default=600, help="time cap for pool discovery (default 600)")
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--no-history", action="store_true", help="skip the league's own previous-season walk")
    ap.add_argument("--no-trade-history", action="store_true", help="skip pricing the league's past trades with historical values")
    ap.add_argument("--refresh-values", action="store_true", help="re-download the values feed even if cached today")
    ap.add_argument("--pdf", action="store_true", help="also render brief.pdf (needs Chrome, Chromium or Edge installed)")
    ap.add_argument("--open", action="store_true", help="open the trade board in the browser when done")
    a = ap.parse_args(argv)

    t0 = time.time()
    log = lambda s: print(f"[{time.time() - t0:5.0f}s] {s}", flush=True)  # noqa: E731
    api = Sleeper(a.cache_dir)
    log("pulling league")
    league = League(api, a.league, log=log)
    rid = league.find_team(a.team)
    log(f"team: {league.team_name[rid]} (roster {rid}, manager {league.owner_name[rid]})")
    values = Values.load(a.cache_dir, league.fmt["superflex"], refresh=a.refresh_values)
    log(f"values: DynastyProcess {values.col} as of {values.asof} ({len(values.players)} players)")
    out = a.out or os.path.join(HERE, "out", league.id)
    os.makedirs(out, exist_ok=True)

    # own history
    state = api.state()
    sw, ss = (int(state.get("week") or 0) or None), state.get("season")
    own_bundle = league.bundle()
    chain = [league.id]
    if not a.no_history:
        log("walking this league's history")
        chain = walk_lineage(api, a.cache_dir, league.id, state_week=sw, state_season=ss)
        log(f"history: {len(chain)} seasons ({', '.join(str(load_bundles(a.cache_dir, [c])[c]['league']['season']) for c in chain)})")
    own_bundles = load_bundles(a.cache_dir, chain)
    own_bundles[league.id] = own_bundle

    # benchmark
    shipped_note = ""
    bm = None
    if a.benchmarks:
        bm = bmod.load(a.benchmarks)
        shipped_note = f" (loaded from {os.path.basename(a.benchmarks)})"
    elif not a.pool:
        bm = bmod.find_shipped(os.path.join(HERE, "benchmarks"), league.fmt)
        if bm:
            shipped_note = f" (shipped benchmark built {bm['built']}; run with --pool to crawl a fresh one)"
            log(f"benchmark: shipped {bm['label']} ({bm['team_seasons']} team-seasons)")
    if bm is None:
        log(f"no shipped benchmark for {fmt_key(league.fmt)}; crawling a pool (cap {a.crawl_seconds}s, target {a.pool_target} leagues)")
        # discovery is the slow, uncached part of a crawl: keep the found pool per format for a day so a rerun skips it
        pool_dir = os.path.join(a.cache_dir, "pools")
        os.makedirs(pool_dir, exist_ok=True)
        pool_file = os.path.join(pool_dir, f"{fmt_key(league.fmt)}.json")
        pool = None
        if os.path.exists(pool_file) and time.time() - os.path.getmtime(pool_file) < 86400:
            with open(pool_file, encoding="utf-8") as f:
                pool = json.load(f)
            log(f"pool: {len(pool)} leagues of this format found earlier today (delete {os.path.basename(pool_file)} to rediscover)")
        if pool is None:
            pool = discover_pool(api, league, target=a.pool_target, seconds=a.crawl_seconds, threads=a.threads, log=log)
            with open(pool_file, "w", encoding="utf-8") as f:
                json.dump(pool, f)
        roots = list(pool) + [league.id]
        lineages = crawl_lineages(api, a.cache_dir, roots, threads=a.threads, state_week=sw, state_season=ss, log=log)
        ids = [lid for ch in lineages.values() for lid in ch]
        bundles = load_bundles(a.cache_dir, ids)
        bm = bmod.build(bundles, league.pdb, league.fmt, league.season, log=log)
        bm["pool"] = {"roots": len(pool), "strict": sum(1 for v in pool.values() if v == "strict")}
        bpath = os.path.join(out, f"benchmark-{fmt_key(league.fmt)}.json")
        bmod.save(bm, bpath)
        shipped_note = f" (crawled today: {len(pool)} leagues of this format, saved to {os.path.basename(bpath)})"
        log(f"benchmark saved: {bpath}")

    # grade, ledger, deals
    log("grading")
    g = grade(league, values, rid, bm, own_bundle)
    log(f"call: {g['mode']} (window {g['window']}); " + "; ".join(g["reasons"]))
    assets = classify_assets(g["team"], g["mode"], league)
    log(f"ledger: sell {len(assets['sell'])}, hold {len(assets['hold'])}, keep {len(assets['keep'])}")
    ds = deals(g, league, assets, g["mode"])
    log(f"deals: {len(ds)} across {len({d['counterparty'] for d in ds})} counterparties")
    multi = three_team_deals(g, league, assets, g["mode"])
    if multi:
        log(f"three-team deals: {len(multi)}")
    lineage = report.lineage_table(own_bundles, chain, league.pdb, rid, league) if not a.no_history else []

    # outputs
    th = None
    if not a.no_trade_history:
        log("pricing the league's trade history")
        try:
            th = thmod.build(a.cache_dir, own_bundles, league, values, log=log)
        except Exception as e:  # network or GitHub rate limit: the rest of the run does not depend on it
            log(f"trade history skipped: {e}")
    ct = report.call_text(g, league, bm, assets)
    types = team_types(league, values, bm, own_bundle)
    data = board.board_data(league, values, g, assets, ds, ct, trade_history=th, multi=multi, team_types=types)
    html = board.render(data, os.path.join(out, "trade-board.html"))
    md = report.write(os.path.join(out, "brief.md"), league, values, g, assets, ds, bm, lineage, shipped_note, multi=multi)
    pdf_path = None
    if a.pdf:
        pdf_path, why = pdfmod.render(md, os.path.join(out, "brief.pdf"))
        log(f"pdf: {pdf_path}" if pdf_path else f"pdf skipped: {why}")
    with open(os.path.join(out, "board-data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=0)
    summary = {"league": league.lg.get("name"), "league_id": league.id, "season": league.season, "week": league.week, "team": g["team"]["name"], "roster_id": rid,
               "manager": g["team"]["owner"], "format": fmt_key(league.fmt), "mode": g["mode"], "window": g["window"], "reasons": g["reasons"],
               "record": f"{g['team']['wins']}-{g['team']['losses']}", "rank": g["team"]["rank"], "percentiles": g["pct"], "ledger_rank": g["ledger_rank"],
               "sell": [p["name"] for p in assets["sell"]], "hold": [p["name"] for p in assets["hold"]], "keep": [p["name"] for p in assets["keep"]],
               "deals": [{"title": d["title"], "counterparty": d["counterparty"], "target_value": d["vars"]["Target"]["value"]} for d in ds],
               "benchmark": {"label": bm["label"], "team_seasons": bm["team_seasons"], "built": bm["built"]} if bm else None,
               "api_calls": api.calls, "seconds": round(time.time() - t0)}
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    log(f"done: {api.calls} Sleeper calls")
    print(f"\n{g['team']['name']}: {g['mode'].upper()} (contend in {g['window']})")
    for r in g["reasons"]:
        print(f"  - {r}")
    print(f"\n  brief        {md}" + (f"\n  brief pdf    {pdf_path}" if pdf_path else "") + f"\n  trade board  {html}\n  summary      {os.path.join(out, 'summary.json')}")
    if a.open:
        webbrowser.open("file://" + os.path.abspath(html))
    return 0


if __name__ == "__main__":
    sys.exit(main())
