import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quakes  # noqa: E402

NOW = datetime(2026, 11, 15, 1, 0, tzinfo=timezone.utc).timestamp()


def usgs(mag, lat, lon, depth, place, seconds_ago, kind="earthquake"):
    return {"type": "Feature", "properties": {"mag": mag, "place": place, "time": int((NOW - seconds_ago) * 1000), "type": kind},
            "geometry": {"type": "Point", "coordinates": [lon, lat, depth]}}


def emsc(mag, lat, lon, depth, region, seconds_ago):
    when = datetime.fromtimestamp(NOW - seconds_ago, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0Z")
    return {"type": "Feature", "properties": {"time": when, "mag": mag, "lat": lat, "lon": lon, "depth": depth,
                                              "flynn_region": region, "unid": "x"},
            "geometry": {"type": "Point", "coordinates": [lon, lat, -depth * 1000]}}


def ovs_marker(mag, lat, lon, when, place, depth=10):
    return ("var eq1 = L.icon({ iconUrl:'x.png' }); L.marker([%s,%s],{icon: eq1}).bindPopup('<div><table> <col width=\"80\"><tr bgcolor=#DEDEEF>"
            "<td width=50>Magnitud:</td> <td width=100>%s</td></tr><tr><td width=90>Fecha y Hora Local:</td> <td>%s</td></tr>"
            "<tr bgcolor=#DEDEEF><td width=90>Ubicacion:</td> <td>%s</td></tr><tr><td width=90>Prof. [km]:</td> <td>%s</td></tr>"
            "</table></div>',{minWidth:300}).addTo(eq);" % (lat, lon, mag, when, place, depth))


class OvsicoriTests(unittest.TestCase):
    def test_parse_reads_local_time_and_filters(self):
        page = "<script>" + ovs_marker("4.7", 8.3982, -83.0541, "2026-11-14 21:01:40", "2.7 km al Sureste de Pavon de Puntarenas") \
            + ovs_marker("2.2", 9.5, -84.6, "2026-11-14 21:00:00", "chico") \
            + ovs_marker("5.0", 35.0, 139.0, "2026-11-14 21:00:00", "lejos") + "</script>"
        events = quakes.parse_ovsicori(page)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["src"], "ovsicori")
        self.assertEqual(events[0]["mag"], 4.7)
        self.assertEqual(events[0]["depth"], 10.0)
        # 21:01:40 hora de Costa Rica = 03:01:40 UTC del día siguiente
        self.assertEqual(datetime.fromtimestamp(events[0]["t"], tz=timezone.utc), datetime(2026, 11, 15, 3, 1, 40, tzinfo=timezone.utc))

    def test_parse_survives_garbage(self):
        self.assertEqual(quakes.parse_ovsicori("<html>nada</html>"), [])
        self.assertEqual(quakes.parse_ovsicori(None), [])

    def test_ovsicori_magnitude_and_place_win_when_merged(self):
        store = []
        t = NOW - 300
        quakes.merge_into(store, [{"src": "emsc", "t": t + 5, "lat": 8.4, "lon": -83.0, "mag": 4.4, "depth": 8.0, "place": "Costa Rica"}], NOW)
        quakes.merge_into(store, [{"src": "ovsicori", "t": t, "lat": 8.3982, "lon": -83.0541, "mag": 4.7, "depth": 10.0,
                                   "place": "2.7 km al Sureste de Pavon de Puntarenas"}], NOW)
        self.assertEqual(len(store), 1)
        self.assertEqual(store[0]["mag"], 4.7)
        self.assertIn("Pavon", store[0]["place"])
        self.assertEqual(store[0]["t"], t)
        self.assertTrue(store[0]["cr"])


class CoherenceTests(unittest.TestCase):
    def test_low_reading_from_one_source_still_matches_the_other(self):
        store = []
        t = NOW - 300
        quakes.merge_into(store, [{"src": "ovsicori", "t": t, "lat": 8.47, "lon": -83.09, "mag": 3.4, "depth": 4.0, "place": "Pavon"}], NOW)
        quakes.merge_into(store, [{"src": "emsc", "t": t + 1, "lat": 8.5, "lon": -83.0, "mag": 3.5, "depth": 10.0, "place": "Costa Rica"}], NOW)
        store = quakes.prune(store, NOW)
        self.assertEqual(len(store), 1)
        self.assertEqual(store[0]["mag"], 3.4)          # manda el OVSICORI
        self.assertEqual(quakes.build_payload(store, {})["quakes"], [])  # bajo 3.5: no se publica

    def test_places_in_spanish_and_accents(self):
        self.assertEqual(quakes.spanish_place("12 km NNE of Jacó, Costa Rica"), "12 km al Nor-noreste de Jacó, Costa Rica")
        self.assertEqual(quakes.spanish_place("South Of Panama"), "Sur de Panamá")
        self.assertFalse(quakes.is_costa_rica({"place": "Sur de Panamá", "lat": 8.5, "lon": -82.9}))


class ParseTests(unittest.TestCase):
    def test_usgs_filters_magnitude_region_and_type(self):
        data = {"features": [
            usgs(4.2, 9.9, -84.0, 15.0, "5 km N of San José, Costa Rica", 120),
            usgs(2.9, 9.9, -84.0, 15.0, "pequeño", 120),            # muy débil
            usgs(5.5, 35.0, 139.0, 10.0, "Japón", 120),             # fuera de la región
            usgs(4.0, 9.9, -84.0, 1.0, "explosión", 120, kind="quarry blast"),
            {"properties": {"mag": None}, "geometry": {"coordinates": [1, 2, 3]}},
            {"broken": True},
        ]}
        events = quakes.parse_usgs(data)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["src"], "usgs")
        self.assertAlmostEqual(events[0]["t"], NOW - 120, places=0)

    def test_emsc_parses_region_depth_and_time(self):
        events = quakes.parse_emsc({"features": [emsc(4.3, 9.95, -84.05, 14.0, "COSTA RICA", 100), {"x": 1}]})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["place"], "Costa Rica")
        self.assertEqual(events[0]["depth"], 14.0)
        self.assertAlmostEqual(events[0]["t"], NOW - 100, places=0)


class MergeTests(unittest.TestCase):
    def test_same_quake_from_two_sources_becomes_one(self):
        store = []
        quakes.merge_into(store, quakes.parse_usgs({"features": [usgs(4.2, 9.90, -84.00, 15, "5 km N of Alajuela, Costa Rica", 130)]}), NOW)
        quakes.merge_into(store, quakes.parse_emsc({"features": [emsc(4.4, 9.93, -84.03, 12, "COSTA RICA", 126)]}), NOW)
        self.assertEqual(len(store), 1)
        self.assertEqual(store[0]["src"], ["emsc", "usgs"])
        self.assertEqual(store[0]["mag"], 4.3)
        self.assertTrue(store[0]["cr"])
        self.assertIn("Alajuela", store[0]["place"])

    def test_different_quakes_stay_separate_and_revision_updates(self):
        store = []
        quakes.merge_into(store, quakes.parse_usgs({"features": [usgs(4.0, 9.9, -84.0, 15, "a, Costa Rica", 600)]}), NOW)
        quakes.merge_into(store, quakes.parse_usgs({"features": [usgs(4.1, 9.9, -84.0, 15, "a, Costa Rica", 60)]}), NOW)
        self.assertEqual(len(store), 2)
        again = quakes.parse_usgs({"features": [usgs(4.4, 9.9, -84.0, 15, "a, Costa Rica", 60)]})
        self.assertTrue(quakes.merge_into(store, again, NOW))
        self.assertEqual(len(store), 2)
        self.assertEqual(max(e["mag"] for e in store), 4.4)

    def test_costa_rica_flag(self):
        base = {"lat": 10.0, "lon": -84.0}
        self.assertTrue(quakes.is_costa_rica({**base, "place": "Costa Rica"}))
        self.assertFalse(quakes.is_costa_rica({**base, "place": "30 km W of Chinandega, Nicaragua"}))
        self.assertTrue(quakes.is_costa_rica({**base, "place": "Pacific coast"}))
        self.assertFalse(quakes.is_costa_rica({"lat": 12.5, "lon": -87.0, "place": ""}))

    def test_prune_drops_old_and_sorts_newest_first(self):
        store = [{"t": NOW - 49 * 3600, "mag": 5.0}, {"t": NOW - 3600, "mag": 4.0}, {"t": NOW - 60, "mag": 3.6}]
        kept = quakes.prune(store, NOW)
        self.assertEqual([e["mag"] for e in kept], [3.6, 4.0])


class AlertTests(unittest.TestCase):
    def event(self, mag, cr=True, age=300, notified=False):
        return {"t": NOW - age, "mag": mag, "cr": cr, "place": "Quepos, Costa Rica", "depth": 20.0,
                "src": ["usgs"], "notified": notified}

    def test_thresholds(self):
        self.assertFalse(quakes.should_alert(self.event(3.8), NOW))
        self.assertTrue(quakes.should_alert(self.event(4.0), NOW))
        self.assertFalse(quakes.should_alert(self.event(4.6, cr=False), NOW))
        self.assertTrue(quakes.should_alert(self.event(5.1, cr=False), NOW))
        self.assertFalse(quakes.should_alert(self.event(5.0, age=3 * 3600), NOW))
        self.assertFalse(quakes.should_alert(self.event(5.0, notified=True), NOW))

    def test_costa_rica_message_is_dramatic_and_honest(self):
        message = quakes.alert_message(self.event(5.2), NOW)
        self.assertIn("TEMBLOR EN COSTA RICA", message["title"])
        self.assertEqual(message["priority"], 4)
        self.assertIn("no es una alerta temprana", message["message"])
        calm = quakes.alert_message(self.event(5.4, cr=False), NOW)
        self.assertNotIn("TEMBLOR", calm["title"])

    def test_sends_once_and_marks_only_on_success(self):
        session = MagicMock()
        store = [self.event(4.5), self.event(3.7)]
        self.assertEqual(quakes.send_alerts(store, session, "topic-x", NOW), 1)
        self.assertTrue(store[0]["notified"])
        self.assertFalse(store[1].get("notified"))
        self.assertEqual(quakes.send_alerts(store, session, "topic-x", NOW), 0)
        failing = MagicMock()
        failing.post.side_effect = quakes.requests.ConnectionError("sin red")
        store2 = [self.event(4.5)]
        self.assertEqual(quakes.send_alerts(store2, failing, "topic-x", NOW), 0)
        self.assertFalse(store2[0].get("notified"))


class RoundTripTests(unittest.TestCase):
    def test_payload_survives_reload_with_notified_flag(self):
        store = []
        quakes.merge_into(store, quakes.parse_usgs({"features": [usgs(4.6, 9.9, -84.0, 15, "x, Costa Rica", 100)]}), NOW)
        store[0]["notified"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.json"
            path.write_text(json.dumps(quakes.build_payload(store, {"usgs": True, "emsc": True})), encoding="utf-8")
            again = quakes.load_previous(path)
        self.assertEqual(len(again), 1)
        self.assertTrue(again[0]["notified"])
        self.assertEqual(again[0]["mag"], 4.6)


if __name__ == "__main__":
    unittest.main()
