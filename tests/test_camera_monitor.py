import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "monitor_cameras.py"
spec = importlib.util.spec_from_file_location("raintrack_camera_monitor", MODULE_PATH)
cams = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cams)

# Límites aproximados de Costa Rica (con margen para referencias fronterizas).
CR_LAT = (7.9, 11.3)
CR_LON = (-86.1, -82.4)


class ParsingTests(unittest.TestCase):
    def test_localized_numbers(self):
        self.assertEqual(cams.parse_localized_number("1.234,5"), 1234.5)
        self.assertEqual(cams.parse_localized_number("1,234.5"), 1234.5)
        self.assertEqual(cams.parse_localized_number("12,5"), 12.5)
        self.assertEqual(cams.parse_localized_number(" 7 "), 7.0)
        self.assertIsNone(cams.parse_localized_number(""))
        self.assertIsNone(cams.parse_localized_number(None))
        self.assertIsNone(cams.parse_localized_number("n/d"))

    def test_camera_name_from_slug(self):
        self.assertEqual(cams.camera_name_from_slug("tamarindo", "tamarindo-diria-1"), "Diriá 1")
        self.assertEqual(cams.camera_name_from_slug("tamarindo", "default"), "Vista general del sitio")

    def test_cache_busted_keeps_existing_query(self):
        url = cams.cache_busted("https://example.test/a.jpg?x=1")
        self.assertIn("x=1", url)
        self.assertIn("raintrack_ts=", url)


class StationFreshnessTests(unittest.TestCase):
    NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

    def status(self, minutes_ago):
        stamp = (self.NOW - timedelta(minutes=minutes_ago)).isoformat()
        with patch.object(cams, "utc_now", return_value=self.NOW):
            return cams.assess_station_freshness(stamp)["availability_status"]

    def test_online_delayed_stale(self):
        self.assertEqual(self.status(5), "online")
        self.assertEqual(self.status(25), "online")  # el IMN publica ~cada 15 min + el ciclo del bot
        self.assertEqual(self.status(35), "delayed")
        self.assertEqual(self.status(40), "delayed")
        self.assertEqual(self.status(300), "stale")

    def test_future_or_missing_timestamp_is_unknown(self):
        with patch.object(cams, "utc_now", return_value=self.NOW):
            future = (self.NOW + timedelta(hours=3)).isoformat()
            self.assertEqual(cams.assess_station_freshness(future)["availability_status"], "unknown")
            self.assertEqual(cams.assess_station_freshness(None)["availability_status"], "unknown")
            self.assertEqual(cams.assess_station_freshness("no-es-fecha")["availability_status"], "unknown")


class StationHistoryTests(unittest.TestCase):
    def test_dead_after_seven_days_and_recovers(self):
        old = (cams.utc_now() - timedelta(days=8)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        previous = {"a": {"id": "a", "last_ok_at": old, "first_seen_at": old},
                    "b": {"id": "b", "last_ok_at": old, "first_seen_at": old}}
        rows = [{"id": "a", "availability_status": "stale"}, {"id": "b", "availability_status": "online"},
                {"id": "c", "availability_status": "stale"}]
        cams.apply_station_history(rows, previous)
        self.assertTrue(rows[0]["dead"])
        self.assertFalse(rows[1]["dead"])
        self.assertFalse(rows[2]["dead"])


class UcrVantageTests(unittest.TestCase):
    def test_parse_morning_and_afternoon(self):
        html = "Actualizado cada 5 minutos: 14/11/26, 7:01a Temperature 20.5&nbsp;°C Humidity 98% Today's Rain 1.2&nbsp;mm Rain Rate 2.4&nbsp;mm/hr"
        values = cams.parse_ucr_vantage(html)
        self.assertEqual(values["image_timestamp"], "2026-11-14T13:01:00Z")
        self.assertEqual(values["rain_rate_mmh"], 2.4)
        self.assertEqual(values["rain_today_mm"], 1.2)
        self.assertEqual(values["temperature_c"], 20.5)
        afternoon = cams.parse_ucr_vantage("Actualizado: 14/11/26, 1:05p Rain Rate 0.0 mm/hr")
        self.assertEqual(afternoon["image_timestamp"], "2026-11-14T19:05:00Z")


class UcrSanLuisTests(unittest.TestCase):
    def test_sums_last_hour_and_today(self):
        text = (
            "2026-11-14 07:10:10: tipo=MV_RSL, temp=23.8,rh=85,te525=0.2,bar=931.1\n"
            "2026-11-14 08:00:10: tipo=MV_RSL, temp=23.9,rh=88,te525=0.3,bar=931.1\n"
            "2026-11-14 08:12:10: tipo=MV_RSL, temp=24.0,rh=86.6,te525=0.1,bar=931.2\n"
        )
        values = cams.parse_ucr_sanluis(text)
        self.assertEqual(values["image_timestamp"], "2026-11-14T14:12:10Z")
        self.assertEqual(values["rain_last_hour_mm"], 0.4)
        self.assertEqual(values["rain_today_mm"], 0.6)
        self.assertEqual(cams.parse_ucr_sanluis("basura"), {})


class CameraTrainingTests(unittest.TestCase):
    def test_features_and_row(self):
        from PIL import Image
        sys_path = str(Path(__file__).resolve().parents[1] / "scripts")
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        import camera_training as ct
        image = Image.new("RGB", (200, 150), (120, 130, 150))
        feats = ct.extract_features(image)
        self.assertIn("sky_luma", feats)
        self.assertAlmostEqual(feats["contrast"], 0.0, places=1)
        stations = [
            {"id": "a", "lat": 9.93, "lon": -84.08, "availability_status": "online", "rain_last_hour_mm": 1.2},
            {"id": "b", "lat": 9.94, "lon": -84.07, "availability_status": "stale", "rain_last_hour_mm": 9.0},
            {"id": "c", "lat": 11.0, "lon": -85.0, "availability_status": "online", "rain_last_hour_mm": 0.0},
        ]
        now = cams.utc_now()
        flashes = [[now.timestamp() - 60, 9.95, -84.05], [now.timestamp() - 3000, 9.95, -84.05]]
        row = ct.build_row({"id": "cam1", "lat": 9.935, "lon": -84.075, "image_quality_status": "usable", "image_age_minutes": 3},
                           feats, stations, flashes, now)
        self.assertEqual([item[0] for item in row["st"]], ["a"])
        self.assertEqual(row["lg"], 1)
        self.assertIsNone(ct.lightning_near(9.9, -84.0, None, now))

    def test_append_rows_prunes_old(self):
        import tempfile
        import camera_training as ct
        now = cams.utc_now()
        old = (now - timedelta(days=20)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            path.write_text(json.dumps({"t": old, "cam": "old"}) + "\n", encoding="utf-8")
            total = ct.append_rows([{"t": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"), "cam": "new"}], now, path)
            self.assertEqual(total, 1)
            self.assertNotIn("old", path.read_text(encoding="utf-8"))


class HomeCameraTests(unittest.TestCase):
    def test_tablet_features_match_bot_features(self):
        from PIL import Image
        scripts = str(Path(__file__).resolve().parents[1] / "scripts")
        tablet = str(Path(__file__).resolve().parents[1] / "tools" / "home-cameras")
        for folder in (scripts, tablet):
            if folder not in sys.path:
                sys.path.insert(0, folder)
        import camera_training as ct
        import camaras_casa as tablet_script
        img = Image.new("RGB", (200, 150), (90, 120, 160))
        for x in range(0, 200, 7):
            img.putpixel((x, 40), (255, 255, 255))
        self.assertEqual(ct.extract_features(img), tablet_script.extract_features(img))

    def test_parse_home_messages_filters_bad_data(self):
        import camera_training as ct
        now = cams.utc_now()
        stamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        feats = {k: 1.0 for k in ct.FEATURE_KEYS}
        good = {"v": 1, "cam": "casa-patio", "t": stamp, "q": "usable", "f": feats}
        old = dict(good, t=(now - timedelta(hours=3)).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
        badcam = dict(good, cam="../etc")
        missing = dict(good, f={"luma": 1.0})
        nan = dict(good, f=dict(feats, luma=1e9))
        lines = "\n".join(json.dumps({"event": "message", "message": json.dumps(m)}) for m in (good, old, badcam, missing, nan))
        lines += "\n" + json.dumps({"event": "open"}) + "\nbasura"
        out = ct.parse_home_messages(lines, now)
        self.assertEqual([m["cam"] for m in out], ["home-casa-patio"])

    def test_append_rows_dedupes(self):
        import tempfile
        import camera_training as ct
        now = cams.utc_now()
        row = {"t": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"), "cam": "home-a"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            ct.append_rows([row], now, path)
            self.assertEqual(ct.append_rows([row], now, path), 1)


class CameraSourcesTests(unittest.TestCase):
    def test_config_file_matches_loaded_constants(self):
        raw = json.loads(cams.CAMERA_SOURCES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(raw["sites"]), len(cams.SITES))
        self.assertEqual(len(raw["imn_stations"]), len(cams.IMN_STATIONS))

    def test_ids_are_unique(self):
        for name in ("IMN_STATIONS", "OVSICORI_CAMERAS", "SKYLINE_CAMERAS", "EXTERNAL_LINK_CAMERAS"):
            ids = [row["id"] for row in getattr(cams, name)]
            self.assertEqual(len(ids), len(set(ids)), name)
        slugs = [row[0] for row in cams.SITES]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_coordinates_are_inside_costa_rica(self):
        points = [(row[3], row[4], row[0]) for row in cams.SITES]
        for name in ("IMN_STATIONS", "OVSICORI_CAMERAS", "SKYLINE_CAMERAS", "EXTERNAL_LINK_CAMERAS"):
            points += [(row["lat"], row["lon"], row["id"]) for row in getattr(cams, name)]
        for lat, lon, label in points:
            self.assertTrue(CR_LAT[0] <= lat <= CR_LAT[1], f"lat fuera de rango: {label}")
            self.assertTrue(CR_LON[0] <= lon <= CR_LON[1], f"lon fuera de rango: {label}")

    def test_external_cameras_have_https_page_urls(self):
        for name in ("OVSICORI_CAMERAS", "SKYLINE_CAMERAS", "EXTERNAL_LINK_CAMERAS"):
            for row in getattr(cams, name):
                self.assertTrue(row["page_url"].startswith("https://"), row["id"])


class HomeMotionTests(unittest.TestCase):
    def setUp(self):
        import random
        scripts = str(Path(__file__).resolve().parents[1] / "scripts")
        tablet = str(Path(__file__).resolve().parents[1] / "tools" / "home-cameras")
        for folder in (scripts, tablet):
            if folder not in sys.path:
                sys.path.insert(0, folder)
        import camaras_casa as tablet_script
        import camera_training as ct
        from PIL import Image
        self.t, self.ct, self.Image, self.random = tablet_script, ct, Image, random

    def base(self):
        return self.Image.new("RGB", (200, 150), (110, 105, 100))

    def rain_frame(self, seed):
        img = self.base()
        rng = self.random.Random(seed)
        for _ in range(500):  # rayitas repartidas por toda la imagen
            x, y = rng.randrange(0, 198), rng.randrange(0, 140)
            for k in range(8):
                img.putpixel((x + (k // 4), y + k), (235, 235, 240))
        return img

    def test_still_scene_has_no_motion(self):
        result = self.t.motion_features([self.base(), self.base(), self.base()])
        self.assertEqual(result["motion"], 0)
        self.assertEqual(result["motion_spread"], 0)

    def test_rain_changes_many_blocks(self):
        result = self.t.motion_features([self.rain_frame(1), self.rain_frame(2), self.rain_frame(3)])
        self.assertGreater(result["motion_spread"], 0.5)

    def test_object_that_stays_is_not_counted_as_motion(self):
        a, b, c = self.base(), self.base(), self.base()
        for x in range(60, 100):
            for y in range(70, 110):
                b.putpixel((x, y), (250, 250, 250))  # algo aparece solo en la foto del medio
        # el menor cambio entre pares evita que un solo evento cuente (a-b y b-c son iguales aquí,
        # así que probamos con un objeto presente en dos fotos y ausente en la primera)
        c = b.copy()
        result = self.t.motion_features([a, b, c])
        self.assertEqual(result["motion"], 0)

    def test_bot_accepts_messages_with_and_without_motion(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 14, 17, 5, tzinfo=timezone.utc)
        feats = {k: 1.0 for k in self.ct.FEATURE_KEYS}
        def line(extra):
            data = {"v": 1, "cam": "casa", "t": "2026-11-14T17:04:00Z", "q": "usable", "f": {**feats, **extra}}
            return json.dumps({"event": "message", "message": json.dumps(data)})
        old = self.ct.parse_home_messages(line({}), now)
        new = self.ct.parse_home_messages(line({"motion": 3.2, "motion_spread": 0.7}), now)
        bad = self.ct.parse_home_messages(line({"motion": float("nan")}), now)
        self.assertEqual(len(old), 1)
        self.assertNotIn("motion", old[0]["f"])
        self.assertEqual(new[0]["f"]["motion_spread"], 0.7)
        self.assertEqual(bad, [])


class HomeSilenceTests(unittest.TestCase):
    def setUp(self):
        scripts = str(Path(__file__).resolve().parents[1] / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import camera_training as ct
        self.ct = ct

    def write(self, tmp, times):
        path = Path(tmp) / "f.jsonl"
        path.write_text("\n".join(json.dumps({"t": t, "cam": "home-casa"}) for t in times) + "\n", encoding="utf-8")
        return path

    def test_alerts_once_per_outage_and_again_after_recovery(self):
        import tempfile
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as tmp:
            state = {}
            path = self.write(tmp, ["2026-11-14T17:00:00Z"])
            ok = self.ct.home_silence_message(datetime(2026, 11, 14, 17, 20, tzinfo=timezone.utc), state, path)
            self.assertIsNone(ok)
            alert = self.ct.home_silence_message(datetime(2026, 11, 14, 17, 40, tzinfo=timezone.utc), state, path)
            self.assertIn("11:00", alert["message"])  # 17:00 UTC = 11:00 hora local
            state["home_cam_alerted_for"] = alert["last"]
            again = self.ct.home_silence_message(datetime(2026, 11, 14, 19, 0, tzinfo=timezone.utc), state, path)
            self.assertIsNone(again)
            path = self.write(tmp, ["2026-11-14T17:00:00Z", "2026-11-14T20:00:00Z"])
            later = self.ct.home_silence_message(datetime(2026, 11, 14, 20, 45, tzinfo=timezone.utc), state, path)
            self.assertIsNotNone(later)

    def test_no_readings_ever_means_no_alert(self):
        import tempfile
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.ct.home_silence_message(datetime.now(timezone.utc), {}, Path(tmp) / "none.jsonl"))


class HomeRainEstimateTests(unittest.TestCase):
    def setUp(self):
        scripts = str(Path(__file__).resolve().parents[1] / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import camera_training as ct
        self.ct = ct

    def row(self, saturation, ground=100, hour=11, q="usable", t="2026-11-14T17:00:00Z"):
        return {"t": t, "cam": "home-casa", "hour": hour, "q": q,
                "f": {"saturation": saturation, "ground_luma": ground, "sky_blue_ratio": 0.9}}

    def test_without_history_uses_fixed_threshold(self):
        self.assertEqual(self.ct.estimate_home_rain(self.row(20), [])["estimate"], "possible_rain")
        self.assertEqual(self.ct.estimate_home_rain(self.row(60), [])["estimate"], "no_rain")

    def test_night_and_low_quality_give_no_opinion(self):
        self.assertEqual(self.ct.estimate_home_rain(self.row(10, hour=22), [])["estimate"], "unknown")
        self.assertEqual(self.ct.estimate_home_rain(self.row(10, q="low_visibility"), [])["estimate"], "unknown")

    def test_with_baseline_needs_grey_and_darker_ground(self):
        history = [self.row(40, ground=100) for _ in range(15)]
        self.assertEqual(self.ct.estimate_home_rain(self.row(20, ground=70), history)["estimate"], "possible_rain")
        # apagado pero el suelo no se oscureció (nublado seco): no avisa
        self.assertEqual(self.ct.estimate_home_rain(self.row(20, ground=98), history)["estimate"], "no_rain")
        # suelo oscuro pero con color normal (sombra): no avisa
        self.assertEqual(self.ct.estimate_home_rain(self.row(38, ground=70), history)["estimate"], "no_rain")
        # 30 es "apagado" con umbral fijo, pero normal para una cámara que suele dar 40
        self.assertEqual(self.ct.estimate_home_rain(self.row(30, ground=70), history)["estimate"], "no_rain")

    def test_home_estimates_use_latest_fresh_reading_and_round_coordinates(self):
        import tempfile
        from datetime import datetime, timezone
        now = datetime(2026, 11, 14, 17, 5, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.jsonl"
            rows = [self.row(60, t="2026-11-14T16:50:00Z"), self.row(18, t="2026-11-14T17:00:00Z")]
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            result = self.ct.home_estimates(now, 9.912345, -83.612345, path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["estimate"], "possible_rain")
            self.assertEqual((result[0]["lat"], result[0]["lon"]), (9.91, -83.61))
            stale = self.ct.home_estimates(datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc), None, None, path)
            # Sin lectura reciente la cámara se conserva, marcada como sin conexión.
            self.assertEqual(len(stale), 1)
            self.assertTrue(stale[0]["stale"])
            self.assertEqual(stale[0]["estimate"], "unknown")


if __name__ == "__main__":
    unittest.main()
