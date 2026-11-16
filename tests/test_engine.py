import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from rebuild import cli, engine, fetch, inputs, trade_history
from rebuild.grade import grade, team_types
from rebuild.league import League
from rebuild.values import Values
from tests import synth_league


class SynthTest(unittest.TestCase):
    def test_inputs_are_stable_and_public_safe(self):
        a, b = synth_league.make_inputs(), synth_league.make_inputs()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertIsNone(re.search(r"(?<![\d.])\d{17,20}(?![\d.])", json.dumps(a)))
        self.assertEqual(a["version"], 1)
        self.assertEqual(a["chain"][0], a["pull"]["league"]["league_id"])
        self.assertEqual(set(a["history"]), set(a["chain"][1:]))


class PureEngineTest(unittest.TestCase):
    def test_engine_modules_import_without_requests_or_numpy(self):
        code = ("import sys; import rebuild.league, rebuild.values, rebuild.metrics, rebuild.grade, rebuild.trades, "
                "rebuild.trade_history, rebuild.report, rebuild.board; "
                "assert 'requests' not in sys.modules and 'numpy' not in sys.modules")
        self.assertEqual(subprocess.run([sys.executable, "-c", code]).returncode, 0)

    def test_league_builds_from_data(self):
        i = synth_league.make_inputs()
        lg = League(i["pull"], i["players"], i["state"])
        self.assertEqual(lg.n, 12)
        self.assertEqual(lg.week, 6)
        self.assertEqual(League(synth_league.make_inputs(week=0)["pull"], i["players"], i["state"]).week, 0)

    def test_fetch_pull_matches_inputs(self):
        i = synth_league.make_inputs()
        api = synth_league.FakeSleeper(i)
        self.assertEqual(fetch.league_pull(api, i["chain"][0], i["state"]), i["pull"])

    def test_trade_history_uses_the_given_now(self):
        i = synth_league.make_inputs()
        lg = League(i["pull"], i["players"], i["state"])
        values = Values.from_csv(i["values_csv"], lg.fmt["superflex"])
        bundles = {**i["history"], lg.id: lg.bundle()}
        needed = trade_history.needed_snapshots(bundles, i["snapshot_index"])
        self.assertEqual(set(needed), set(i["snapshots"]))
        now = dt.datetime(2026, 11, 16, 12, tzinfo=dt.timezone.utc)
        quiet = lambda s: None  # noqa: E731
        a = trade_history.build(bundles, lg, values, i["snapshot_index"], i["snapshots"], now, log=quiet)
        b = trade_history.build(bundles, lg, values, i["snapshot_index"], i["snapshots"], now + dt.timedelta(days=10), log=quiet)
        self.assertEqual(len(a["trades"]), 2)
        self.assertEqual([t["id"] for t in a["trades"]], [t["id"] for t in b["trades"]])
        for x, y in zip(a["trades"], b["trades"]):
            self.assertEqual(y["days_ago"] - x["days_ago"], 10)

    def test_trade_history_with_no_completed_trades(self):
        i = synth_league.make_inputs(trades=False)
        lg = League(i["pull"], i["players"], i["state"])
        bundles = {**i["history"], lg.id: lg.bundle()}
        self.assertEqual(trade_history.needed_snapshots(bundles, [["2026-09-01T00:00:00Z", "5a1c0de"]]), {})
        now = dt.datetime(2026, 11, 16, 12, tzinfo=dt.timezone.utc)
        self.assertIsNone(trade_history.build(bundles, lg, Values.from_csv(i["values_csv"], lg.fmt["superflex"]), [], {}, now,
                                              log=lambda s: None))

    def test_fetch_pull_of_a_missing_league(self):
        i = synth_league.make_inputs()
        self.assertIsNone(fetch.league_pull(synth_league.FakeSleeper(i), "L404", i["state"]))


class GradeTest(unittest.TestCase):
    def test_grade_a_team_with_no_metrics_row(self):
        i = synth_league.make_inputs(week=0)   # before the season: no matchups, so no metrics row for any team
        lg = League(i["pull"], i["players"], i["state"])
        g = grade(lg, Values.from_csv(i["values_csv"], lg.fmt["superflex"]), 3, i["benchmark"], lg.bundle())
        self.assertIsNone(g["row"])
        self.assertEqual(g["pct"], {})
        self.assertIn(g["mode"], {"contend", "retool", "rebuild"})

    def test_team_types_calls_a_team_with_no_metrics_row_retool(self):
        i = synth_league.make_inputs()
        lg = League(i["pull"], i["players"], i["state"])
        values = Values.from_csv(i["values_csv"], lg.fmt["superflex"])
        bundle = lg.bundle()
        bundle["matchups"] = {wk: [m for m in ms if m["roster_id"] != 4] for wk, ms in bundle["matchups"].items()}
        self.assertIsNone(grade(lg, values, 4, i["benchmark"], bundle)["row"])
        self.assertIsNotNone(grade(lg, values, 6, i["benchmark"], bundle)["row"])
        types = team_types(lg, values, i["benchmark"], bundle)
        self.assertEqual(types[4], "retool")   # graded on its own it would be a contender
        self.assertEqual(types[6], "contend")
        self.assertEqual(set(types), set(lg.team_name))


class InputsFolderTest(unittest.TestCase):
    def test_round_trip(self):
        i = synth_league.make_inputs()
        with tempfile.TemporaryDirectory() as d:
            inputs.save(i, d, "Team 3")
            loaded, team = inputs.load(d)
        self.assertEqual(team, "Team 3")
        self.assertEqual(json.dumps(loaded, sort_keys=True), json.dumps(i, sort_keys=True))

    def test_missing_file_and_wrong_version(self):
        i = synth_league.make_inputs()
        with tempfile.TemporaryDirectory() as d:
            inputs.save(i, d, "Team 3")
            os.remove(os.path.join(d, "players.json"))
            with self.assertRaisesRegex(ValueError, "is missing players.json"):
                inputs.load(d)
        with tempfile.TemporaryDirectory() as d:
            inputs.save(dict(i, version=2), d, "Team 3")
            with self.assertRaisesRegex(ValueError, "is version 2, expected 1"):
                inputs.load(d)

    def test_benchmark_path_is_not_recorded_and_the_input_is_not_changed(self):
        i = synth_league.make_inputs()
        i["benchmark"] = dict(i["benchmark"], _path="/home/someone/benchmarks/x.json")
        with tempfile.TemporaryDirectory() as d:
            inputs.save(i, d, "Team 3")
            loaded, _ = inputs.load(d)
            on_disk = ""
            for root, _, names in os.walk(d):
                for n in names:
                    with open(os.path.join(root, n), encoding="utf-8") as f:
                        on_disk += f.read()
        self.assertNotIn("_path", loaded["benchmark"])
        self.assertNotIn("/home/someone", on_disk)
        self.assertEqual(i["benchmark"]["_path"], "/home/someone/benchmarks/x.json")
        self.assertEqual({k: v for k, v in i["benchmark"].items() if k != "_path"}, loaded["benchmark"])
        a = engine.build_report(i, "Team 3", log=QUIET)
        b = engine.build_report(loaded, "Team 3", log=QUIET)
        self.assertEqual(json.dumps(a), json.dumps(b))


QUIET = lambda s: None  # noqa: E731


class BuildReportTest(unittest.TestCase):
    def test_same_inputs_give_the_same_report(self):
        a = engine.build_report(synth_league.make_inputs(), "Team 3", log=QUIET)
        b = engine.build_report(synth_league.make_inputs(), "Team 3", log=QUIET)
        self.assertEqual(json.dumps(a), json.dumps(b))
        self.assertEqual(set(a), {"league_id", "roster_id", "summary", "board_data", "brief"})
        self.assertNotIn("api_calls", a["summary"])
        self.assertIn(a["summary"]["mode"], {"contend", "retool", "rebuild"})

    def test_stages_are_filled_and_serialisable(self):
        stages = {}
        engine.build_report(synth_league.make_inputs(), "Team 3", log=QUIET, stages=stages)
        self.assertEqual(set(stages), {"league", "assets", "grade", "ledger", "deals", "three_team_deals", "trade_history"})
        json.dumps(stages)

    def test_no_trades_and_no_snapshot_index(self):
        r = engine.build_report(synth_league.make_inputs(trades=False), "Team 3", log=QUIET)
        self.assertIsNone(r["board_data"]["trade_history"])
        i = synth_league.make_inputs()
        i["snapshot_index"] = None
        self.assertIsNone(engine.build_report(i, "Team 3", log=QUIET)["board_data"]["trade_history"])

    def test_preseason_league(self):
        r = engine.build_report(synth_league.make_inputs(week=0), "Team 3", log=QUIET)
        self.assertEqual(r["summary"]["week"], 0)

    def test_wrong_version_is_refused(self):
        i = synth_league.make_inputs()
        i["version"] = 99
        with self.assertRaisesRegex(ValueError, "version 99"):
            engine.build_report(i, "Team 3")

    def test_engine_imports_without_requests_or_numpy(self):
        code = "import sys; import rebuild.engine; assert 'requests' not in sys.modules and 'numpy' not in sys.modules"
        self.assertEqual(subprocess.run([sys.executable, "-c", code]).returncode, 0)


class GatherTest(unittest.TestCase):
    def gather(self, i, tmp, *extra, index=None):
        args = cli.parse_args(["--league", i["chain"][0], "--team", "Team 3", "--cache-dir", os.path.join(tmp, "cache"),
                               "--out", os.path.join(tmp, "out"), *extra])
        with mock.patch.object(fetch, "values_csv", lambda *a, **k: i["values_csv"]), \
                mock.patch.object(fetch, "snapshot_index", index or (lambda *a, **k: i["snapshot_index"])), \
                mock.patch.object(fetch, "snapshot_csv", lambda cache_dir, sha: i["snapshots"][sha]):
            lines = []
            return cli.gather(synth_league.FakeSleeper(i), args, lines.append), lines

    def test_gathered_inputs_give_the_report_the_inputs_give(self):
        i = synth_league.make_inputs()
        with tempfile.TemporaryDirectory() as tmp:
            g, _ = self.gather(i, tmp)
        self.assertEqual(set(g), set(i))
        for k in ("version", "options", "state", "players", "pull", "chain", "values_csv", "snapshot_index", "snapshots", "benchmark_note"):
            self.assertEqual(g[k], i[k], k)
        self.assertEqual({k: v for k, v in g["benchmark"].items() if k != "_path"}, i["benchmark"])   # find_shipped notes where it found it
        self.assertEqual(set(g["history"]), set(i["history"]))
        g["run_at"] = i["run_at"]
        self.assertEqual(json.dumps(engine.build_report(g, "Team 3", log=QUIET)), json.dumps(engine.build_report(i, "Team 3", log=QUIET)))

    def test_no_history_gathers_only_the_current_league(self):
        i = synth_league.make_inputs()
        with tempfile.TemporaryDirectory() as tmp:
            g, _ = self.gather(i, tmp, "--no-history")
        self.assertEqual((g["chain"], g["history"], g["options"]["history"]), ([i["chain"][0]], {}, False))

    def test_snapshot_index_failure_skips_trade_history(self):
        def down(*a, **k):
            raise OSError("rate limited")
        i = synth_league.make_inputs()
        with tempfile.TemporaryDirectory() as tmp:
            g, lines = self.gather(i, tmp, index=down)
        self.assertIsNone(g["snapshot_index"])
        self.assertIn("trade history skipped: rate limited", lines)


if __name__ == "__main__":
    unittest.main()
