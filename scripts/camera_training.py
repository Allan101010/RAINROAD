#!/usr/bin/env python3
"""Recolección de datos para aprender a detectar lluvia con las cámaras.

Por cada cámara en línea guarda un resumen numérico de la imagen (no la foto) junto con lo que
midieron las estaciones cercanas y los rayos de los últimos minutos. Con eso se puede medir,
sin etiquetar nada a mano, si una cámara "ve" la lluvia. No afecta nada visible en la app.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image, ImageFilter, ImageOps, ImageStat

DATA_PATH = Path("training-data/camera-features.jsonl")
BRANCH = "camera-training"
KEEP_DAYS = 14
LIGHTNING_URL = "https://raw.githubusercontent.com/Allan101010/RAINROAD/lightning-data/lightning.json"
STATION_RADIUS_KM = 25
LIGHTNING_RADIUS_KM = 15
LIGHTNING_MINUTES = 15
LOCAL_TZ = timezone(timedelta(hours=-6))


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180
    a = math.sin((lat2 - lat1) * rad / 2) ** 2 + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin((lon2 - lon1) * rad / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def extract_features(image: Image.Image) -> dict:
    """Resumen numérico de la imagen: brillo, contraste, color, bordes y cielo vs suelo."""
    width, height = 128, 96
    rgb = image.convert("RGB").resize((width, height))
    gray = ImageOps.grayscale(rgb)
    third = height // 3

    def mean_std(im: Image.Image) -> tuple[float, float]:
        stat = ImageStat.Stat(im)
        return float(stat.mean[0]), float(stat.stddev[0])

    sky_mean, sky_std = mean_std(gray.crop((0, 0, width, third)))
    ground_mean, ground_std = mean_std(gray.crop((0, third, width, height)))
    all_mean, all_std = mean_std(gray)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_all, _ = mean_std(edges)
    edge_sky, _ = mean_std(edges.crop((0, 0, width, third)))
    saturation = float(ImageStat.Stat(rgb.convert("HSV")).mean[1])
    sky_rgb = ImageStat.Stat(rgb.crop((0, 0, width, third))).mean
    histogram = gray.histogram()
    total = max(1, sum(histogram))
    return {
        "luma": round(all_mean, 1), "contrast": round(all_std, 1),
        "sky_luma": round(sky_mean, 1), "sky_contrast": round(sky_std, 1),
        "ground_luma": round(ground_mean, 1), "ground_contrast": round(ground_std, 1),
        "edges": round(edge_all, 2), "sky_edges": round(edge_sky, 2),
        "saturation": round(saturation, 1),
        "sky_blue_ratio": round(float(sky_rgb[2]) / max(1.0, float(sky_rgb[0])), 3),
        "bright_frac": round(sum(histogram[200:]) / total, 3),
        "dark_frac": round(sum(histogram[:40]) / total, 3),
    }


def nearby_stations(lat: float, lon: float, stations: list[dict]) -> list[list]:
    found = []
    for station in stations:
        if station.get("availability_status") not in ("online", "delayed"):
            continue
        if station.get("lat") is None or station.get("lon") is None:
            continue
        dist = distance_km(lat, lon, float(station["lat"]), float(station["lon"]))
        if dist <= STATION_RADIUS_KM:
            found.append([station.get("id"), round(dist, 1), station.get("rain_last_hour_mm"), station.get("availability_status")])
    found.sort(key=lambda item: item[1])
    return found[:3]


def fetch_lightning(session: requests.Session) -> list[list[float]] | None:
    try:
        response = session.get(LIGHTNING_URL, timeout=15)
        response.raise_for_status()
        return [f for f in response.json().get("flashes", []) if isinstance(f, list) and len(f) == 3]
    except Exception:
        return None


def lightning_near(lat: float, lon: float, flashes: list[list[float]] | None, now: datetime) -> int | None:
    if flashes is None:
        return None
    since = now.timestamp() - LIGHTNING_MINUTES * 60
    return sum(1 for f in flashes if f[0] >= since and distance_km(lat, lon, f[1], f[2]) <= LIGHTNING_RADIUS_KM)


def build_row(camera: dict, features: dict, stations: list[dict], flashes, now: datetime) -> dict:
    lat, lon = float(camera["lat"]), float(camera["lon"])
    return {
        "t": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cam": camera["id"],
        "hour": now.astimezone(LOCAL_TZ).hour,
        "q": camera.get("image_quality_status"),
        "age": camera.get("image_age_minutes"),
        "f": features,
        "st": nearby_stations(lat, lon, stations),
        "lg": lightning_near(lat, lon, flashes, now),
    }


FEATURE_KEYS = ("luma", "contrast", "sky_luma", "sky_contrast", "ground_luma", "ground_contrast",
                "edges", "sky_edges", "saturation", "sky_blue_ratio", "bright_frac", "dark_frac")
OPTIONAL_FEATURE_KEYS = ("motion", "motion_spread")  # solo las manda la tablet nueva
HOME_MAX_SKEW_MINUTES = 30


def parse_home_messages(text: str, now: datetime) -> list[dict]:
    """Lee los mensajes de la tablet desde ntfy (una línea JSON por mensaje) y descarta lo dudoso."""
    messages = []
    for line in text.splitlines():
        try:
            envelope = json.loads(line)
            if envelope.get("event") != "message":
                continue
            data = json.loads(envelope.get("message", ""))
            cam = str(data.get("cam", ""))
            features = data.get("f", {})
            stamp = datetime.fromisoformat(str(data.get("t", "")).replace("Z", "+00:00"))
            if data.get("v") != 1 or not re.fullmatch(r"[a-z0-9-]{1,40}", cam):
                continue
            if abs((now - stamp).total_seconds()) > HOME_MAX_SKEW_MINUTES * 60:
                continue
            clean = {}
            for key in FEATURE_KEYS:
                value = float(features[key])
                if not math.isfinite(value) or abs(value) > 1000:
                    raise ValueError(key)
                clean[key] = value
            for key in OPTIONAL_FEATURE_KEYS:
                if key in features:
                    value = float(features[key])
                    if not math.isfinite(value) or abs(value) > 1000:
                        raise ValueError(key)
                    clean[key] = value
            quality = data.get("q") if data.get("q") in ("usable", "low_visibility") else "usable"
            messages.append({"cam": "home-" + cam, "t": stamp.astimezone(timezone.utc), "q": quality, "f": clean})
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return messages


def fetch_home_rows(session: requests.Session, topic: str, lat: float | None, lon: float | None,
                    stations: list[dict], flashes, now: datetime) -> list[dict]:
    """Filas de las cámaras de casa, con las estaciones y rayos cercanos al lugar (si se conoce)."""
    try:
        response = session.get(f"https://ntfy.sh/{topic}/json", params={"poll": "1", "since": "20m"}, timeout=20)
        response.raise_for_status()
    except Exception:
        return []
    rows = []
    for message in parse_home_messages(response.text, now):
        rows.append({
            "t": message["t"].replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "cam": message["cam"],
            "hour": message["t"].astimezone(LOCAL_TZ).hour,
            "q": message["q"],
            "age": None,
            "f": message["f"],
            "st": nearby_stations(lat, lon, stations) if lat is not None and lon is not None else [],
            "lg": lightning_near(lat, lon, flashes, now) if lat is not None and lon is not None else None,
        })
    return rows


def append_rows(rows: list[dict], now: datetime, path: Path | None = None) -> int:
    """Agrega filas al archivo local y descarta lo anterior a KEEP_DAYS."""
    path = path or DATA_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    cutoff = (now - timedelta(days=KEEP_DAYS)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    kept = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("t", "") >= cutoff:
                    kept.append(line)
            except ValueError:
                continue
    existing = set()
    for line in kept:
        try:
            item = json.loads(line)
            existing.add((item.get("cam"), item.get("t")))
        except ValueError:
            continue
    kept.extend(json.dumps(row, separators=(",", ":"), ensure_ascii=False) for row in rows
                if (row.get("cam"), row.get("t")) not in existing)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return len(kept)


HOME_FRESH_MINUTES = 20
HOME_BASELINE_MIN_ROWS = 12
HOME_DAY_HOURS = range(8, 17)  # hora local en que el color de la imagen es confiable
HOME_FALLBACK_SATURATION = 30.0
HOME_GREY_RATIO = 0.6
HOME_DARK_RATIO = 0.85
HOME_COORD_DECIMALS = 2  # ~1 km: la ubicación exacta de la casa no se publica


def _median(values: list[float]) -> float:
    values = sorted(values)
    return values[len(values) // 2]


def estimate_home_rain(latest: dict, history: list[dict]) -> dict:
    """Estimación experimental de lluvia con una sola cámara, de día.

    No es una medición. Con historial de la misma cámara (de día) pide dos señales a la vez frente a
    lo habitual: color más apagado y suelo más oscuro (calle mojada). Sin historial usa solo un
    umbral fijo de color. No exige cielo azul porque esta cámara mira al suelo. De noche no opina.
    """
    features = latest.get("f", {})
    hour = latest.get("hour")
    if latest.get("q") != "usable" or hour not in HOME_DAY_HOURS:
        return {"estimate": "unknown", "reason": "night_or_low_quality"}
    saturation = float(features.get("saturation", 0))
    ground = float(features.get("ground_luma", 0))
    day_rows = [r for r in history
                if r.get("hour") in HOME_DAY_HOURS and r.get("q") == "usable" and "saturation" in r.get("f", {})]
    if len(day_rows) >= HOME_BASELINE_MIN_ROWS:
        base_sat = _median([float(r["f"]["saturation"]) for r in day_rows])
        base_ground = _median([float(r["f"].get("ground_luma", 0)) for r in day_rows])
        grey = saturation < base_sat * HOME_GREY_RATIO
        darker = base_ground > 0 and ground < base_ground * HOME_DARK_RATIO
        rain = grey and darker
        basis = "own_baseline"
        baseline = round(base_sat, 1)
    else:
        rain = saturation < HOME_FALLBACK_SATURATION
        basis = "fixed_threshold"
        baseline = None
    return {"estimate": "possible_rain" if rain else "no_rain", "saturation": round(saturation, 1),
            "baseline": baseline, "basis": basis}


def home_estimates(now: datetime, lat: float | None, lon: float | None, path: Path | None = None) -> list[dict]:
    """Una estimación por cámara de casa, a partir de su lectura más reciente."""
    path = path or DATA_PATH
    if not path.exists():
        return []
    by_cam: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if str(row.get("cam", "")).startswith("home-"):
            by_cam.setdefault(row["cam"], []).append(row)
    fresh_after = (now - timedelta(minutes=HOME_FRESH_MINUTES)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = []
    for cam, rows in sorted(by_cam.items()):
        rows.sort(key=lambda r: r["t"])
        latest = rows[-1]
        if latest["t"] < fresh_after:
            # Sin lectura reciente: la cámara sigue en el mapa pero marcada como sin conexión.
            item = {"id": cam, "t": latest["t"], "estimate": "unknown", "stale": True}
        else:
            item = {"id": cam, "t": latest["t"], **estimate_home_rain(latest, rows[:-1])}
        if lat is not None and lon is not None:
            item["lat"] = round(lat, HOME_COORD_DECIMALS)
            item["lon"] = round(lon, HOME_COORD_DECIMALS)
        result.append(item)
    return result


HOME_SILENCE_MINUTES = 30


def home_silence_message(now: datetime, state: dict, path: Path | None = None) -> dict | None:
    """Aviso si la tablet lleva más de 30 min sin mandar lecturas. Uno por apagón, no repite.

    `state` recuerda la última lectura por la que ya se avisó; cuando vuelve la tablet y luego se
    cae de nuevo, esa lectura cambia y se vuelve a avisar. No avisa si nunca hubo lecturas.
    """
    path = path or DATA_PATH
    if not path.exists():
        return None
    last = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if str(row.get("cam", "")).startswith("home-") and (last is None or row["t"] > last):
            last = row["t"]
    if last is None:
        return None
    try:
        last_time = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return None
    silent = (now - last_time).total_seconds() / 60
    if silent <= HOME_SILENCE_MINUTES or state.get("home_cam_alerted_for") == last:
        return None
    local = last_time.astimezone(LOCAL_TZ)
    return {
        "last": last,
        "title": "La tablet de las cámaras dejó de enviar",
        "message": f"Última lectura a las {local:%H:%M}. Revisa que la tablet tenga WiFi y batería, "
                   "y que Termux siga abierto con el programa corriendo.",
    }


def publish(path: Path = DATA_PATH) -> None:
    """Publica el archivo como único commit de la rama camera-training."""
    blob = subprocess.check_output(["git", "hash-object", "-w", str(path)], text=True).strip()
    tree = subprocess.check_output(["git", "mktree"], input=f"100644 blob {blob}\tcamera-features.jsonl\n", text=True).strip()
    message = f"Datos de cámaras {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}"
    commit = subprocess.check_output(
        ["git", "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
         "commit-tree", tree, "-m", message], text=True).strip()
    subprocess.run(["git", "push", "--force", "origin", f"{commit}:refs/heads/{BRANCH}"], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        if DATA_PATH.exists():
            publish()
            print("Datos de entrenamiento publicados.")
    else:
        print("Uso: camera_training.py publish")
