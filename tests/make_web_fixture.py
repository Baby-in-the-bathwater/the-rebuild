"""Writes web/fixtures/synth/: the synthetic league as the browser sees it, for the Python and the site's tests.

    python tests/make_web_fixture.py            rewrite the folder
    python tests/make_web_fixture.py --check    exit 1 if the committed folder differs from a fresh build

`http.json` is every request a browser report makes (url -> the exact response text); a league that does not exist is
absent. `players.json` and `snapshot_index.json` are the exact text of the player table and the values feed's commit
index. `responses` gives the same texts keyed as `rebuild.web_api`'s `lookup` asks for them. `inputs.json` is what
`cli.gather` builds from the same data; `expected/` is `engine.build_report` on it."""
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


def _dump(obj, sort_keys=True):
    return json.dumps(obj, sort_keys=sort_keys, separators=(",", ":"), ensure_ascii=False) + "\n"


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


def responses(source):
    """{lookup key: exact response text} for every request a browser report makes, with the body the fake Sleeper
    gives (JSON as Python writes it, key order kept). All of weeks 1..18 for matchups and transactions, so the
    fixture does not say which weeks get asked for."""
    api = synth_league.FakeSleeper(source)
    out = {"state/nfl": json.dumps(api.state())}
    for lid in source["chain"]:
        base = f"league/{lid}"
        out[base] = json.dumps(api.league(lid))
        out[f"{base}/rosters"] = json.dumps(api.rosters(lid))
        out[f"{base}/users"] = json.dumps(api.users(lid))
        out[f"{base}/traded_picks"] = json.dumps(api.traded_picks(lid))
        for wk in range(1, 19):
            out[f"{base}/matchups/{wk}"] = json.dumps(api.matchups(lid, wk))
            out[f"{base}/transactions/{wk}"] = json.dumps(api.transactions(lid, wk))
        out[f"{base}/winners_bracket"] = json.dumps(api.winners_bracket(lid))
        drafts = api.drafts(lid)
        out[f"{base}/drafts"] = json.dumps(drafts)
        for d in drafts:
            out[f"draft/{d['draft_id']}/picks"] = json.dumps(api.draft_picks(d["draft_id"]))
    out["players"] = json.dumps(api.players())
    out["values_csv"] = source["values_csv"]
    out["snapshot_index"] = json.dumps(source["snapshot_index"])
    for sha, text in source["snapshots"].items():
        out[f"snapshot/{sha}"] = text
    return out


OWN_FILES = {"players": "players.json", "snapshot_index": "snapshot_index.json"}   # keys kept out of http.json


def url_of(key):
    if key == "values_csv":
        return fetch.VALUES_URL
    if key.startswith("snapshot/"):
        return fetch.RAW_URL.format(sha=key[len("snapshot/"):])
    return f"{SLEEPER}/{key}"


def key_of(url):
    """The lookup key for a url in http.json."""
    if url == fetch.VALUES_URL:
        return "values_csv"
    prefix, suffix = fetch.RAW_URL.split("{sha}")
    if url.startswith(prefix) and url.endswith(suffix):
        return "snapshot/" + url[len(prefix):-len(suffix)]
    if url.startswith(SLEEPER + "/"):
        return url[len(SLEEPER) + 1:]
    raise ValueError(f"not a url a browser report asks for: {url}")


def read_responses(folder):
    """{lookup key: text} from a fixture folder's http.json, players.json and snapshot_index.json."""
    with open(os.path.join(folder, "http.json"), encoding="utf-8") as f:
        out = {key_of(url): text for url, text in json.load(f).items()}
    for key, name in OWN_FILES.items():
        with open(os.path.join(folder, name), encoding="utf-8", newline="") as f:
            out[key] = f.read()
    return out


def files():
    """{relative path: text} for the whole folder."""
    source = synth_league.make_inputs()
    inputs = gather(source)
    report = engine.build_report(inputs, TEAM, log=lambda s: None)
    texts = responses(source)
    return {
        "http.json": _dump({url_of(k): t for k, t in texts.items() if k not in OWN_FILES}),
        **{name: texts[key] for key, name in OWN_FILES.items()},
        "meta.json": _dump({"league_id": inputs["chain"][0], "team": TEAM, "run_at": RUN_AT}),
        "inputs.json": _dump(inputs, sort_keys=False),
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
