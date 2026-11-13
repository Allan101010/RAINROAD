import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import vision_judge as vj  # noqa: E402

spec = importlib.util.spec_from_file_location("raintrack_camera_monitor_vj", SCRIPTS / "monitor_cameras.py")
cams = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cams)


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self._text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return {"content": [{"type": "text", "text": self._text}]}


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def rain_reply(raining="yes", confidence=0.93, evidence="Se ven rayas de lluvia."):
    return FakeResponse(200, json.dumps({"raining": raining, "confidence": confidence, "evidence": evidence}))


def make_judge(session, **kwargs):
    return vj.VisionJudge(api_key="test-key", session=session, **kwargs)


def img(color=(120, 120, 120)):
    return Image.new("RGB", (64, 48), color)


class ParseVerdictTests(unittest.TestCase):
    def test_confident_yes_is_rain(self):
        out = vj.parse_verdict('{"raining":"yes","confidence":0.9,"evidence":"rayas"}')
        self.assertEqual(out["verdict"], "rain")

    def test_low_confidence_yes_becomes_unclear(self):
        out = vj.parse_verdict('{"raining":"yes","confidence":0.5,"evidence":"quizá"}')
        self.assertEqual(out["verdict"], "unclear")

    def test_no_and_unclear(self):
        self.assertEqual(vj.parse_verdict('{"raining":"no","confidence":0.9,"evidence":"seco"}')["verdict"], "no_rain")
        self.assertEqual(vj.parse_verdict('{"raining":"unclear","confidence":0.2,"evidence":""}')["verdict"], "unclear")

    def test_json_inside_extra_text_is_found(self):
        out = vj.parse_verdict('Claro:\n{"raining":"yes","confidence":0.95,"evidence":"x"}\nGracias')
        self.assertEqual(out["verdict"], "rain")

    def test_garbage_is_unclear(self):
        for bad in ("", "no sé", "{rota", '{"raining":"tal vez"}', '{"confidence":1}'):
            self.assertEqual(vj.parse_verdict(bad)["verdict"], "unclear", bad)

    def test_confidence_is_clamped(self):
        self.assertEqual(vj.parse_verdict('{"raining":"yes","confidence":7,"evidence":"x"}')["confidence"], 1.0)


class JudgeBehaviourTests(unittest.TestCase):
    def test_disabled_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            judge = vj.VisionJudge.from_env()
        self.assertFalse(judge.enabled)
        self.assertFalse(judge.can_call())

    def test_api_call_returns_rain_and_counts(self):
        session = FakeSession(rain_reply())
        judge = make_judge(session)
        out = judge.assess(img(), "Cámara de prueba")
        self.assertEqual((out["verdict"], out["source"]), ("rain", "api"))
        self.assertEqual((session.calls, judge.calls_today, judge.calls_this_run), (1, 1, 1))

    def test_same_image_reuses_previous_verdict_without_api_call(self):
        session = FakeSession(rain_reply())
        judge = make_judge(session)
        first = judge.assess(img(), "cam")
        again = judge.assess(img(), "cam", previous=first)
        self.assertEqual(again["source"], "reused")
        self.assertEqual(again["verdict"], "rain")
        self.assertEqual(session.calls, 1)

    def test_different_image_is_not_reused(self):
        session = FakeSession(rain_reply(), rain_reply("no", 0.9, "seco"))
        judge = make_judge(session)
        first = judge.assess(img((10, 10, 10)), "cam")
        second = judge.assess(img((200, 30, 30)), "cam", previous=first)
        self.assertEqual(second["source"], "api")
        self.assertEqual(second["verdict"], "no_rain")

    def test_budget_or_error_results_are_never_reused(self):
        session = FakeSession(rain_reply())
        judge = make_judge(session)
        ok = judge.assess(img(), "cam")
        stale = dict(ok, source="budget", verdict="unclear")
        out = judge.assess(img(), "cam", previous=stale)
        self.assertEqual(out["source"], "api")

    def test_per_run_limit(self):
        session = FakeSession(rain_reply())
        judge = make_judge(session, max_per_run=2)
        sources = [judge.assess(img((i * 40, 0, 0)), "cam")["source"] for i in range(4)]
        self.assertEqual(sources, ["api", "api", "budget", "budget"])
        self.assertEqual(session.calls, 2)
        self.assertEqual(judge.skipped_budget, 2)

    def test_daily_limit(self):
        session = FakeSession(rain_reply())
        judge = make_judge(session, daily_limit=5, calls_today=5)
        self.assertEqual(judge.assess(img(), "cam")["source"], "budget")
        self.assertEqual(session.calls, 0)

    def test_api_error_gives_unclear_and_never_raises(self):
        session = FakeSession(requests.ConnectionError("sin red"))
        judge = make_judge(session)
        with patch.object(vj.time, "sleep"):
            out = judge.assess(img(), "cam")
        self.assertEqual((out["verdict"], out["source"]), ("unclear", "error"))
        self.assertEqual(judge.errors, 1)

    def test_retry_on_429_then_success(self):
        session = FakeSession(FakeResponse(429), rain_reply())
        judge = make_judge(session)
        with patch.object(vj.time, "sleep"):
            out = judge.assess(img(), "cam")
        self.assertEqual(out["verdict"], "rain")
        self.assertEqual(session.calls, 2)

    def test_daily_counter_resets_on_new_day(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "k"}, clear=True):
            same = vj.VisionJudge.from_env({"date": vj.utc_today(), "calls_today": 40})
            old = vj.VisionJudge.from_env({"date": "2000-01-01", "calls_today": 40})
        self.assertEqual((same.calls_today, old.calls_today), (40, 0))


class ApplyVisionJudgeTests(unittest.TestCase):
    def camera(self, status):
        return {"id": "cam", "camera_name": "Cámara", "status": status, "message": ""}

    def test_disabled_never_leaves_possible_or_clear(self):
        judge = vj.VisionJudge(api_key=None)
        for status in ("possible", "clear"):
            result = self.camera(status)
            cams.apply_vision_judge(result, img(), judge, None, candidate=True)
            self.assertEqual(result["status"], "weather_uncertain")
            self.assertIsNone(result["vision_judge"])

    def test_disabled_keeps_other_statuses(self):
        judge = vj.VisionJudge(api_key=None)
        result = self.camera("low_visibility")
        cams.apply_vision_judge(result, img(), judge, None, candidate=False)
        self.assertEqual(result["status"], "low_visibility")

    def test_enabled_rain_verdict_makes_possible(self):
        judge = make_judge(FakeSession(rain_reply()))
        result = self.camera("weather_uncertain")
        cams.apply_vision_judge(result, img(), judge, None, candidate=True)
        self.assertEqual(result["status"], "possible")
        self.assertEqual(result["vision_judge"]["verdict"], "rain")
        self.assertIn("IA de visión", result["message"])

    def test_enabled_no_rain_makes_clear(self):
        judge = make_judge(FakeSession(rain_reply("no", 0.9, "Pista mojada pero sin gotas.")))
        result = self.camera("weather_uncertain")
        cams.apply_vision_judge(result, img(), judge, None, candidate=True)
        self.assertEqual(result["status"], "clear")

    def test_enabled_unclear_stays_uncertain(self):
        judge = make_judge(FakeSession(rain_reply("unclear", 0.3, "Imagen oscura.")))
        result = self.camera("possible")
        cams.apply_vision_judge(result, img(), judge, None, candidate=True)
        self.assertEqual(result["status"], "weather_uncertain")

    def test_non_candidate_is_not_sent_to_api(self):
        session = FakeSession(rain_reply())
        judge = make_judge(session)
        result = self.camera("weather_uncertain")
        cams.apply_vision_judge(result, img(), judge, None, candidate=False)
        self.assertEqual(session.calls, 0)
        self.assertEqual(result["status"], "weather_uncertain")


if __name__ == "__main__":
    unittest.main()
