import os
import tempfile
import unittest
from types import SimpleNamespace

from rebuild import board, grade, trades


class RenderTest(unittest.TestCase):
    def test_render_inlines_weights_logic(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "board.html")
            board.render({"league": "L"}, out)
            with open(out, encoding="utf-8") as f:
                html = f.read()
        self.assertIn("function curveValue", html)
        self.assertNotIn("/*__WEIGHTS_JS__*/", html)


class TeamTypesTest(unittest.TestCase):
    def test_team_types_falls_back(self):
        league = SimpleNamespace(team_name={1: "a", 2: "b"})

        def fn(league_, values, rid, bm, own_bundle):
            if rid == 2:
                raise KeyError("no history row")
            return {"mode": "contend"}

        self.assertEqual(grade.team_types(league, None, None, None, grade_fn=fn), {1: "contend", 2: "retool"})


class BridgeFitsTest(unittest.TestCase):
    """What a third team will take from the buyer, by its grade (v1.2.1)."""

    @staticmethod
    def p(pos, age, value=3000, startable=True):
        return {"pos": pos, "age": age, "value": value, "startable": startable}

    def test_rebuild_takes_nothing_its_own_ledger_would_sell(self):
        fits = trades.bridge_fits
        self.assertFalse(fits(self.p("TE", 33), "rebuild", ["TE", "QB"]))                 # Kittle, even into a hole
        self.assertFalse(fits(self.p("TE", 26), "rebuild", ["TE"]))                       # producing two years before the turn
        self.assertTrue(fits(self.p("TE", 26, startable=False), "rebuild", ["TE"]))       # not producing yet: a hold
        self.assertTrue(fits(self.p("TE", 24), "rebuild", ["TE"]))
        self.assertFalse(fits(self.p("TE", 33, value=500), "rebuild", ["TE"]))            # too cheap to sell, still too old
        self.assertFalse(fits(self.p("WR", None), "rebuild", ["WR"]))                     # unknown age counts as old

    def test_retool_takes_a_veteran_only_into_a_hole(self):
        fits = trades.bridge_fits
        self.assertTrue(fits(self.p("RB", 25), "retool", ["RB", "WR"]))
        self.assertFalse(fits(self.p("RB", 25), "retool", ["WR", "QB"]))
        self.assertFalse(fits(self.p("RB", 26), "retool", ["RB"]))                        # retool sells a year past the turn
        self.assertTrue(fits(self.p("RB", 23), "retool", []))

    def test_contender_and_ungraded_take_anyone(self):
        self.assertTrue(trades.bridge_fits(self.p("QB", 36), "contend", []))
        self.assertTrue(trades.bridge_fits(self.p("QB", 36), None, []))

    def test_retool_keeps_its_own_next_first_and_core(self):
        league = SimpleNamespace(pick_seasons=["2027", "2028"])
        players = [dict(self.p("WR", 22, value=9000 - k * 100), id=f"p{k}") for k in range(9)]
        picks = [{"key": "own27", "round": 1, "own": True, "season": "2027"},
                 {"key": "via27", "round": 1, "own": False, "season": "2027"},
                 {"key": "own28", "round": 1, "own": True, "season": "2028"}]
        items = ([{"kind": "pick", "key": pk["key"]} for pk in picks]
                 + [{"kind": "player", "id": p["id"]} for p in players])
        left = trades.retool_spendable({"players": players, "picks": picks}, items, league)
        self.assertEqual({i.get("key") or i.get("id") for i in left}, {"via27", "own28", "p8"})

    def test_ledger_rule_matches_the_sell_list(self):
        team = {"players": [dict(self.p("RB", 24), id="a", name="a", ppg=10, ir=False, years_exp=3),
                            dict(self.p("WR", 25), id="b", name="b", ppg=10, ir=False, years_exp=3),
                            dict(self.p("QB", 26), id="c", name="c", ppg=10, ir=False, years_exp=3)]}
        sold = {p["id"] for p in trades.classify_assets(team, "rebuild", None)["sell"]}
        self.assertEqual(sold, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
