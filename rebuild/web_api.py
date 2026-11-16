"""What the browser calls: JSON text in, JSON text out, so the page needs nothing Python-specific.

`plan` says which extra data the page still has to fetch, `build` runs the engine. Nothing here reads the network,
the disk (but the shipped benchmarks, in BENCHMARK_DIR) or the clock."""
import json

from . import benchmarks as bmod
from . import engine
from . import trade_history as thmod
from .league import League, current_week as _current_week, fmt_key

BENCHMARK_DIR = None  # set by the loader to the folder holding the shipped benchmark files


def current_week(league_json: str, state_json: str) -> int:
    return _current_week(json.loads(league_json), json.loads(state_json))


def plan(partial_json: str) -> str:
    p = json.loads(partial_json)
    league = League(p["pull"], p["players"], p["state"])
    own = engine.own_bundles(league, p["chain"], p["history"])
    index = p.get("snapshot_index")
    if not thmod.completed_trades(own):
        index, shas = [], []
    elif index is None:
        shas = []
    else:
        shas = list(thmod.needed_snapshots(own, index))
    bm = bmod.find_shipped(BENCHMARK_DIR, league.fmt) if BENCHMARK_DIR else None
    if bm:
        bm = {k: v for k, v in bm.items() if k != "_path"}
        note = f" (shipped benchmark built {bm['built']}; run with --pool to crawl a fresh one)"
    else:
        bm, note = None, " (no benchmark for this format yet)"
    teams = [{"rid": r, "name": league.team_name[r], "owner": league.owner_name[r]} for r in league.standings]
    return json.dumps({"snapshot_index": index, "snapshot_shas": shas, "benchmark": bm, "benchmark_note": note, "teams": teams})


def build(inputs_json: str, team: str, log=None) -> str:
    try:
        report = engine.build_report(json.loads(inputs_json), team, log=log or (lambda s: None))
    except SystemExit as e:
        return json.dumps({"ok": False, "kind": "team", "message": str(e)})
    except ValueError as e:
        return json.dumps({"ok": False, "kind": "inputs", "message": str(e)})
    except Exception as e:  # noqa: BLE001 - the page shows whatever went wrong
        return json.dumps({"ok": False, "kind": "engine", "message": f"{type(e).__name__}: {e}"})
    try:
        return json.dumps({"ok": True, "report": report}, allow_nan=False)
    except (TypeError, ValueError) as e:  # a report the browser could not read (NaN, a set)
        return json.dumps({"ok": False, "kind": "engine", "message": f"{type(e).__name__}: {e}"})
