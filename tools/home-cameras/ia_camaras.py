"""Prueba de IA en las cámaras públicas (no se muestra en la app todavía).

De día, cada 20 min, la tablet baja la foto de las cámaras públicas en línea, la achica y se la pasa al
Worker, que le pregunta a una IA de visión si se ve LLUVIA, NUBLADO, DESPEJADO o NO_SE_VE. Los resultados
quedan guardados para compararlos con las estaciones del IMN antes de usarlos en el mapa.

Requiere: pip install requests (Pillow ya está).
"""
from __future__ import annotations

import io
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aviones_casa

PAGES = "https://allan101010.github.io/RAINROAD/"
LOCAL_TZ = timezone(timedelta(hours=-6))
EVERY_S = 20 * 60
START_HOUR, END_HOUR = 6, 17       # de 6:00 a 17:59 (de noche la mayoría no se ve)
MAX_PER_ROUND = 30                 # máx. fotos a la IA por ronda (12 h x 3 rondas x 30 = 1080 al día, cupo gratis ~1100)
MAX_AGE_MIN = 30
WIDTH = 560


def _log(text: str) -> None:
    print(f"{datetime.now():%H:%M:%S} ia: {text}", flush=True)


def _json(url: str):
    import json
    with urllib.request.urlopen(urllib.request.Request(url, headers=aviones_casa.UA), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


ROUND = {"n": 0}


def pick_cameras(catalog: dict, alerts: dict, rotate: bool = False) -> list[dict]:
    """Cámaras con foto directa y con imagen reciente según el último informe del bot.

    Si hay más de MAX_PER_ROUND, se turnan entre rondas para que todas se analicen."""
    status = {c.get("id"): c for c in alerts.get("cameras", [])}
    chosen = []
    for cam in catalog.get("cameras", []):
        info = status.get(cam.get("id"), {})
        if not cam.get("snapshot_url") or cam.get("lat") is None:
            continue
        if info.get("availability_status") not in ("online", "delayed"):
            continue
        age = info.get("image_age_minutes")
        if age is not None and age > MAX_AGE_MIN:
            continue
        chosen.append(cam)
    if not rotate or len(chosen) <= 1:
        return chosen
    start = ROUND["n"] % len(chosen)
    ROUND["n"] += MAX_PER_ROUND
    return chosen[start:] + chosen[:start]


STATE_PATH = Path.home() / ".raintrack_ia_estado.json"
FROZEN_DAYS = 7          # sin cambiar en una semana: se aparta y se revisa una vez al día
FROZEN_RECHECK_S = 86400


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")


def image_signature(data: bytes) -> list[int]:
    """Huella de la foto: 16x9 puntos en grises. Si no cambia entre rondas, la foto está congelada."""
    from PIL import Image
    return list(Image.open(io.BytesIO(data)).convert("L").resize((16, 9)).tobytes())


def same_image(a: list[int] | None, b: list[int]) -> bool:
    return bool(a) and len(a) == len(b) and sum(abs(x - y) for x, y in zip(a, b)) / len(b) < 2.0


def frozen_skip(entry: dict, now: float) -> bool:
    """¿Saltarse esta cámara sin bajar la foto? Solo si lleva una semana congelada y ya se revisó hoy."""
    if now - entry.get("changed", now) < FROZEN_DAYS * 86400:
        return False
    return now - entry.get("checked", 0) < FROZEN_RECHECK_S


def small_jpeg(data: bytes) -> bytes:
    from PIL import Image, ImageOps
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    if image.width > WIDTH:
        image = image.resize((WIDTH, round(image.height * WIDTH / image.width)))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=78)
    return out.getvalue()


def fetch_image(session, cam: dict) -> bytes:
    sep = "&" if "?" in cam["snapshot_url"] else "?"
    response = session.get(cam["snapshot_url"] + sep + "raintrack_ts=" + str(int(time.time())), timeout=25,
                           headers={"Accept": "image/*", "Cache-Control": "no-cache"})
    response.raise_for_status()
    if not response.headers.get("Content-Type", "").lower().startswith("image/"):
        raise ValueError("no es imagen")
    return response.content


def classify(session, cam: dict, data: bytes | None = None) -> dict:
    body = small_jpeg(data if data is not None else fetch_image(session, cam))
    req = urllib.request.Request(aviones_casa.WORKER + "/ia", data=body, method="POST", headers={
        **aviones_casa.UA, "Content-Type": "image/jpeg", "X-Clave": aviones_casa._key(),
        "X-Cam": cam["id"], "X-Lat": str(cam["lat"]), "X-Lon": str(cam["lon"])})
    import json
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def loop() -> None:
    import requests
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 14) RainTrackCR-tablet/1.0"
    last_round = 0.0
    while True:
        try:
            hour = datetime.now(LOCAL_TZ).hour
            if START_HOUR <= hour <= END_HOUR and time.time() - last_round >= EVERY_S:
                last_round = time.time()
                cams = pick_cameras(_json(PAGES + "camera-catalog.json?t=" + str(int(time.time()))),
                                    _json(PAGES + "camera-alerts.json?t=" + str(int(time.time()))), rotate=True)
                counts: dict[str, int] = {}
                state = _load_state()
                now = time.time()
                sent = 0
                for cam in cams:
                    entry = state.setdefault(cam["id"], {"changed": now})
                    if frozen_skip(entry, now):
                        counts["apartada"] = counts.get("apartada", 0) + 1
                        continue
                    if sent >= MAX_PER_ROUND:
                        break
                    try:
                        data = fetch_image(session, cam)
                        entry["checked"] = now
                        sig = image_signature(data)
                        if same_image(entry.get("sig"), sig):
                            counts["congelada"] = counts.get("congelada", 0) + 1
                            continue
                        entry["sig"], entry["changed"] = sig, now
                        result = classify(session, cam, data)
                        sent += 1
                        counts[result.get("label", "?")] = counts.get(result.get("label", "?"), 0) + 1
                    except urllib.error.HTTPError as exc:
                        if exc.code == 429:
                            _log("cupo diario de la IA agotado; sigue mañana")
                            break
                        counts["error"] = counts.get("error", 0) + 1
                    except Exception:
                        counts["error"] = counts.get("error", 0) + 1
                    time.sleep(1)
                _save_state(state)
                _log(f"{len(cams)} cámaras: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
            time.sleep(60)
        except Exception as exc:
            _log(f"error {type(exc).__name__}")
            time.sleep(300)


def start(config: dict) -> None:
    if config.get("ia_camaras") is False:
        return
    threading.Thread(target=loop, name="ia", daemon=True).start()
    _log("prueba de IA lista (de día, cada 20 min)")


if __name__ == "__main__":
    import sys
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 14) RainTrackCR-tablet/1.0"
    cams = pick_cameras(_json(PAGES + "camera-catalog.json"), _json(PAGES + "camera-alerts.json"))
    for cam in cams[: int(sys.argv[1]) if len(sys.argv) > 1 else 3]:  # prueba a mano (sin revisar congeladas)
        try:
            print(cam["id"], classify(s, cam))
        except urllib.error.HTTPError as exc:
            print(cam["id"], "error", exc.code, exc.read().decode("utf-8", "replace")[:400])
