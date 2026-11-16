"""the-rebuild: league id + team name in, graded brief and interactive trade board out.

    python -m rebuild --league 123456789 --team "My Team"

Steps: pull the league, price every asset, walk the league's own history, load (or crawl) the format benchmark,
grade the roster, make the call, draft the deals, write brief.md + trade-board.html + data JSON."""
import argparse
import datetime as dt
import json
import os
import sys
import time
import webbrowser

from . import benchmarks as bmod
from . import pdf as pdfmod
from . import board, engine, fetch, inputs as inputs_mod
from . import trade_history as thmod
from .crawl import crawl_lineages, discover_pool, load_bundles, walk_lineage
from .league import League, fmt_key
from .sleeper import Sleeper

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# options that only shape the gathering, which --replay skips
REPLAY_IGNORED = ("--league", "--pool", "--pool-target", "--crawl-seconds", "--threads", "--benchmarks", "--cache-dir",
                  "--refresh-values", "--no-history", "--no-trade-history")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="rebuild", description="Grade a Sleeper dynasty roster against what wins its format and draft the trades.")
    ap.add_argument("--league", help="Sleeper league id (the number in the league URL; required unless --replay)")
    ap.add_argument("--team", help="team name, manager display name, username, or roster id (required unless --replay, which defaults to the recorded team)")
    ap.add_argument("--out", default=None, help="output folder (default out/<league id>, or out/replay with --replay)")
    ap.add_argument("--record", metavar="DIR", help="after the run, save the gathered inputs to DIR (holds the league's data)")
    ap.add_argument("--replay", metavar="DIR", help="rebuild the report from inputs saved with --record; makes no network call")
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
    if a.record and a.replay:
        ap.error("use --record or --replay, not both")
    if a.replay:
        # a second parse into a namespace that already holds a sentinel for every option: defaults are not applied, so what differs was typed
        unset = object()
        given = ap.parse_args(argv, namespace=argparse.Namespace(**{act.dest: unset for act in ap._actions}))
        for flag in REPLAY_IGNORED:
            if getattr(given, flag[2:].replace("-", "_")) is not unset:
                ap.error(f"--replay takes its data from the recording; remove {flag}")
    if not a.replay and not (a.league and a.team):
        ap.error("--league and --team are required (unless --replay)")
    return a


def out_dir(a, league_id):
    return a.out or os.path.join(HERE, "out", league_id)


def gather(api, a, log):
    """Everything the engine reads, fetched from Sleeper, DynastyProcess and the cache: the inputs dict `engine.build_report` takes."""
    run_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    log("pulling league")
    state = api.state()
    pull = fetch.league_pull(api, a.league, state)
    if not pull:
        raise SystemExit(f"League {a.league} not found on Sleeper.")
    league = League(pull, api.players(), state)
    log(f"league: {league.lg.get('name')} | {fmt_key(league.fmt)} | season {league.season} {league.status} | week {league.week} | {api.calls} calls")
    rid = league.find_team(a.team)
    log(f"team: {league.team_name[rid]} (roster {rid}, manager {league.owner_name[rid]})")
    values_csv = fetch.values_csv(a.cache_dir, refresh=a.refresh_values)

    # own history
    sw, ss = (int(state.get("week") or 0) or None), state.get("season")
    chain = [league.id]
    if not a.no_history:
        log("walking this league's history")
        chain = walk_lineage(api, a.cache_dir, league.id, state_week=sw, state_season=ss)
        log(f"history: {len(chain)} seasons ({', '.join(str(load_bundles(a.cache_dir, [c])[c]['league']['season']) for c in chain)})")
    history = load_bundles(a.cache_dir, [c for c in chain if c != league.id])

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
        bpath = os.path.join(out_dir(a, league.id), f"benchmark-{fmt_key(league.fmt)}.json")
        os.makedirs(out_dir(a, league.id), exist_ok=True)
        bmod.save(bm, bpath)
        shipped_note = f" (crawled today: {len(pool)} leagues of this format, saved to {os.path.basename(bpath)})"
        log(f"benchmark saved: {bpath}")

    # the values feed's history, for pricing past trades
    index, snapshots = None, {}
    if not a.no_trade_history:
        own_bundles = engine.own_bundles(league, chain, history)
        try:
            index = fetch.snapshot_index(a.cache_dir) if thmod.completed_trades(own_bundles) else []
            snapshots = {sha: fetch.snapshot_csv(a.cache_dir, sha) for sha in thmod.needed_snapshots(own_bundles, index)}
        except Exception as e:  # network or GitHub rate limit: the rest of the run does not depend on it
            log(f"trade history skipped: {e}")
            index, snapshots = None, {}
    return {"version": engine.INPUTS_VERSION, "run_at": run_at, "options": {"history": not a.no_history, "trade_history": not a.no_trade_history},
            "state": state, "players": league.pdb, "pull": pull, "chain": chain, "history": history, "values_csv": values_csv,
            "snapshot_index": index, "snapshots": snapshots, "benchmark": bm, "benchmark_note": shipped_note}


def main(argv=None, api=None):
    a = parse_args(argv)
    t0 = time.time()
    log = lambda s: print(f"[{time.time() - t0:5.0f}s] {s}", flush=True)  # noqa: E731
    stages = {} if a.replay else None
    try:
        if a.replay:
            gathered, recorded_team = inputs_mod.load(a.replay)
            team = a.team or recorded_team
            log(f"replaying {a.replay}")
            api_calls = 0
        else:
            api = api or Sleeper(a.cache_dir)
            gathered, team = gather(api, a, log), a.team
        r = engine.build_report(gathered, team, log=log, stages=stages)
    except ValueError as e:
        if not a.replay:
            raise
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not a.replay:
        api_calls = api.calls
    if a.replay:
        out = a.out or os.path.join(HERE, "out", "replay")
    else:
        out = out_dir(a, r["league_id"])
    os.makedirs(out, exist_ok=True)

    html = board.render(r["board_data"], os.path.join(out, "trade-board.html"))
    md = os.path.join(out, "brief.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write(r["brief"])
    pdf_path = None
    if a.pdf:
        pdf_path, why = pdfmod.render(md, os.path.join(out, "brief.pdf"))
        log(f"pdf: {pdf_path}" if pdf_path else f"pdf skipped: {why}")
    with open(os.path.join(out, "board-data.json"), "w", encoding="utf-8") as f:
        json.dump(r["board_data"], f, indent=0)
    summary = {**r["summary"], "api_calls": api_calls, "seconds": round(time.time() - t0)}
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    if stages is not None:
        os.makedirs(os.path.join(out, "stages"), exist_ok=True)
        for name, value in stages.items():
            with open(os.path.join(out, "stages", f"{name}.json"), "w", encoding="utf-8") as f:
                json.dump(value, f, indent=1)
    log(f"done: replayed from {a.replay}" if a.replay else f"done: {api_calls} Sleeper calls")
    print(f"\n{summary['team']}: {summary['mode'].upper()} (contend in {summary['window']})")
    for reason in summary["reasons"]:
        print(f"  - {reason}")
    print(f"\n  brief        {md}" + (f"\n  brief pdf    {pdf_path}" if pdf_path else "") + f"\n  trade board  {html}\n  summary      {os.path.join(out, 'summary.json')}")
    if a.record:
        try:
            inputs_mod.save(gathered, a.record, team)
        except (ValueError, OSError) as e:
            print(f"error: {e}; the report was written, the recording was not saved", file=sys.stderr)
            return 2
        print(f"  recording    {a.record} (holds the league's data; keep it out of public repos)")
    if a.open:
        webbrowser.open("file://" + os.path.abspath(html))
    return 0


if __name__ == "__main__":
    sys.exit(main())
