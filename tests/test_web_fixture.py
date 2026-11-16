import json
import os
import re
import tempfile
import unittest
from urllib.parse import urlparse

from tests import make_web_fixture

LONG_ID = re.compile(r"(?<![\d.])\d{17,20}(?![\d.])")   # the public-data guard's pattern
HOSTS = {"api.sleeper.app", "raw.githubusercontent.com"}


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
