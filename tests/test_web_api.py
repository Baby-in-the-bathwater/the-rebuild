import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

from rebuild import engine, web_api
from rebuild.league import League
from tests import make_web_fixture, synth_league

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCHMARKS = os.path.join(ROOT, "benchmarks")
QUIET = lambda s: None  # noqa: E731
RUN_AT = make_web_fixture.RUN_AT

# a subprocess runs this first: names the browser cannot import are refused, then the engine bundle is exercised
REFUSE = """
import sys
class Refuse:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("requests", "numpy", "threading"):
            raise ImportError("refused: " + name)
sys.meta_path.insert(0, Refuse())
"""
RUN = """
import json, sys
from rebuild import web_api
web_api.BENCHMARK_DIR = sys.argv[3]
texts, league_id, run_at = json.load(open(sys.argv[1]))
assert json.loads(web_api.plan(texts.get, league_id))["found"]
out = json.loads(web_api.build(texts.get, league_id, "Team 3", run_at))
assert out["ok"], out
json.dump(out["report"], open(sys.argv[2], "w"))
"""


def roundtrip(x):
    return json.loads(json.dumps(x))


def expected_report(source):
    """The report the CLI gives for `source`, as the browser reads it."""
    return roundtrip(engine.build_report(make_web_fixture.gather(source), "Team 3", log=QUIET))


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.old = web_api.BENCHMARK_DIR
        web_api.BENCHMARK_DIR = BENCHMARKS
        self.addCleanup(setattr, web_api, "BENCHMARK_DIR", self.old)
        self.source = synth_league.make_inputs()
        self.lid = self.source["chain"][0]

    def lookup(self, source=None, drop=()):
        texts = make_web_fixture.responses(source or self.source)
        return lambda key: None if key in drop else texts.get(key)

    def plan(self, lookup=None, league_id=None):
        return json.loads(web_api.plan(lookup or self.lookup(), league_id or self.lid))

    def build(self, lookup=None, team="Team 3", league_id=None, log=None):
        return json.loads(web_api.build(lookup or self.lookup(), league_id or self.lid, team, RUN_AT, log))

    def inputs(self):
        return web_api._inputs(web_api._Responses(self.lookup()), self.lid, RUN_AT, QUIET)

    def test_assembles_the_inputs_the_cli_gathers(self):
        got = self.inputs()
        for bundle in got["history"].values():
            bundle["fetched"] = make_web_fixture.FETCHED
        want = make_web_fixture.gather(self.source)   # run_at fixed, history's fetched fixed, the benchmark's _path dropped
        self.assertEqual(got, want)
        self.assertEqual(list(got["players"]), list(want["players"]))
        self.assertEqual(list(got["benchmark"]), list(want["benchmark"]))
        self.assertEqual(json.dumps(got), json.dumps(want))   # every key order, and 4.0 stays 4.0

    def test_looks_up_each_key_once(self):
        asked = []
        texts = make_web_fixture.responses(self.source)
        self.assertTrue(self.build(lambda key: asked.append(key) or texts.get(key))["ok"])
        self.assertEqual(len(asked), len(set(asked)))

    def test_plan(self):
        out = self.plan()
        league = League(self.source["pull"], self.source["players"], self.source["state"])
        self.assertTrue(out["found"])
        self.assertEqual(out["league"], {"name": league.lg["name"], "season": str(league.lg["season"]), "status": league.status,
                                         "week": league.week})
        self.assertEqual(out["chain"], self.source["chain"])
        self.assertTrue(out["snapshot_shas"])
        self.assertEqual(set(out["snapshot_shas"]), set(self.source["snapshots"]))
        self.assertEqual([t["rid"] for t in out["teams"]], league.standings)
        r = league.standings[0]
        self.assertEqual(out["teams"][0], {"rid": r, "name": league.team_name[r], "owner": league.owner_name[r]})

    def test_plan_without_snapshots(self):
        self.assertEqual(self.plan(self.lookup(drop={"snapshot_index"}))["snapshot_shas"], [])
        none = synth_league.make_inputs(trades=False)
        self.assertEqual(self.plan(self.lookup(none), none["chain"][0])["snapshot_shas"], [])
        csvs = {k for k in make_web_fixture.responses(self.source) if k.startswith("snapshot/")}
        self.assertEqual(set(self.plan(self.lookup(drop=csvs))["snapshot_shas"]), set(self.source["snapshots"]))   # needs only the index

    def test_plan_before_the_draft_and_without_history(self):
        for source in (synth_league.make_inputs(week=0), synth_league.make_inputs(history=False)):
            out = self.plan(self.lookup(source), source["chain"][0])
            self.assertEqual(out["chain"], source["chain"])

    def test_league_not_found(self):
        self.assertEqual(self.plan(league_id="L404"), {"found": False})
        out = self.build(league_id="L404")
        self.assertEqual((out["ok"], out["kind"]), (False, "league"))
        self.assertIn("L404", out["message"])

    def test_build_matches_the_cli(self):
        lines = []
        out = self.build(log=lines.append)
        self.assertTrue(out["ok"])
        self.assertEqual(out["report"], expected_report(self.source))
        self.assertTrue(lines)
        self.assertTrue(self.build()["ok"])

    def test_build_without_trade_history_data(self):
        csvs = {k for k in make_web_fixture.responses(self.source) if k.startswith("snapshot/")}
        for drop, reason in (({"snapshot_index"}, "no snapshot index"), (csvs, "no snapshot ")):
            lines = []
            out = self.build(self.lookup(drop=drop), log=lines.append)
            self.assertTrue(out["ok"])
            self.assertIsNone(out["report"]["board_data"]["trade_history"])
            self.assertTrue([l for l in lines if l.startswith(f"trade history skipped: {reason}")], lines)

    def test_benchmark_present_and_absent(self):
        got = self.inputs()
        self.assertEqual(got["benchmark"], self.source["benchmark"])
        self.assertNotIn("_path", got["benchmark"])
        self.assertEqual(got["benchmark_note"], self.source["benchmark_note"])
        with tempfile.TemporaryDirectory() as empty:
            web_api.BENCHMARK_DIR = empty
            got = self.inputs()
            self.assertTrue(self.build()["ok"])
        self.assertEqual((got["benchmark"], got["benchmark_note"]), (None, " (no benchmark for this format yet)"))

    def test_build_says_when_no_benchmark_matches_the_format(self):
        note = "no benchmark for this league format: depth is graded at the middle of the pool"
        lines = []
        self.assertTrue(self.build(log=lines.append)["ok"])
        self.assertNotIn(note, lines)
        with tempfile.TemporaryDirectory() as empty:
            web_api.BENCHMARK_DIR = empty
            lines = []
            out = self.build(log=lines.append)
        self.assertTrue(out["ok"])
        self.assertIsNone(out["report"]["summary"]["benchmark"])
        self.assertEqual(lines.count(note), 1)

    def test_build_errors(self):
        out = self.build(team="No Such Team")
        self.assertEqual((out["ok"], out["kind"]), (False, "team"))
        self.assertIn("Teams in this league", out["message"])
        texts = make_web_fixture.responses(self.source)
        out = self.build(lambda k: "{not json" if k == "players" else texts.get(k))
        self.assertEqual((out["ok"], out["kind"]), (False, "inputs"))
        out = self.build(lambda k: None if k == "values_csv" else texts.get(k))
        self.assertEqual((out["ok"], out["kind"], out["message"]), (False, "inputs", "no values feed"))
        with mock.patch.object(engine, "build_report", side_effect=KeyError("pull")):
            out = self.build()
        self.assertEqual((out["ok"], out["kind"]), (False, "engine"))

    def test_build_reports_an_unserialisable_report_as_an_engine_error(self):
        for bad in ({"x": {1, 2}}, {"x": float("nan")}):
            with mock.patch.object(engine, "build_report", return_value=bad):
                out = self.build()
            self.assertEqual((out["ok"], out["kind"]), (False, "engine"))

    def test_a_failing_lookup_is_an_engine_error(self):
        def broken(key):
            raise RuntimeError("offline")
        out = self.build(broken)
        self.assertEqual((out["ok"], out["kind"]), (False, "engine"))
        self.assertIn("offline", out["message"])


class BrowserEnvironmentTest(unittest.TestCase):
    def run_refusing(self, path, benchmarks):
        source = synth_league.make_inputs()
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, "in.json"), os.path.join(tmp, "out.json")
            with open(src, "w") as f:
                json.dump([make_web_fixture.responses(source), source["chain"][0], RUN_AT], f)
            r = subprocess.run([sys.executable, "-c", REFUSE + RUN, src, dst, benchmarks], cwd=path, capture_output=True, text=True,
                               env={**os.environ, "PYTHONPATH": path, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(dst) as f:
                got = json.load(f)
        self.assertEqual(got, expected_report(source))

    def test_imports_without_requests_numpy_or_threads(self):
        self.run_refusing(ROOT, BENCHMARKS)

    def test_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = os.path.join(tmp, "engine.zip")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "web", "scripts", "build_engine.py"), "--out", zp], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertRegex(r.stdout, r"\d+ files")
            with zipfile.ZipFile(zp) as z:
                names = set(z.namelist())
                z.extractall(os.path.join(tmp, "unpacked"))
            for n in ("rebuild/engine.py", "rebuild/web_api.py", "benchmarks/benchmark-dynasty-12team-sf-halfppr-tep.json", "benchmarks/dynasty-12team-sf-halfppr.json"):
                self.assertIn(n, names)
            for n in ("rebuild/cli.py", "rebuild/fetch.py", "rebuild/sleeper.py", "rebuild/__main__.py", "rebuild/inputs.py", "rebuild/pdf.py"):
                self.assertNotIn(n, names)
            self.assertFalse([n for n in names if n.endswith(".pyc") or "templates" in n])
            unpacked = os.path.join(tmp, "unpacked")
            self.run_refusing(unpacked, os.path.join(unpacked, "benchmarks"))


if __name__ == "__main__":
    unittest.main()
