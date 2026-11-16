import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from rebuild import web_api
from tests import make_web_fixture

ROOT = make_web_fixture.ROOT
spec = importlib.util.spec_from_file_location("build_data", os.path.join(ROOT, "web", "scripts", "build_data.py"))
build_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_data)

STARTING = {"age", "birth_date", "fantasy_positions", "full_name", "injury_status", "last_name", "position", "team", "years_exp"}


def write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class BuildDataTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.out = os.path.join(self.dir, "data")
        self.players_src = os.path.join(self.dir, "p.json")
        self.index_src = os.path.join(self.dir, "i.json")
        self.players = {f"{1000 + i}": {"player_id": f"{1000 + i}", "position": "WR", "full_name": f"P {i}", "age": 20 + i,
                                        "search_rank": i, "depth_chart_order": 1, "team": "ALP"} for i in range(10)}
        write(self.players_src, self.players)
        write(self.index_src, [["2024-02-01T00:00:00Z", "bbb"], ["2023-01-01T00:00:00Z", "aaa"]])

    def run_main(self):
        argv = ["--out", self.out, "--index-from", self.index_src, "--players-from", self.players_src]
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = build_data.main(argv)
        return code, err.getvalue()

    def test_trimming_keeps_exactly_the_listed_fields_in_order(self):
        rec = {k: 1 for k in ["zzz", *reversed(build_data.PLAYER_FIELDS), "player_id", "search_rank"]}
        got = build_data.trim({"b": rec, "a": {"x": 1}})
        self.assertEqual(list(got), ["b", "a"])
        self.assertEqual(list(got["b"]), list(reversed(build_data.PLAYER_FIELDS)))
        self.assertEqual(got["a"], {})

    def test_the_field_list_has_the_starting_nine_and_no_repeats(self):
        self.assertTrue(STARTING <= set(build_data.PLAYER_FIELDS))
        self.assertEqual(len(build_data.PLAYER_FIELDS), len(set(build_data.PLAYER_FIELDS)))

    def test_writes_compact_trimmed_files_in_original_order(self):
        self.assertEqual(self.run_main()[0], 0)
        text = read_text(os.path.join(self.out, "players.json"))
        self.assertNotIn(" ", text.replace("P ", ""))
        got = json.loads(text)
        self.assertEqual(list(got), list(self.players))
        self.assertEqual(got["1003"], {"position": "WR", "full_name": "P 3", "age": 23, "team": "ALP"})

    def test_the_index_is_sorted_oldest_first(self):
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(json.loads(read_text(os.path.join(self.out, "snapshot_index.json"))),
                         [["2023-01-01T00:00:00Z", "aaa"], ["2024-02-01T00:00:00Z", "bbb"]])

    def test_fewer_than_80_percent_keeps_the_old_file_and_exits_1(self):
        self.assertEqual(self.run_main()[0], 0)
        path = os.path.join(self.out, "players.json")
        before = read_text(path)
        write(self.players_src, dict(list(self.players.items())[:7]))   # 70%
        code, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("fewer than 80%", err)
        self.assertEqual(read_text(path), before)
        write(self.players_src, dict(list(self.players.items())[:8]))   # exactly 80% is accepted
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(len(json.loads(read_text(path))), 8)

    def test_a_failed_download_with_no_old_file_exits_1(self):
        os.remove(self.players_src)
        code, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("download failed", err)
        self.assertFalse(os.path.exists(os.path.join(self.out, "players.json")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "snapshot_index.json")))

    def test_a_failed_download_keeps_the_old_files(self):
        self.assertEqual(self.run_main()[0], 0)
        before = {n: read_text(os.path.join(self.out, n)) for n in os.listdir(self.out)}
        os.remove(self.index_src)
        self.assertEqual(self.run_main()[0], 1)
        self.assertEqual({n: read_text(os.path.join(self.out, n)) for n in os.listdir(self.out)}, before)

    def test_an_empty_table_exits_1(self):
        write(self.players_src, {})
        self.assertEqual(self.run_main()[0], 1)

    def test_the_engine_builds_the_same_report_with_trimmed_players(self):
        folder = make_web_fixture.FIXTURE_DIR
        texts = make_web_fixture.read_responses(folder)
        write(self.players_src, json.loads(texts["players"]))
        write(self.index_src, json.loads(texts["snapshot_index"]))
        self.assertEqual(self.run_main()[0], 0)
        trimmed = read_text(os.path.join(self.out, "players.json"))
        self.assertLess(len(trimmed), len(texts["players"]))
        texts["players"] = trimmed
        meta = json.loads(read_text(os.path.join(folder, "meta.json")))
        old, web_api.BENCHMARK_DIR = web_api.BENCHMARK_DIR, os.path.join(ROOT, "benchmarks")
        try:
            out = json.loads(web_api.build(texts.get, meta["league_id"], meta["team"], meta["run_at"]))
        finally:
            web_api.BENCHMARK_DIR = old
        self.assertTrue(out["ok"], out)
        exp = os.path.join(folder, "expected")
        self.assertEqual(out["report"]["summary"], json.loads(read_text(os.path.join(exp, "summary.json"))))
        self.assertEqual(out["report"]["board_data"], json.loads(read_text(os.path.join(exp, "board-data.json"))))
        self.assertEqual(out["report"]["brief"], read_text(os.path.join(exp, "brief.md")))


if __name__ == "__main__":
    unittest.main()
