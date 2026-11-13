import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import monitor_hazards as mh

class HazardParserTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

    def test_usgs_normalizes_earthquake_and_tsunami_indicator(self):
        payload = {"features":[{"id":"test-quake-1","properties":{
            "mag":6.2,"place":"off the coast of Costa Rica","time":1794484800000,
            "url":"https://earthquake.usgs.gov/test","tsunami":1,"status":"reviewed"},
            "geometry":{"coordinates":[-84.5,9.7,18.0]}}]}
        events = mh.parse_usgs(payload,self.now)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]["type"],"earthquake")
        self.assertEqual(events[0]["severity"],"high")
        self.assertIn("tsunami_indicator",events[0]["tags"])
        self.assertEqual(events[0]["relevance"],"costa_rica")

    def test_nhc_empty_active_storms_is_valid_empty_result(self):
        self.assertEqual(mh.parse_nhc({"activeStorms":[]},self.now),[])

    def test_nhc_storm_normalization(self):
        payload = {"activeStorms":[{"id":"AL012026","name":"Test Storm","classification":"Hurricane",
            "latitude":"18.2","longitude":"-72.1","windSpeed":85,"movement":"NW at 8 mph"}]}
        events = mh.parse_nhc(payload,self.now)
        self.assertEqual(events[0]["type"],"cyclone")
        self.assertEqual(events[0]["severity"],"high")
        self.assertEqual(events[0]["metadata"]["wind_mph"],85)

    def test_gdacs_geojson_normalization(self):
        payload = {"features":[{"id":"gdacs-123","properties":{"eventtype":"FL","eventname":"Flood in test region",
            "alertlevel":"Orange","country":"Costa Rica","fromdate":"2026-11-12T10:00:00Z",
            "url":"https://www.gdacs.org/"},"geometry":{"type":"Point","coordinates":[-84.2,9.8]}}]}
        events = mh.parse_gdacs(payload,self.now)
        self.assertEqual(events[0]["type"],"flood")
        self.assertEqual(events[0]["severity"],"high")
        self.assertEqual(events[0]["relevance"],"costa_rica")

    def test_eonet_wildfire_normalization(self):
        payload = {"events":[{"id":"EONET_1","title":"Test wildfire",
            "categories":[{"id":"wildfires","title":"Wildfires"}],
            "geometry":[{"date":"2026-11-12T10:00:00Z","coordinates":[-84.1,9.9]}],
            "link":"https://eonet.gsfc.nasa.gov/"}]}
        events = mh.parse_eonet(payload,self.now)
        self.assertEqual(events[0]["type"],"wildfire")
        self.assertEqual(events[0]["relevance"],"costa_rica")

    def test_tsunami_information_statement_is_not_a_warning(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <id>bulletin-1</id><title>TSUNAMI INFORMATION STATEMENT - ALEUTIAN ISLANDS</title>
          <updated>2026-11-12T10:00:00Z</updated><summary>No tsunami threat is expected.</summary>
          <link href="https://www.tsunami.gov/" /></entry></feed>"""
        events = mh.parse_tsunami_atom(ET.fromstring(xml),self.now,"PTWC")
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]["severity"],"info")
        self.assertEqual(events[0]["relevance"],"global")

    def test_haversine_zero_distance(self):
        self.assertAlmostEqual(mh.haversine_km(9.9,-84.1,9.9,-84.1),0,places=5)

    def test_swpc_scale_parser(self):
        payload = {"0":{"DateStamp":"2026-11-12","TimeStamp":"12:00:00",
            "G":{"Scale":"2","Text":"moderate"},"R":{"Scale":"0","Text":"none"},"S":{"Scale":"0","Text":"none"}}}
        result = mh.parse_swpc_scales(payload,self.now)
        self.assertEqual(result["current"]["geomagnetic"]["scale"],"2")

if __name__ == "__main__":
    unittest.main(verbosity=2)
