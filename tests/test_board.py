import os
import tempfile
import unittest
from types import SimpleNamespace

from rebuild import board, grade


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


if __name__ == "__main__":
    unittest.main()
