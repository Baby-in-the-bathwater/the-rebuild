"""The engine's one entry point: an inputs dict in (league pull, players, values, history, snapshots, benchmark, run
date), the report out (summary, board data, brief). No network, no disk, no clock: everything comes from `inputs`."""
import datetime as dt
import json

from . import board, report
from . import trade_history as thmod
from .grade import grade, team_types
from .league import League, fmt_key
from .trades import classify_assets, deals, three_team_deals
from .values import Values

INPUTS_VERSION = 1


def own_bundles(league, chain, history):
    """The league's own season bundles keyed by league id in `chain` order, the current season built from `league`."""
    current = league.bundle()
    out = {}
    for lid in chain:
        if lid == league.id:
            out[lid] = current
        elif lid in history:
            out[lid] = history[lid]
    out.setdefault(league.id, current)
    return out


def _plain(x):
    """A JSON-safe copy of `x`, taken now so later steps cannot change what a stage recorded."""
    return json.loads(json.dumps(x, default=str))


def build_report(inputs: dict, team: str, *, log=print, stages: dict | None = None) -> dict:
    """Returns {"league_id": str, "roster_id": int, "summary": dict, "board_data": dict, "brief": str}.
    `summary` holds every summary.json key but `api_calls` and `seconds`, which belong to the caller. When `stages` is a
    dict it is filled with each intermediate result: league, assets, grade, ledger, deals, three_team_deals, trade_history."""
    if inputs.get("version") != INPUTS_VERSION:
        raise ValueError(f"inputs are version {inputs.get('version')}, expected {INPUTS_VERSION}")
    try:
        run_at = dt.datetime.fromisoformat(str(inputs["run_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        run_at = None
    if run_at is None or run_at.tzinfo is None:
        raise ValueError("inputs run_at must be an ISO timestamp with a timezone")

    def keep(name, value):
        if stages is not None:
            stages[name] = _plain(value)

    options = inputs["options"]
    league = League(inputs["pull"], inputs["players"], inputs["state"])
    rid = league.find_team(team)
    values = Values.from_csv(inputs["values_csv"], league.fmt["superflex"])
    log(f"values: DynastyProcess {values.col} as of {values.asof} ({len(values.players)} players)")
    bm = inputs["benchmark"]
    chain = inputs["chain"]
    bundles = own_bundles(league, chain, inputs["history"])
    own_bundle = bundles[league.id]
    keep("league", {"id": league.id, "name": league.lg.get("name"), "season": league.season, "week": league.week,
                    "status": league.status, "format": fmt_key(league.fmt), "fmt": league.fmt, "n": league.n,
                    "redraft": league.redraft, "pick_seasons": league.pick_seasons, "chain": chain,
                    "teams": [{"rid": r, "name": league.team_name[r], "owner": league.owner_name[r], "rank": league.rank[r]}
                              for r in league.standings]})

    # grade, ledger, deals
    log("grading")
    g = grade(league, values, rid, bm, own_bundle)
    log(f"call: {g['mode']} (window {g['window']}); " + "; ".join(g["reasons"]))
    keep("assets", list(g["teams"].values()))
    assets = classify_assets(g["team"], g["mode"], league)
    log(f"ledger: sell {len(assets['sell'])}, hold {len(assets['hold'])}, keep {len(assets['keep'])}")
    types = team_types(league, values, bm, own_bundle)  # every team's call: buyers for an injured sell, what a third team takes, the board
    keep("grade", {k: v for k, v in g.items() if k != "teams"} | {"team_types": types})
    keep("ledger", assets)
    ds = deals(g, league, assets, g["mode"], types=types)
    log(f"deals: {len(ds)} across {len({d['counterparty'] for d in ds})} counterparties")
    keep("deals", ds)
    try:
        multi = three_team_deals(g, league, assets, g["mode"], types=types)
    except Exception as e:  # an optional section: a failure here should not cost the brief and the board
        log(f"three-team deals skipped: {e}")
        multi = []
    if multi:
        log(f"three-team deals: {len(multi)}")
    keep("three_team_deals", multi)
    lineage = report.lineage_table(bundles, chain, league.pdb, rid, league) if options["history"] else []

    # outputs
    th = None
    if options["trade_history"] and inputs["snapshot_index"] is not None:
        log("pricing the league's trade history")
        try:
            th = thmod.build(bundles, league, values, inputs["snapshot_index"], inputs["snapshots"],
                             now=run_at, log=log)
        except Exception as e:  # a gap in the snapshots, say: the rest of the report does not depend on it
            log(f"trade history skipped: {e}")
    keep("trade_history", th)
    ct = report.call_text(g, league, bm, assets)
    data = board.board_data(league, values, g, assets, ds, ct, trade_history=th, multi=multi, team_types=types)
    brief = report.render(league, values, g, assets, ds, bm, lineage, inputs["benchmark_note"], multi=multi)
    summary = {"league": league.lg.get("name"), "league_id": league.id, "season": league.season, "week": league.week, "team": g["team"]["name"], "roster_id": rid,
               "manager": g["team"]["owner"], "format": fmt_key(league.fmt), "mode": g["mode"], "window": g["window"], "reasons": g["reasons"],
               "record": f"{g['team']['wins']}-{g['team']['losses']}", "rank": g["team"]["rank"], "percentiles": g["pct"], "ledger_rank": g["ledger_rank"],
               "sell": [p["name"] for p in assets["sell"]], "hold": [p["name"] for p in assets["hold"]], "keep": [p["name"] for p in assets["keep"]],
               "deals": [{"title": d["title"], "counterparty": d["counterparty"], "target_value": d["vars"]["Target"]["value"]} for d in ds],
               "benchmark": {"label": bm["label"], "team_seasons": bm["team_seasons"], "built": bm["built"]} if bm else None}
    return {"league_id": league.id, "roster_id": rid, "summary": summary, "board_data": data, "brief": brief}
