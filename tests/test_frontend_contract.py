import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class FrontendContractTests(unittest.TestCase):
    def test_hazard_center_required_controls_exist_once(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        required = [
            "hazardCenter", "hazardFeedStatus", "hazardStats", "hazardTotalCount",
            "hazardRegionalCount", "hazardHighCount", "hazardSourcesCount",
            "spaceWeatherCard", "spaceWeatherScales", "hazardFilters",
            "hazardEventList", "hazardSourceList", "hazardUpdatedAt",
            "enableHazardNotifications", "refreshHazardsBtn", "hazardMapNote"
        ]
        for element_id in required:
            with self.subTest(element_id=element_id):
                self.assertEqual(html.count('id="' + element_id + '"'), 1)

    def test_inline_script_tags_are_balanced(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"<script(?:\s[^>]*)?>", html, re.I)),
                         len(re.findall(r"</script\s*>", html, re.I)))

    def test_private_home_coordinates_are_not_in_current_html(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("10.102970", html)
        self.assertNotIn("-84.264296", html)
        self.assertNotIn("Casa · Santa Rosa de Poás", html)
        self.assertIn("ROUTE_HOME_STORAGE_KEY", html)

    def test_version_and_hazard_snapshot_schema(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        snapshot = json.loads((ROOT / "hazards.json").read_text(encoding="utf-8"))
        self.assertIn("v2.0.0", html)
        self.assertEqual(snapshot.get("schema_version"), 1)
        self.assertIsInstance(snapshot.get("events"), list)
        self.assertIsInstance(snapshot.get("sources"), list)

if __name__ == "__main__":
    unittest.main(verbosity=2)
