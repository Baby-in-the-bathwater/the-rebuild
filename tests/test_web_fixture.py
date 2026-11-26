import json
import os
import re
import tempfile
import unittest
from urllib.parse import urlparse

from rebuild import web_api
from tests import make_web_fixture

LONG_ID = re.compile(r"(?<![\d.])\d{17,20}(?![\d.])")   # the public-data guard's pattern
HOSTS = {"api.sleeper.app", "raw.githubusercontent.com"}
BENCHMARKS = os.path.join(make_web_fixture.ROOT, "benchmarks")


def read_folder(folder):
    out = {}
    for root, _, names in os.walk(folder):
        for n in names:
            p = os.path.join(root, n)
            with open(p, encoding="utf-8", newline="") as f:
                out[os.path.relpath(p, folder)] = f.read()
    return out


class WebFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        make_web_fixture.build(cls.tmp.name)
        cls.fresh = read_folder(cls.tmp.name)
        cls.committed = read_folder(make_web_fixture.FIXTURE_DIR)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_fresh_build_equals_the_committed_folder(self):
        self.assertEqual(sorted(self.fresh), sorted(self.committed))
        for name in self.fresh:
            self.assertEqual(self.fresh[name], self.committed[name], name)

    def test_http_has_only_the_known_hosts(self):
        http = json.loads(self.committed["http.json"])
        self.assertTrue(http)
        for url in http:
            self.assertIn(urlparse(url).hostname, HOSTS, url)
            self.assertNotIn("api.github.com", url)

    def test_no_value_looks_like_a_sleeper_id(self):
        for name, text in self.committed.items():
            self.assertIsNone(LONG_ID.search(text), name)

    def test_the_fixture_responses_build_the_expected_report(self):
        """What the site's tests do: only http.json, players.json and snapshot_index.json, through `lookup`."""
        texts = make_web_fixture.read_responses(make_web_fixture.FIXTURE_DIR)
        meta = json.loads(self.committed["meta.json"])
        old, web_api.BENCHMARK_DIR = web_api.BENCHMARK_DIR, BENCHMARKS
        try:
            out = json.loads(web_api.build(texts.get, meta["league_id"], meta["team"], meta["run_at"]))
        finally:
            web_api.BENCHMARK_DIR = old
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["report"]["summary"], json.loads(self.committed[os.path.join("expected", "summary.json")]))
        self.assertEqual(out["report"]["board_data"], json.loads(self.committed[os.path.join("expected", "board-data.json")]))
        self.assertEqual(out["report"]["brief"], self.committed[os.path.join("expected", "brief.md")])

    def test_every_url_maps_to_a_lookup_key_and_back(self):
        for url in json.loads(self.committed["http.json"]):
            self.assertEqual(make_web_fixture.url_of(make_web_fixture.key_of(url)), url)
        self.assertEqual(make_web_fixture.key_of(make_web_fixture.fetch.VALUES_URL), "values_csv")
