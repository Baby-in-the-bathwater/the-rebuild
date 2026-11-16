"""What the browser calls: the page hands over the exact text of each response, Python does the rest.

`lookup(key)` returns one response's text, or None if there is none. Keys are the Sleeper paths `rebuild/sleeper.py`
requests (`state/nfl`, `league/<id>`, `league/<id>/matchups/<week>`, `draft/<id>/picks`, ...), plus `players` (the
player table), `values_csv`, `snapshot_index` (`[[iso date, sha], ...]`) and `snapshot/<sha>` (one historical CSV).
The inputs are assembled with the CLI's own code, so the engine sees what the CLI would have seen. `plan` says what the
page still has to fetch, `build` runs the engine; both return JSON text. Nothing here reads the network, the disk (but
the shipped benchmarks, in BENCHMARK_DIR) or the clock (but the `fetched` date `season_bundle` notes)."""
import json

from . import benchmarks as bmod
from . import engine
from . import trade_history as thmod
from .crawl import season_bundle
from .league import League, league_pull

BENCHMARK_DIR = None  # set by the loader to the folder holding the shipped benchmark files
MAX_SEASONS = 12      # walk_lineage's default


class _Responses:
    """The `Sleeper` methods the assembling code calls, answered from `lookup` with `Sleeper`'s defaults for a missing
    response. Each key is looked up once."""

    def __init__(self, lookup):
        self._lookup = lookup
        self._texts = {}

    def text(self, key):
        if key not in self._texts:
            self._texts[key] = self._lookup(key)
        return self._texts[key]

    def get(self, key):
        text = self.text(key)
        return None if text is None else json.loads(text)

    def state(self):
        return self.get("state/nfl") or {}

    def league(self, lid):
        return self.get(f"league/{lid}")

    def rosters(self, lid):
        return self.get(f"league/{lid}/rosters") or []

    def users(self, lid):
        return self.get(f"league/{lid}/users") or []

    def traded_picks(self, lid):
        return self.get(f"league/{lid}/traded_picks") or []

    def matchups(self, lid, week):
        return self.get(f"league/{lid}/matchups/{week}") or []

    def transactions(self, lid, week):
        return self.get(f"league/{lid}/transactions/{week}") or []

    def winners_bracket(self, lid):
        return self.get(f"league/{lid}/winners_bracket") or []

    def drafts(self, lid):
        return self.get(f"league/{lid}/drafts") or []

    def draft_picks(self, draft_id):
        return self.get(f"draft/{draft_id}/picks") or []


def _league(api, league_id):
    """(state, pull, league, chain, history) as `cli.gather` has them with history on, or None if there is no such league.
    The chain follows `previous_league_id` the way `walk_lineage` does, but takes the current season from the pull."""
    state = api.state()
    pull = league_pull(api, league_id, state)
    if not pull:
        return None
    league = League(pull, api.get("players") or {}, state)
    sw, ss = (int(state.get("week") or 0) or None), state.get("season")
    chain, history = [], {}
    lid = league.id
    while lid and lid != "0" and len(chain) < MAX_SEASONS:
        if not chain:
            b = pull   # the root: walk_lineage fetches it only to read previous_league_id
        else:
            b = season_bundle(api, lid, state_week=sw, state_season=ss)
            if not b:
                break
            if lid != league.id:
                history[lid] = b
        chain.append(lid)
        lid = b["league"].get("previous_league_id")
    return state, pull, league, chain, history


def _snapshots(api, own):
    """(index, {sha: csv}) as `cli.gather` fetches them; raises LookupError when the index or a snapshot is missing."""
    if not thmod.completed_trades(own):
        index = []
    else:
        index = api.get("snapshot_index")
        if index is None:
            raise LookupError("no snapshot index")
    out = {}
    for sha in thmod.needed_snapshots(own, index):
        text = api.text(f"snapshot/{sha}")
        if text is None:
            raise LookupError(f"no snapshot {sha}")
        out[sha] = text
    return index, out


def _inputs(api, league_id, run_at, log):
    """The inputs dict `cli.gather` builds for a default run (history and trade history on, shipped benchmark only),
    or None if there is no such league."""
    found = _league(api, league_id)
    if found is None:
        return None
    state, pull, league, chain, history = found
    values_csv = api.text("values_csv")
    if values_csv is None:   # the CLI stops when this fetch fails; an empty feed would price every asset at 0
        raise ValueError("no values feed")
    bm =bmod.find_shipped(BENCHMARK_DIR, league.fmt) if BENCHMARK_DIR else None
    if bm:
        bm = {k: v for k, v in bm.items() if k != "_path"}
        note = f" (shipped benchmark built {bm['built']}; run with --pool to crawl a fresh one)"
    else:
        bm, note = None, " (no benchmark for this format yet)"
    own = engine.own_bundles(league, chain, history)
    try:
        index, snapshots = _snapshots(api, own)
    except Exception as e:  # noqa: BLE001 - as the CLI treats a failed fetch: the rest of the run does not need it
        log(f"trade history skipped: {e}")
        index, snapshots = None, {}
    return {"version": engine.INPUTS_VERSION, "run_at": run_at, "options": {"history": True, "trade_history": True},
            "state": state, "players": league.pdb, "pull": pull, "chain": chain, "history": history, "values_csv": values_csv,
            "snapshot_index": index, "snapshots": snapshots, "benchmark": bm, "benchmark_note": note}


def plan(lookup, league_id: str) -> str:
    api = _Responses(lookup)
    found = _league(api, league_id)
    if found is None:
        return json.dumps({"found": False})
    _, _, league, chain, history = found
    own = engine.own_bundles(league, chain, history)
    index = api.get("snapshot_index") if thmod.completed_trades(own) else None
    shas = list(thmod.needed_snapshots(own, index)) if index is not None else []
    teams = [{"rid": r, "name": league.team_name[r], "owner": league.owner_name[r]} for r in league.standings]
    info = {"name": league.lg.get("name"), "season": str(league.lg.get("season")), "status": league.status, "week": league.week}
    return json.dumps({"found": True, "league": info, "chain": chain, "snapshot_shas": shas, "teams": teams})


def build(lookup, league_id: str, team: str, run_at: str, log=None) -> str:
    log = log or (lambda s: None)
    try:
        inputs = _inputs(_Responses(lookup), league_id, run_at, log)
        if inputs is None:
            return json.dumps({"ok": False, "kind": "league", "message": f"League {league_id} not found on Sleeper."})
        report = engine.build_report(inputs, team, log=log)
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
