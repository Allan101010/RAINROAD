"""Datos más en vivo desde la tablet de la casa, publicados en el Worker de Cloudflare.

1. Cámara de casa: cada lectura (cada 2 min) se estima aquí mismo con la misma regla del bot
   (scripts/camera_training.py) y se publica al instante. ntfy sigue recibiendo una lectura cada 8 min
   para el historial del bot.
2. Estaciones del IMN: mientras alguien tiene la app abierta, la tablet lee cada 3 min las tablas de las
   estaciones de las zonas elegidas (por defecto Valle Central) y las publica. El bot sigue leyendo todas
   cada 10 min. Además calcula cuánta lluvia cayó entre una lectura y la siguiente ("lloviendo ahora").

Requiere: pip install requests beautifulsoup4
"""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aviones_casa

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

LOCAL_TZ = timezone(timedelta(hours=-6))
HISTORY_PATH = Path.home() / ".raintrack_casa_historial.jsonl"
LAST_RAIN_PATH = Path.home() / ".raintrack_casa_ultima_lluvia.json"
HISTORY_DAYS = 3
STATIONS_EVERY_S = 180
DEMAND_CHECK_S = 30
STATION_FIELDS = ["id", "image_timestamp", "image_timestamp_source", "availability_status", "rain_observed",
                  "rain_last_hour_mm", "rain_since_7am_mm", "rain_previous_24h_mm", "temperature_c",
                  "humidity_percent", "wind_speed_kmh", "wind_direction_deg", "wind_gust_kmh", "dew_point_c",
                  "pressure_hpa"]


def _log(text: str) -> None:
    print(f"{datetime.now():%H:%M:%S} tiempo: {text}", flush=True)


# ---------- Cámara de casa ----------
SEED_URL = "https://raw.githubusercontent.com/Allan101010/RAINROAD/camera-training/camera-features.jsonl"


def _seed_history() -> None:
    """Primera vez: copia las lecturas de casa de los últimos días que ya guardó el bot (para la línea base)."""
    import urllib.request
    cutoff = (datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)).isoformat().replace("+00:00", "Z")
    with urllib.request.urlopen(urllib.request.Request(SEED_URL, headers=aviones_casa.UA), timeout=60) as r:
        lines = r.read().decode("utf-8").splitlines()
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if str(row.get("cam", "")).startswith("home-") and row.get("t", "") >= cutoff:
            rows.append({"t": row["t"], "cam": row["cam"][5:], "hour": row.get("hour"), "q": row.get("q"), "f": row.get("f", {})})
    _save_history(rows)
    _log(f"historial inicial: {len(rows)} lecturas del bot")


def _history() -> list[dict]:
    if not HISTORY_PATH.exists():
        try:
            _seed_history()
        except Exception as exc:
            _log(f"no se pudo copiar el historial del bot ({type(exc).__name__}); empieza de cero")
            HISTORY_PATH.write_text("", encoding="utf-8")
        if not HISTORY_PATH.exists():
            return []
    rows = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _save_history(rows: list[dict]) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)).isoformat().replace("+00:00", "Z")
    rows = [r for r in rows if r.get("t", "") >= cutoff]
    HISTORY_PATH.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")


def _last_rain(cam: str, stamp: str, estimate: dict) -> dict | None:
    """Última vez que la cámara vio lluvia (se guarda en un archivo para no perderla al reiniciar)."""
    try:
        saved = json.loads(LAST_RAIN_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    seeing = estimate.get("estimate") == "rain" or (estimate.get("estimate") == "possible_rain" and estimate.get("intensity"))
    if seeing:
        saved[cam] = {"t": stamp, "intensity": estimate.get("intensity")}
        try:
            LAST_RAIN_PATH.write_text(json.dumps(saved), encoding="utf-8")
        except OSError:
            pass
    return saved.get(cam)


def publish_home(message: dict) -> dict | None:
    """Estima la lluvia con la lectura nueva y la publica. Devuelve la estimación (o None si falla)."""
    import camera_training
    stamp = datetime.fromisoformat(message["t"].replace("Z", "+00:00"))
    row = {"t": message["t"], "cam": message["cam"], "hour": stamp.astimezone(LOCAL_TZ).hour,
           "q": message["q"], "f": message["f"]}
    history = [r for r in _history() if r.get("cam") == row["cam"]]
    estimate = camera_training.estimate_home_rain(row, history)
    others = [r for r in _history() if r.get("cam") != row["cam"]]
    _save_history(others + history + [row])
    extra = {k: row["f"][k] for k in ("splash_road", "splash_ref", "saturation", "motion") if k in row["f"]}
    cam_out = {"id": "home-" + row["cam"], "t": row["t"], **estimate, "f": extra}
    last = _last_rain(row["cam"], row["t"], estimate)
    if last:
        cam_out["last_rain"] = last
    payload = {"cams": [cam_out]}
    aviones_casa._post(aviones_casa.WORKER, "/casa", aviones_casa._key(), payload)
    return estimate


# ---------- Estaciones del IMN ----------
def _rain_now(previous: dict, station: dict) -> float | None:
    """Lluvia entre la lectura anterior y esta (mm), usando el acumulado desde las 7 a. m."""
    before = previous.get(station["id"])
    now_total, now_time = station.get("rain_since_7am_mm"), station.get("image_timestamp")
    if not before or now_total is None or not now_time or before["t"] == now_time or before["total"] is None:
        return None
    delta = now_total - before["total"]
    return round(delta, 1) if delta >= 0 else None   # negativo: se reinició a las 7 a. m.


def stations_loop(zones: list[str]) -> None:
    import requests
    import monitor_cameras as mc
    chosen = [s for s in mc.IMN_STATIONS if s.get("zone") in zones]
    session = requests.Session()
    session.headers["User-Agent"] = "RainTrackCR-tablet/1.0 (uso personal)"
    previous: dict[str, dict] = {}
    deltas: dict[str, dict] = {}
    last_run = 0.0
    active = False
    last_error = ""
    _log(f"estaciones listas ({len(chosen)} en {', '.join(zones)})")
    while True:
        try:
            wanted = bool(aviones_casa._get_json(aviones_casa.WORKER + "/demanda").get("wx_wanted"))
            if wanted != active:
                _log("app abierta, leyendo estaciones cada 3 min" if wanted else "app cerrada, estaciones en pausa")
                active = wanted
            if wanted and time.time() - last_run >= STATIONS_EVERY_S:
                last_run = time.time()
                out = []
                for station in chosen:
                    try:
                        values = mc.fetch_imn_table(session, station["table_url"])
                    except Exception:
                        continue
                    row = {"id": station["id"], **values}
                    row.update(mc.assess_station_freshness(row.get("image_timestamp")))
                    rain = row.get("rain_last_hour_mm")
                    row["rain_observed"] = (rain is not None and rain > 0 and row["availability_status"] == "online"
                                            and row.get("image_timestamp_source") == "imn_html_table")
                    slim = {k: row.get(k) for k in STATION_FIELDS}
                    step = _rain_now(previous, row)
                    if step is not None:
                        deltas[row["id"]] = {"mm": step, "from": previous[row["id"]]["t"], "to": row["image_timestamp"]}
                    if row["id"] in deltas and deltas[row["id"]]["to"] == row["image_timestamp"]:
                        slim["rain_step_mm"] = deltas[row["id"]]["mm"]
                        slim["rain_step_from"] = deltas[row["id"]]["from"]
                    if row.get("image_timestamp"):
                        previous[row["id"]] = {"t": row["image_timestamp"], "total": row.get("rain_since_7am_mm")}
                    out.append(slim)
                    time.sleep(0.4)   # una tabla a la vez, sin apurar al IMN
                if out:
                    aviones_casa._post(aviones_casa.WORKER, "/estaciones", aviones_casa._key(), {"stations": out})
            last_error = ""
            time.sleep(DEMAND_CHECK_S)
        except Exception as exc:
            text = f"{type(exc).__name__}: {getattr(exc, 'code', '') or exc}"
            if text != last_error:
                _log("error " + text)
                last_error = text
            time.sleep(60)


def start(config: dict) -> None:
    if config.get("estaciones") is False:
        return
    zones = config.get("estaciones_zonas") or ["Valle Central"]
    try:
        import requests  # noqa: F401
        import bs4  # noqa: F401
    except ImportError:
        _log("faltan paquetes: escribe  pip install requests beautifulsoup4  y reinicia")
        return
    threading.Thread(target=stations_loop, args=(zones,), name="estaciones", daemon=True).start()
