import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class AssetSanityTests(unittest.TestCase):
    def test_css_braces_are_balanced(self):
        css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
        depth = 0
        for number, line in enumerate(css.split("\n"), 1):
            depth += line.count("{") - line.count("}")
            self.assertGreaterEqual(depth, 0, f"llave de cierre de más en la línea {number}")
        self.assertEqual(depth, 0, "styles.css tiene llaves sin cerrar: rompe todo lo que sigue")


if __name__ == "__main__":
    unittest.main()
