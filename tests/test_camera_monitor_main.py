"""Prueba de humo del monitor completo con la red simulada."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "monitor_cameras.py"


def landscape():
    img = Image.new("RGB", (640, 360))
    d = ImageDraw.Draw(img)
    for y in range(360):
        if y < 150:
            c = (90 + y // 3, 140 + y // 4, 200)
        elif y < 240:
            c = (30, 90 + (y - 150) // 2, 150)
        else:
            c = (200 - (y - 240) // 4, 180 - (y - 240) // 4, 130)
        d.line([(0, y), (640, y)], fill=c)
    for x in range(20, 640, 90):
        d.polygon([(x, 240), (x + 20, 150), (x + 40, 240)], fill=(20, 80, 30))
    for x in range(0, 640, 45):
        y0 = 40 + (x % 7) * 8
        d.ellipse([x, y0, x + 60, y0 + 35 + (x % 5) * 3], fill=(235, 235, 240))
    return img.filter(ImageFilter.GaussianBlur(0.8))


def web_camera(cam_id, name, snapshot="u"):
    return {"id": cam_id, "site_slug": "jaco", "site_name": "Jacó", "zone": "Z", "lat": 9.6, "lon": -84.6,
            "camera_name": name, "page_url": "https://example.test/" + cam_id,
            "source_type": "webcamscostarica", "snapshot_url": snapshot}


class MonitorMainTests(unittest.TestCase):
    def run_monitor(self, previous=None, rain=False):
        spec = importlib.util.spec_from_file_location("raintrack_monitor_main", MODULE_PATH)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        tmp = Path(tempfile.mkdtemp())
        m.ALERTS_PATH = tmp / "camera-alerts.json"
        m.CATALOG_PATH = tmp / "camera-catalog.json"
        if previous is not None:
            m.ALERTS_PATH.write_text(json.dumps(previous), encoding="utf-8")
        good, dark = landscape(), Image.new("RGB", (320, 240), (3, 3, 3))
        catalog = [
            web_camera("ok", "OK", "u-ok"), web_camera("dark", "Oscura", "u-dark"),
            web_camera("delayed", "Demorada", "u-del"), web_camera("unknown", "Sin hora", "u-unk"),
            web_camera("stale", "Vieja", "u-stale"), web_camera("off", "Apagada", None),
            {"id": "sky", "site_slug": "skyline-x", "site_name": "Sky", "zone": "G", "lat": 10.2, "lon": -85.3,
             "camera_name": "Sky", "page_url": "https://sky.test/1", "source_type": "skylinewebcams",
             "snapshot_url": "https://e.test/1.jpg", "live_video_page": True},
            {"id": "arenal", "site_slug": "volcan-arenal", "site_name": "Arenal", "zone": "N", "lat": 10.46, "lon": -84.7,
             "camera_name": "Arenal", "page_url": "https://arenal.test/cam", "source_type": "external_link",
             "snapshot_url": None, "live_video_page": True, "reason": "solo video"},
        ]
        freshness = {"delayed": ("delayed", 35), "unknown": ("unknown", None), "stale": ("stale", 300)}
        self.notify_calls = []
        m.notify_new_rain = lambda cur, prev, sess, **kw: self.notify_calls.append((cur, prev)) or 0
        m.session_with_headers = lambda: object()
        m.load_catalog = lambda session: catalog
        m.get_page = lambda session, url: ("<html></html>", url)
        m.skyline_page_is_offline = lambda soup: False
        m.resolve_snapshot_url = lambda s, c: ((c["snapshot_url"], "ok") if c.get("snapshot_url") else (None, "offline"))
        m.fetch_snapshot = lambda s, url: ((dark if url == "u-dark" else good), {"last_modified": None})
        m.assess_image_freshness = lambda c, i, meta: {
            "availability_status": freshness.get(c["id"], ("online", 3))[0],
            "image_age_minutes": freshness.get(c["id"], ("online", 3))[1]}
        m.collect_imn_stations = lambda s: [{
            "id": "imn-x", "station_name": "Estación IMN · X", "lat": 9.9, "lon": -84.0,
            "page_url": "https://imn.test/x", "availability_status": "online", "rain_observed": rain,
            "rain_last_hour_mm": 1.2 if rain else 0.0, "rain_since_7am_mm": 2.0 if rain else 0.0,
            "image_timestamp": "2026-11-13T20:00:00Z"}]
        self.assertEqual(m.main(), 0)
        return json.loads(m.ALERTS_PATH.read_text(encoding="utf-8"))

    def test_every_camera_is_reported_with_its_plain_status(self):
        data = self.run_monitor()
        by_id = {c["id"]: c for c in data["cameras"]}
        self.assertEqual(set(by_id), {"ok", "dark", "delayed", "unknown", "stale", "off", "sky", "arenal"})
        self.assertEqual(by_id["ok"]["status"], "online")
        self.assertEqual(by_id["delayed"]["status"], "delayed")
        self.assertEqual(by_id["unknown"]["status"], "unknown")
        self.assertEqual(by_id["dark"]["status"], "low_visibility")
        self.assertEqual(by_id["stale"]["status"], "stale")
        self.assertEqual(by_id["off"]["status"], "offline")
        self.assertEqual(by_id["sky"]["status"], "external_preview")
        self.assertEqual(by_id["arenal"]["status"], "external_link")
        self.assertEqual(by_id["arenal"]["availability_status"], "unknown")

    def test_cameras_never_generate_rain_alerts(self):
        data = self.run_monitor()
        self.assertEqual(data["alerts"], [])
        self.assertEqual(data["visual_rain_detection"], "disabled")
        self.assertEqual(data["camera_count"], 8)
        self.assertEqual(data["evaluated_count"], 1)
        for camera in data["cameras"]:
            for key in ("scene_assessment", "rain_evidence_assessment", "rain_probability", "vision_judge"):
                self.assertNotIn(key, camera)

    def test_station_rain_is_the_only_alert(self):
        dry = self.run_monitor(rain=False)
        wet = self.run_monitor(rain=True)
        self.assertEqual(dry["station_alerts"], [])
        self.assertEqual([a["station_id"] for a in wet["station_alerts"]], ["imn-x"])
        self.assertEqual(wet["station_alerts"][0]["rain_last_hour_mm"], 1.2)

    def test_monitor_hands_new_station_rain_to_notifier(self):
        previous = {"generated_at": "2000-01-01T00:00:00Z", "station_alerts": []}
        self.run_monitor(previous=previous, rain=True)
        current, before = self.notify_calls[0]
        self.assertEqual([a["station_id"] for a in current], ["imn-x"])
        self.assertEqual(before, [])

    def test_camera_back_from_offline_is_marked_recovered(self):
        previous = {"generated_at": "2000-01-01T00:00:00Z", "cameras": [
            {"id": "ok", "availability_status": "offline"}]}
        data = self.run_monitor(previous=previous)
        by_id = {c["id"]: c for c in data["cameras"]}
        self.assertTrue(by_id["ok"]["recovered"])
        self.assertFalse(by_id["dark"]["recovered"])


if __name__ == "__main__":
    unittest.main()
