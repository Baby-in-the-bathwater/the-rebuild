import datetime as dt
import json
import re
import subprocess
import sys
import unittest

from rebuild import fetch, trade_history
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


if __name__ == "__main__":
    unittest.main()
