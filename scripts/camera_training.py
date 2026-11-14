#!/usr/bin/env python3
"""Recolección de datos para aprender a detectar lluvia con las cámaras.

Por cada cámara en línea guarda un resumen numérico de la imagen (no la foto) junto con lo que
midieron las estaciones cercanas y los rayos de los últimos minutos. Con eso se puede medir,
sin etiquetar nada a mano, si una cámara "ve" la lluvia. No afecta nada visible en la app.
"""
from __future__ import annotations

import json
import math
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
    kept.extend(json.dumps(row, separators=(",", ":"), ensure_ascii=False) for row in rows)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return len(kept)


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
