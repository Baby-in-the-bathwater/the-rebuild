import json
import re
import unittest

from tests import synth_league


class SynthTest(unittest.TestCase):
    def test_inputs_are_stable_and_public_safe(self):
        a, b = synth_league.make_inputs(), synth_league.make_inputs()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertIsNone(re.search(r"(?<![\d.])\d{17,20}(?![\d.])", json.dumps(a)))
        self.assertEqual(a["version"], 1)
        self.assertEqual(a["chain"][0], a["pull"]["league"]["league_id"])


if __name__ == "__main__":
    unittest.main()
