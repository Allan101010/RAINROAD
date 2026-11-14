import json
import unittest
from pathlib import Path

import requests

from scripts import notify_zones as nz

CONFIG = {"server": "https://ntfy.test", "zones": [
    {"id": "a", "name": "Alajuela", "topic": "t-a", "places": ["Río Segundo"], "station_ids": ["s1"]},
    {"id": "b", "name": "San José", "topic": "t-b", "places": [], "station_ids": ["s2"]},
]}


def alert(station_id, mm=0.8):
    return {"station_id": station_id, "station_name": "Estación " + station_id,
            "rain_last_hour_mm": mm, "page_url": "https://imn.test/" + station_id}


class FakeSession:
    def __init__(self, fail=False):
        self.posts, self.fail = [], fail

    def post(self, url, data, timeout):
        if self.fail:
            raise requests.ConnectionError("sin red")
        self.posts.append((url, json.loads(data.decode("utf-8"))))
        return type("R", (), {"raise_for_status": lambda self: None})()


class NotifyTests(unittest.TestCase):
    def test_only_new_rain_is_sent_to_its_zone(self):
        s = FakeSession()
        sent = nz.notify_new_rain([alert("s1"), alert("s2"), alert("other")], [alert("s2")], s, CONFIG)
        self.assertEqual(sent, 1)
        url, body = s.posts[0]
        self.assertEqual(url, "https://ntfy.test")
        self.assertEqual(body["topic"], "t-a")
        self.assertIn("0.8 mm", body["message"])
        self.assertIn("Río Segundo", body["message"])
        self.assertEqual(body["title"], "Lluvia en Alajuela")

    def test_continuous_rain_does_not_repeat(self):
        s = FakeSession()
        self.assertEqual(nz.notify_new_rain([alert("s1")], [alert("s1")], s, CONFIG), 0)
        self.assertEqual(s.posts, [])

    def test_network_failure_never_raises(self):
        self.assertEqual(nz.notify_new_rain([alert("s1")], [], FakeSession(fail=True), CONFIG), 0)

    def test_no_config_sends_nothing(self):
        s = FakeSession()
        self.assertEqual(nz.notify_new_rain([alert("s1")], [], s, {"server": "", "zones": []}), 0)

    def test_real_config_zones_reference_known_stations_and_unique_topics(self):
        cfg = nz.load_zones()
        root = Path(__file__).resolve().parent.parent
        ids = {x["id"] for x in json.loads((root / "config" / "camera-sources.json").read_text("utf-8"))["imn_stations"]}
        topics = [z["topic"] for z in cfg["zones"]]
        self.assertEqual(len(topics), len(set(topics)))
        for zone in cfg["zones"]:
            self.assertGreaterEqual(len(zone["topic"]), 24)
            self.assertTrue(set(zone["station_ids"]) <= ids)


if __name__ == "__main__":
    unittest.main()
