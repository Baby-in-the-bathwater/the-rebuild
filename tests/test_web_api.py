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
from tests import synth_league

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCHMARKS = os.path.join(ROOT, "benchmarks")
QUIET = lambda s: None  # noqa: E731

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
i = json.load(open(sys.argv[1]))
out = json.loads(web_api.build(json.dumps(i), "Team 3"))
assert out["ok"], out
json.dump(out["report"], open(sys.argv[2], "w"))
"""


def roundtrip(x):
    return json.loads(json.dumps(x))


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.old = web_api.BENCHMARK_DIR
        web_api.BENCHMARK_DIR = BENCHMARKS
        self.addCleanup(setattr, web_api, "BENCHMARK_DIR", self.old)

    def partial(self, i, **over):
        keys = ("state", "players", "pull", "chain", "history", "snapshot_index")
        return json.dumps({**{k: i[k] for k in keys}, **over})

    def test_current_week(self):
        for week in (6, 0):
            i = synth_league.make_inputs(week=week)
            lg = i["pull"]["league"]
            self.assertEqual(web_api.current_week(json.dumps(lg), json.dumps(i["state"])), League(i["pull"], i["players"], i["state"]).week)
        done = synth_league.make_inputs()
        lg = {**done["pull"]["league"], "status": "complete"}
        self.assertEqual(web_api.current_week(json.dumps(lg), json.dumps(done["state"])), int(lg["settings"].get("playoff_week_start") or 15) - 1)

    def test_plan_snapshots(self):
        i = synth_league.make_inputs()
        out = json.loads(web_api.plan(self.partial(i)))
        self.assertEqual(out["snapshot_index"], i["snapshot_index"])
        self.assertEqual(set(out["snapshot_shas"]), set(i["snapshots"]))
        none = synth_league.make_inputs(trades=False)
        out = json.loads(web_api.plan(self.partial(none)))
        self.assertEqual((out["snapshot_index"], out["snapshot_shas"]), ([], []))
        out = json.loads(web_api.plan(self.partial(i, snapshot_index=None)))
        self.assertEqual((out["snapshot_index"], out["snapshot_shas"]), (None, []))

    def test_plan_teams_in_standings_order(self):
        i = synth_league.make_inputs()
        league = League(i["pull"], i["players"], i["state"])
        out = json.loads(web_api.plan(self.partial(i)))
        self.assertEqual([t["rid"] for t in out["teams"]], league.standings)
        self.assertEqual(out["teams"][0], {"rid": league.standings[0], "name": league.team_name[league.standings[0]], "owner": league.owner_name[league.standings[0]]})

    def test_plan_benchmark(self):
        i = synth_league.make_inputs()
        out = json.loads(web_api.plan(self.partial(i)))
        self.assertEqual(out["benchmark"], i["benchmark"])
        self.assertNotIn("_path", out["benchmark"])
        self.assertEqual(out["benchmark_note"], i["benchmark_note"])
        with tempfile.TemporaryDirectory() as empty:
            web_api.BENCHMARK_DIR = empty
            out = json.loads(web_api.plan(self.partial(i)))
        self.assertEqual((out["benchmark"], out["benchmark_note"]), (None, " (no benchmark for this format yet)"))

    def test_build_matches_the_engine(self):
        i = synth_league.make_inputs()
        lines = []
        out = json.loads(web_api.build(json.dumps(i), "Team 3", lines.append))
        self.assertTrue(out["ok"])
        self.assertEqual(out["report"], roundtrip(engine.build_report(i, "Team 3", log=QUIET)))
        self.assertTrue(lines)
        self.assertTrue(json.loads(web_api.build(json.dumps(i), "Team 3"))["ok"])

    def test_build_errors(self):
        i = synth_league.make_inputs()
        out = json.loads(web_api.build(json.dumps(i), "No Such Team"))
        self.assertEqual((out["ok"], out["kind"]), (False, "team"))
        self.assertIn("Teams in this league", out["message"])
        out = json.loads(web_api.build(json.dumps({**i, "version": 99}), "Team 3"))
        self.assertEqual((out["ok"], out["kind"]), (False, "inputs"))
        out = json.loads(web_api.build(json.dumps({**i, "values_csv": 5}), "Team 3"))
        self.assertEqual((out["ok"], out["kind"]), (False, "engine"))

    def test_build_reports_an_unserialisable_report_as_an_engine_error(self):
        i = synth_league.make_inputs()
        for bad in ({"x": {1, 2}}, {"x": float("nan")}):
            with mock.patch.object(engine, "build_report", return_value=bad):
                out = json.loads(web_api.build(json.dumps(i), "Team 3"))
            self.assertEqual((out["ok"], out["kind"]), (False, "engine"))


class BrowserEnvironmentTest(unittest.TestCase):
    def run_refusing(self, path):
        i = synth_league.make_inputs()
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, "in.json"), os.path.join(tmp, "out.json")
            with open(src, "w") as f:
                json.dump(i, f)
            r = subprocess.run([sys.executable, "-c", REFUSE + RUN, src, dst], cwd=path, capture_output=True, text=True,
                               env={**os.environ, "PYTHONPATH": path, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(dst) as f:
                got = json.load(f)
        self.assertEqual(got, roundtrip(engine.build_report(i, "Team 3", log=QUIET)))

    def test_imports_without_requests_numpy_or_threads(self):
        self.run_refusing(ROOT)

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
            self.run_refusing(os.path.join(tmp, "unpacked"))


if __name__ == "__main__":
    unittest.main()
