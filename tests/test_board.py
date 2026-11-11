import os
import tempfile
import unittest

from rebuild import board


class RenderTest(unittest.TestCase):
    def test_render_inlines_weights_logic(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "board.html")
            board.render({"league": "L"}, out)
            with open(out, encoding="utf-8") as f:
                html = f.read()
        self.assertIn("function curveValue", html)
        self.assertNotIn("/*__WEIGHTS_JS__*/", html)


if __name__ == "__main__":
    unittest.main()
