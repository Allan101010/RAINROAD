#!/usr/bin/env python3
"""RainTrack CR - lector de cámaras de casa (para una tablet/teléfono Android con Termux).

Cada pocos minutos saca UNA foto de cada cámara por RTSP (dentro de tu red de casa), calcula un
resumen numérico (brillo, contraste, cielo, bordes...) y envía SOLO esos números a un tema
privado de ntfy. La foto se borra al instante y nunca sale de tu casa.

Uso:  python camaras_casa.py            (queda corriendo)
      python camaras_casa.py --una-vez  (una sola ronda, para probar)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat

CONFIG_PATH = Path(__file__).with_name("config.json")


def extract_features(image: Image.Image) -> dict:
    """Misma fórmula que usa el bot con las cámaras públicas (scripts/camera_training.py)."""
    width, height = 128, 96
    rgb = image.convert("RGB").resize((width, height))
    gray = ImageOps.grayscale(rgb)
    third = height // 3

    def mean_std(im):
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


def quality_of(features: dict) -> str:
    if features["luma"] < 23 and features["bright_frac"] < 0.02:
        return "low_visibility"
    return "usable"


def grab_frame(rtsp_url: str, timeout: int = 25) -> Image.Image:
    """Saca un solo fotograma con ffmpeg. La URL (con tu contraseña) nunca se imprime."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "frame.jpg"
        command = ["ffmpeg", "-y", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", rtsp_url,
                   "-frames:v", "1", "-q:v", "3", str(target)]
        subprocess.run(command, check=True, timeout=timeout, capture_output=True)
        with Image.open(target) as img:
            img.load()
            return img.copy()


def build_message(camera_id: str, features: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    return {
        "v": 1,
        "cam": camera_id,
        "t": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "q": quality_of(features),
        "f": features,
    }


def send(topic: str, message: dict, server: str = "https://ntfy.sh") -> None:
    request = urllib.request.Request(
        f"{server}/{topic}", data=json.dumps(message, separators=(",", ":")).encode("utf-8"),
        headers={"Title": "RainTrack camara", "Priority": "min"}, method="POST")
    urllib.request.urlopen(request, timeout=20).read()


def run_round(config: dict) -> int:
    sent = 0
    for camera in config["cameras"]:
        name = camera["id"]
        try:
            features = extract_features(grab_frame(camera["rtsp"]))
            send(config["ntfy_topic"], build_message(name, features))
            sent += 1
            print(f"{datetime.now():%H:%M:%S} {name}: enviado (luma {features['luma']}, contraste {features['contrast']})")
        except subprocess.TimeoutExpired:
            print(f"{datetime.now():%H:%M:%S} {name}: la cámara no respondió a tiempo")
        except subprocess.CalledProcessError:
            print(f"{datetime.now():%H:%M:%S} {name}: no se pudo leer la imagen (revisa la dirección RTSP)")
        except Exception as exc:  # una cámara con problemas no detiene a las demás
            print(f"{datetime.now():%H:%M:%S} {name}: error {type(exc).__name__}")
    return sent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--una-vez", action="store_true")
    args = parser.parse_args()
    if not CONFIG_PATH.exists():
        print("Falta config.json: copia config.ejemplo.json a config.json y complétalo.")
        return 1
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    interval = int(config.get("intervalo_segundos", 300))
    while True:
        run_round(config)
        if args.una_vez:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
