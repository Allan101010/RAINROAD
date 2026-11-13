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

    @patch.object(monitor, "fetch_json")
    def test_swpc_alert_parses_g_scale_and_timestamp(self, fetch_json):
        fetch_json.return_value = [{
            "product_id": "ALERT-1",
            "issue_datetime": "2026 Nov 13 0600 UTC",
            "message": "Geomagnetic Storm G3 Watch\\nWATCH: Geomagnetic storm level G3"
        }]
        source = {"provider": "NOAA SWPC", "url": "https://example.test/alerts.json"}
        rows = monitor.parse_swpc_alerts(source, "2026-11-13T06:05:00Z")
        self.assertEqual(rows[0]["hazard_type"], "geomagnetic_storm")
        self.assertEqual(rows[0]["severity"], "severe")
        self.assertEqual(rows[0]["status"], "active")
        self.assertEqual(rows[0]["observed_at"], "2026-11-13T06:00:00Z")

    @patch.object(monitor, "fetch_json")
    def test_old_swpc_alert_is_not_marked_active(self, fetch_json):
        fetch_json.return_value = [{
            "product_id": "ALERT-OLD",
            "issue_datetime": "2026 Nov 10 0600 UTC",
            "message": "Solar flare report"
        }]
        source = {"provider": "NOAA SWPC", "url": "https://example.test/alerts.json"}
        rows = monitor.parse_swpc_alerts(source, "2026-11-13T06:05:00Z")
        self.assertEqual(rows[0]["status"], "resolved")

    @patch.object(monitor, "fetch_json")
    def test_swpc_naive_iso_timestamp_is_normalized_and_stale(self, fetch_json):
        fetch_json.return_value = [{
            "product_id": "K06A",
            "issue_datetime": "2026-11-05 18:57:32.737",
            "message": "ALERT: Geomagnetic K-index of 6"
        }]
        source = {"provider": "NOAA SWPC", "url": "https://example.test/alerts.json"}
        rows = monitor.parse_swpc_alerts(source, "2026-11-13T06:05:00Z")
        self.assertEqual(rows[0]["observed_at"], "2026-11-05T18:57:32.737000Z")
        self.assertEqual(rows[0]["status"], "resolved")
        self.assertEqual(rows[0]["severity"], "moderate")


    @patch.object(monitor, "fetch_text")
    def test_imn_cap_preserves_severity_area_and_expiry(self, fetch_text):
        fetch_text.return_value = """<?xml version="1.0"?>
        <rss><channel><item>
          <title>Aviso por lluvias fuertes en Costa Rica</title>
          <link>https://imn.ac.cr/aviso/123</link><guid>urn:imn:123</guid>
          <cap:alert xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
            <cap:identifier>urn:imn:123</cap:identifier><cap:sent>2026-11-13T06:00:00-06:00</cap:sent>
            <cap:status>Actual</cap:status><cap:msgType>Alert</cap:msgType>
            <cap:info><cap:event>Heavy Rain</cap:event><cap:severity>Severe</cap:severity>
              <cap:urgency>Immediate</cap:urgency><cap:certainty>Likely</cap:certainty>
              <cap:description>Lluvias fuertes en sectores vulnerables.</cap:description>
              <cap:expires>2026-11-13T14:00:00-06:00</cap:expires>
              <cap:area><cap:areaDesc>Alajuela</cap:areaDesc><cap:polygon>10.0,-84.2 10.2,-84.0 10.1,-83.9</cap:polygon></cap:area>
            </cap:info>
          </cap:alert>
        </item></channel></rss>"""
        rows = monitor.parse_imn_cap_rss({"provider": "IMN", "url": "https://example.test/cap.xml"}, "2026-11-13T12:00:00Z")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hazard_type"], "severe_storm")
        self.assertEqual(rows[0]["severity"], "severe")
        self.assertEqual(rows[0]["status"], "active")
        self.assertEqual(rows[0]["metrics"]["urgency"], "Immediate")
        self.assertEqual(rows[0]["location"]["country_code"], "CR")
        self.assertEqual(rows[0]["expires_at"], "2026-11-13T20:00:00Z")

    @patch.object(monitor, "fetch_text")
    def test_imn_cap_expired_alert_is_resolved(self, fetch_text):
        fetch_text.return_value = """<rss><channel><item>
          <title>Aviso anterior</title><link>https://imn.ac.cr/old</link>
          <cap:alert xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
            <cap:identifier>old</cap:identifier><cap:sent>2026-11-10T06:00:00Z</cap:sent>
            <cap:status>Actual</cap:status><cap:msgType>Alert</cap:msgType>
            <cap:info><cap:event>Rain</cap:event><cap:severity>Moderate</cap:severity>
              <cap:expires>2026-11-11T06:00:00Z</cap:expires>
            </cap:info>
          </cap:alert></item></channel></rss>"""
        rows = monitor.parse_imn_cap_rss({"provider": "IMN", "url": "https://example.test/cap.xml"}, "2026-11-13T12:00:00Z")
        self.assertEqual(rows[0]["status"], "resolved")

    def test_spanish_feed_mojibake_is_repaired(self):
        self.assertEqual(monitor.repair_mojibake("PacÃ­fico Oriental"), "Pacífico Oriental")
        self.assertEqual(monitor.repair_mojibake("Texto normal"), "Texto normal")

    def test_epoch_milliseconds_are_converted(self):
        self.assertTrue(monitor.iso_from_epoch(1790000000000).endswith("Z"))


if __name__ == "__main__":
    unittest.main()
