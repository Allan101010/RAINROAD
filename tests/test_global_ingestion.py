import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ingest_global_events.py"
spec = importlib.util.spec_from_file_location("raintrack_global_monitor", MODULE_PATH)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.source = {"provider": "Test Provider", "url": "https://example.test/feed", "kind": "rss"}

    def test_stable_id_is_repeatable(self):
        self.assertEqual(monitor.stable_id("USGS", "abc"), monitor.stable_id("USGS", "abc"))
        self.assertNotEqual(monitor.stable_id("USGS", "abc"), monitor.stable_id("USGS", "xyz"))

    @patch.object(monitor, "fetch_json")
    def test_usgs_geojson_normalization(self, fetch_json):
        fetch_json.return_value = {"features": [{
            "id": "us123", "properties": {"title": "M 4.8 - Test", "time": 1790000000000,
            "updated": 1790000001000, "mag": 4.8, "magType": "mw", "url": "https://earthquake.usgs.gov/event/us123"},
            "geometry": {"coordinates": [-84.1, 10.2, 12.0]}
        }]}
        events = monitor.parse_usgs({"provider": "USGS", "url": "https://example.test/usgs"}, "2026-11-13T00:00:00Z")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["hazard_type"], "earthquake")
        self.assertEqual(event["severity"], "moderate")
        self.assertEqual(event["location"]["latitude"], 10.2)
        self.assertEqual(event["location"]["depth_km"], 12.0)
        self.assertEqual(event["source"]["provider"], "USGS")

    @patch.object(monitor, "fetch_json")
    def test_eonet_array_metrics_are_serializable_scalars(self, fetch_json):
        fetch_json.return_value = {"events": [{
            "id": "EONET_1", "title": "Test fire", "link": "https://eonet.gsfc.nasa.gov/events/1",
            "categories": [{"title": "Wildfires"}],
            "geometry": [{"date": "2026-11-13T00:00:00Z", "type": "Point", "coordinates": [-84.0, 10.0]}]
        }]}
        events = monitor.parse_eonet({"provider": "NASA EONET", "url": "https://example.test/eonet"}, "2026-11-13T00:00:00Z")
        self.assertEqual(events[0]["hazard_type"], "wildfire")
        self.assertEqual(events[0]["metrics"]["categories"], "Wildfires")
        self.assertEqual(events[0]["location"]["longitude"], -84.0)

    @patch.object(monitor, "fetch_text")
    def test_gdacs_rss_does_not_guess_severity(self, fetch_text):
        fetch_text.return_value = """<?xml version="1.0"?><rss><channel><item>
          <title>Red alert: Flood in Example</title><link>https://example.test/event/1</link>
          <guid>event-1</guid><pubDate>Fri, 13 Nov 2026 00:00:00 GMT</pubDate>
          <description>Provider alert</description><georss:point xmlns:georss="http://www.georss.org/georss">10.0 -84.0</georss:point>
        </item></channel></rss>"""
        events = monitor.parse_gdacs_rss(self.source, "2026-11-13T00:05:00Z")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["hazard_type"], "flood")
        self.assertEqual(events[0]["severity"], "unknown")
        self.assertEqual(events[0]["location"]["longitude"], -84.0)

    def test_epoch_milliseconds_are_converted(self):
        self.assertTrue(monitor.iso_from_epoch(1790000000000).endswith("Z"))


if __name__ == "__main__":
    unittest.main()
