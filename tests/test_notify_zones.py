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


class GroupingTests(unittest.TestCase):
    CFG = {"server": "https://ntfy.test", "zones": [
        {"id": "a", "name": "Alajuela", "topic": "t-a", "places": [], "station_ids": ["s1", "s2", "s3"]}]}

    def test_many_stations_make_one_message(self):
        s = FakeSession()
        sent = nz.notify_new_rain([alert("s1", 0.2), alert("s2", 3.0), alert("s3", 1.0)], [], s, self.CFG)
        self.assertEqual(sent, 1)
        body = s.posts[0][1]
        self.assertEqual(body["title"], "🌧️ Lluvia en Alajuela")  # la más intensa (3 mm/h) define el título
        self.assertLess(body["message"].index("s2"), body["message"].index("s3"))
        self.assertLessEqual(len(body["message"].splitlines()), 3)

    def test_cooldown_blocks_second_alert_then_allows_later(self):
        from datetime import datetime, timedelta, timezone
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        s, state = FakeSession(), {}
        self.assertEqual(nz.notify_new_rain([alert("s1")], [], s, self.CFG, state, t0), 1)
        self.assertEqual(nz.notify_new_rain([alert("s2")], [], s, self.CFG, state, t0 + timedelta(minutes=10)), 0)
        self.assertEqual(nz.notify_new_rain([alert("s2")], [], s, self.CFG, state, t0 + timedelta(minutes=60)), 1)


class FormatTests(unittest.TestCase):
    ZONE = {"id": "a", "name": "Alajuela", "topic": "t-a", "places": [], "station_ids": []}

    def test_intensity_levels_and_extra_stations(self):
        msg = nz.build_message(self.ZONE, [alert("s1", 9.0), alert("s2", 5.0), alert("s3", 2.0), alert("s4", 0.5), alert("s5", 0.3)])
        self.assertEqual(msg["title"], "🌧️ Tormenta en Alajuela")
        self.assertEqual(msg["priority"], 4)
        self.assertEqual(msg["message"].splitlines(), ["🔴 Estación s1 · 9 mm/h", "🟡 Estación s2 · 5 mm/h", "🟢 Estación s3 · 2 mm/h", "+2 estaciones más"])

    def test_station_prefix_removed_and_missing_amount(self):
        a = {"station_id": "x", "station_name": "Estación IMN · Fabio Baudrit", "rain_last_hour_mm": None}
        msg = nz.build_message(self.ZONE, a)
        self.assertEqual(msg["message"], "🔵 Fabio Baudrit · lluvia medida")


class NotifyTests(unittest.TestCase):
    def test_only_new_rain_is_sent_to_its_zone(self):
        s = FakeSession()
        sent = nz.notify_new_rain([alert("s1"), alert("s2"), alert("other")], [alert("s2")], s, CONFIG)
        self.assertEqual(sent, 1)
        url, body = s.posts[0]
        self.assertEqual(url, "https://ntfy.test")
        self.assertEqual(body["topic"], "t-a")
        self.assertEqual(body["message"], "🔵 Estación s1 · 0.8 mm/h")
        self.assertEqual(body["title"], "🌧️ Llovizna en Alajuela")
        self.assertEqual(body["click"], nz.APP_URL)
        self.assertEqual(body["actions"][0]["label"], "Ver mapa")

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
