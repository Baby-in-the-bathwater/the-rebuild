"""Writes web/fixtures/synth/: the synthetic league as the browser sees it, for the Python and the site's tests.

    python tests/make_web_fixture.py            rewrite the folder
    python tests/make_web_fixture.py --check    exit 1 if the committed folder differs from a fresh build

`http.json` is every request a browser report makes (url -> parsed JSON, or text for CSV); a league that does not exist is
absent. `inputs.json` is what `cli.gather` builds from the same data; `expected/` is `engine.build_report` on it."""
import argparse
import json
import os
import sys
import tempfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rebuild import cli, engine, fetch  # noqa: E402
from tests import synth_league  # noqa: E402

FIXTURE_DIR = os.path.join(ROOT, "web", "fixtures", "synth")
TEAM = "Team 3"
RUN_AT = "2026-11-16T12:00:00Z"
FETCHED = "2026-11-16"
SLEEPER = "https://api.sleeper.app/v1"


def _dump(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def gather(source):
    """What the CLI gathers from `source` (a make_inputs dict): `run_at` fixed, the benchmark without its `_path`."""
    with tempfile.TemporaryDirectory() as tmp:
        args = cli.parse_args(["--league", source["chain"][0], "--team", TEAM, "--cache-dir", os.path.join(tmp, "cache"),
                               "--out", os.path.join(tmp, "out")])
        with mock.patch.object(fetch, "values_csv", lambda *a, **k: source["values_csv"]), \
                mock.patch.object(fetch, "snapshot_index", lambda *a, **k: source["snapshot_index"]), \
                mock.patch.object(fetch, "snapshot_csv", lambda cache_dir, sha: source["snapshots"][sha]):
            inputs = cli.gather(synth_league.FakeSleeper(source), args, lambda s: None)
    inputs["run_at"] = RUN_AT
    inputs["benchmark"] = {k: v for k, v in inputs["benchmark"].items() if k != "_path"}
    for bundle in inputs["history"].values():
        bundle["fetched"] = FETCHED
    return inputs


def recorded_http(source, inputs):
    """Every url a browser report asks for, with the body the fake Sleeper gives. All of weeks 1..18 for matchups and
    transactions, so the fixture does not say which weeks get asked for."""
    api = synth_league.FakeSleeper(source)
    http = {f"{SLEEPER}/state/nfl": source["state"]}
    for lid in inputs["chain"]:
        base = f"{SLEEPER}/league/{lid}"
        http[base] = api.league(lid)
        http[f"{base}/rosters"] = api.rosters(lid)
        http[f"{base}/users"] = api.users(lid)
        http[f"{base}/traded_picks"] = api.traded_picks(lid)
        for wk in range(1, 19):
            http[f"{base}/matchups/{wk}"] = api.matchups(lid, wk)
            http[f"{base}/transactions/{wk}"] = api.transactions(lid, wk)
        http[f"{base}/winners_bracket"] = api.winners_bracket(lid)
        drafts = api.drafts(lid)
        http[f"{base}/drafts"] = drafts
        for d in drafts:
            http[f"{SLEEPER}/draft/{d['draft_id']}/picks"] = api.draft_picks(d["draft_id"])
    http[fetch.VALUES_URL] = source["values_csv"]
    for sha in inputs["snapshots"]:
        http[fetch.RAW_URL.format(sha=sha)] = inputs["snapshots"][sha]
    return http


def files():
    """{relative path: text} for the whole folder."""
    source = synth_league.make_inputs()
    inputs = gather(source)
    report = engine.build_report(inputs, TEAM, log=lambda s: None)
    return {
        "http.json": _dump(recorded_http(source, inputs)),
        "players.json": _dump(inputs["players"]),
        "snapshot_index.json": _dump(source["snapshot_index"]),
        "meta.json": _dump({"league_id": inputs["chain"][0], "team": TEAM, "run_at": RUN_AT}),
        "inputs.json": _dump(inputs),
        "expected/summary.json": _dump(report["summary"]),
        "expected/board-data.json": _dump(report["board_data"]),
        "expected/brief.md": report["brief"],
    }


def build(folder):
    for rel, text in files().items():
        path = os.path.join(folder, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed folder differs from a fresh build")
    a = ap.parse_args(argv)
    if not a.check:
        build(FIXTURE_DIR)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp)
        fresh = {os.path.join(r, n) for r, _, ns in os.walk(tmp) for n in ns}
        want = {os.path.relpath(p, tmp) for p in fresh}
        have = {os.path.relpath(os.path.join(r, n), FIXTURE_DIR) for r, _, ns in os.walk(FIXTURE_DIR) for n in ns}
        bad = sorted(want ^ have)
        for rel in sorted(want & have):
            with open(os.path.join(tmp, rel), encoding="utf-8", newline="") as f, \
                    open(os.path.join(FIXTURE_DIR, rel), encoding="utf-8", newline="") as g:
                if f.read() != g.read():
                    bad.append(rel)
    if bad:
        print("web/fixtures/synth is out of date; run python tests/make_web_fixture.py:", ", ".join(sorted(bad)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
