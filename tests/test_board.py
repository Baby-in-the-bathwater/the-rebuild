import json
import os
import re
import tempfile
import unittest
from html.parser import HTMLParser
from types import SimpleNamespace

from rebuild import board, grade, trades


class RenderTest(unittest.TestCase):
    PLACEHOLDERS = ("__TITLE__", "__CSS__", "__BODY__", "__DATA__", "__WEIGHTS_JS__", "__BOARD_JS__")

    def render(self, data):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "board.html")
            board.render(data, out)
            with open(out, encoding="utf-8") as f:
                return f.read()

    def test_render_inlines_weights_logic(self):
        html = self.render({"league": "L"})
        self.assertIn("function curveValue", html)

    def test_render_inlines_every_part(self):
        html = self.render({"league": "L"})
        parts = board.sources()
        self.assertEqual(set(parts), {"css", "body", "weights_js", "board_js"})
        for name, text in parts.items():
            self.assertTrue(text.strip(), name)
            self.assertIn(text, html, name)
        self.assertIn("<title>L Trade Board</title>", html)

    def test_board_script_reads_data_from_the_window(self):
        js = board.sources()["board_js"]
        self.assertTrue(js.startswith("const DATA = window.__BOARD_DATA__;\n"))
        self.assertIn('"rebuild-board-" + DATA.league_id', js)

    def test_data_is_assigned_once_and_parses_back(self):
        data = {"league": "L", "teams": [{"name": "Zed's \u2603 </script><b>"}], "n": 1.5}
        html = self.render(data)
        marker = "window.__BOARD_DATA__ = "
        self.assertEqual(html.count(marker), 1)
        start = html.index(marker) + len(marker)
        end = html.index(";\n</script>", start)
        self.assertEqual(json.loads(html[start:end]), data)

    def test_script_in_a_team_name_does_not_close_the_script_element(self):
        html = self.render({"league": "L", "teams": [{"name": "</script><img src=x>"}]})
        self.assertNotIn("</script><img", html)
        self.assertEqual(html.count("<script"), html.count("</script>"))
        self.assertEqual(html.count("<script"), 3)

    def test_markup_in_names_reaches_the_page_only_as_script_data(self):
        """A team, league or owner name with markup must not become an element in the file the CLI writes. The
        names travel only inside the data script (where they are text); board.js escapes them when it draws."""
        hostile = '<img src=x onerror="window.__xss=1"> a & b <i>c</i>'
        html = self.render({"league": hostile, "teams": [{"name": hostile, "owner": hostile}]})
        tags = []

        class Tags(HTMLParser):
            def handle_starttag(self, tag, attrs):
                tags.append(tag)

        Tags().feed(html)
        self.assertNotIn("img", tags)
        self.assertEqual(tags.count("i"), board.sources()["body"].count("<i "))   # the legend's swatches only
        outside = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
        self.assertNotIn("<img src=x", outside)
        self.assertIn("&lt;img src=x", outside)   # the title, escaped
        self.assertIn("esc(team.name)", board.sources()["board_js"])

    def test_comment_opener_in_a_team_name_round_trips_and_keeps_the_scripts_intact(self):
        data = {"league": "L", "teams": [{"name": "<!--<script>"}]}
        html = self.render(data)
        self.assertNotIn("<!--<script>", html)
        start = html.index("window.__BOARD_DATA__ = ") + len("window.__BOARD_DATA__ = ")
        end = html.index(";\n</script>", start)
        self.assertEqual(json.loads(html[start:end]), data)
        # the same page with the data removed: the script elements are the template's own, no more
        outside = html[:start] + html[end:]
        self.assertEqual(outside.count("<script"), 3)
        self.assertEqual(outside.count("</script>"), 3)
        self.assertEqual(html.count("</script>"), 3)

    def test_league_name_cannot_break_out_of_the_title(self):
        html = self.render({"league": "</title><b>x</b>"})
        head = html[:html.index("</head>")]
        self.assertNotIn("<b>", head)
        self.assertEqual(head.count("</title>"), 1)
        self.assertIn("<title>&lt;/title&gt;&lt;b&gt;x&lt;/b&gt; Trade Board</title>", head)

    def test_no_placeholder_is_left(self):
        html = self.render({"league": "L"})
        for ph in self.PLACEHOLDERS:
            self.assertNotIn(ph, html)

    def test_placeholder_text_in_data_is_kept_as_data(self):
        html = self.render({"league": "L", "teams": [{"name": "__CSS__"}]})
        self.assertIn('"name": "__CSS__"', html)

    def test_file_references_nothing_local(self):
        html = self.render({"league": "L"})
        urls = re.findall(r'(?:href|src)\s*=\s*["\']([^"\']+)', html)
        self.assertTrue(urls)
        for u in urls:
            self.assertTrue(u.startswith("https://fonts.googleapis.com/"), u)
        self.assertNotIn("@import", html)
        self.assertNotRegex(html, r"url\(\s*[\"']?(?!data:|#)")


class TeamTypesTest(unittest.TestCase):
    def test_team_types_falls_back(self):
        league = SimpleNamespace(team_name={1: "a", 2: "b"})

        def fn(league_, values, rid, bm, own_bundle):
            if rid == 2:
                raise KeyError("no history row")
            return {"mode": "contend", "row": {}}

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

    def test_contender_takes_nobody_out_for_weeks(self):
        self.assertFalse(trades.bridge_fits(dict(self.p("QB", 29), out=True), "contend", []))
        self.assertTrue(trades.bridge_fits(dict(self.p("QB", 29), out=False), "contend", []))

    def test_ledger_rule_matches_the_sell_list(self):
        team = {"players": [dict(self.p("RB", 24), id="a", name="a", ppg=10, ir=False, years_exp=3),
                            dict(self.p("WR", 25), id="b", name="b", ppg=10, ir=False, years_exp=3),
                            dict(self.p("QB", 26), id="c", name="c", ppg=10, ir=False, years_exp=3)]}
        sold = {p["id"] for p in trades.classify_assets(team, "rebuild", None)["sell"]}
        self.assertEqual(sold, {"a", "b"})


class InjuredSellTest(unittest.TestCase):
    """A sell asset out for weeks goes to retooling teams before the deadline (v1.3.0)."""

    def test_out_now_only_in_season_before_the_deadline(self):
        lamar = {"out": True}
        live = SimpleNamespace(status="in_season", trade_deadline=14, week=10)
        self.assertTrue(trades.out_now(lamar, live))
        self.assertFalse(trades.out_now({"out": False}, live))
        self.assertFalse(trades.out_now(lamar, SimpleNamespace(status="in_season", trade_deadline=14, week=14 + 1)))
        self.assertFalse(trades.out_now(lamar, SimpleNamespace(status="complete", trade_deadline=14, week=14)))
        self.assertTrue(trades.out_now(lamar, SimpleNamespace(status="in_season", trade_deadline=None, week=12)))

    def test_retool_buyers_are_retool_teams_at_any_rank(self):
        def team(rid, rank):
            return {"rid": rid, "rank": rank, "firsts": {}, "players": []}
        g = {"n": 4, "team": team(1, 4), "rows": [],
             "teams": {1: team(1, 4), 2: team(2, 1), 3: team(3, 3), 4: team(4, 2)}}
        types = {1: "retool", 2: "contend", 3: "retool", 4: "retool"}
        self.assertEqual([t["rid"] for t, _ in trades.retool_buyers(g, types)], [4, 3])


if __name__ == "__main__":
    unittest.main()
