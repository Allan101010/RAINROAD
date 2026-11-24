#!/usr/bin/env python3
"""RainTrack CR - lector de cámaras de casa (para una tablet/teléfono Android con Termux).

Cada pocos minutos saca 3 fotos seguidas (medio segundo entre una y otra) de cada cámara por RTSP
(dentro de tu red de casa), calcula un resumen numérico (brillo, contraste, color, cuánto se mueve la
imagen...) y envía SOLO esos números a un tema privado de ntfy. Las fotos se borran al instante y
nunca salen de tu casa.

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
import urllib.error
import urllib.request
from array import array
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

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


BURST_FRAMES = 3
BURST_FPS = 2  # una foto cada medio segundo


def motion_features(frames: list[Image.Image]) -> dict:
    """Cuánto cambia la imagen entre fotos seguidas, solo en los 2/3 de abajo (suelo/calle).

    La lluvia cambia muchos puntos repartidos por toda la imagen; un gato o un carro cambian una
    zona. Se usa el menor de los cambios entre pares de fotos para que un objeto que pasa una vez
    no cuente como lluvia. "motion" = cambio medio; "motion_spread" = parte de la imagen (en
    bloques) que cambió de forma notable; "motion_median" = cambio del bloque típico (sube solo si
    cambia TODA la imagen, como con la lluvia de noche; una persona o un animal no lo mueven).
    """
    width, height, block = 128, 96, 8
    grays = [ImageOps.grayscale(f.convert("RGB").resize((width, height))).crop((0, height // 3, width, height))
             for f in frames]
    best = None
    for first, second in zip(grays, grays[1:]):
        diff = ImageChops.difference(first, second)
        mean = float(ImageStat.Stat(diff).mean[0])
        blocks = diff.resize((width // block, diff.height // block), Image.BOX)
        values = list(blocks.tobytes())  # imagen en grises: un byte por bloque
        spread = sum(1 for v in values if v >= 2.0) / max(1, len(values))
        exact = sorted(array("f", diff.convert("F").resize(blocks.size, Image.BOX).tobytes()))
        pair = (mean, spread, exact[len(exact) // 2] if exact else 0.0)
        if best is None or pair[0] < best[0]:
            best = pair
    if best is None:
        return {}
    return {"motion": round(best[0], 2), "motion_spread": round(best[1], 3), "motion_median": round(best[2], 2)}


# Zonas para las salpicaduras (fracciones de ancho/alto de la imagen). Por defecto, las de casa-patio:
# la calle (al aire libre, sin plantas) y la pared del corredor (techada). Se cambian por cámara en
# config.json con "zona_lluvia" y "zona_techada": [x0, y0, x1, y1].
DEFAULT_RAIN_ZONE = (0.0, 0.20, 0.55, 0.50)
DEFAULT_ROOF_ZONE = (0.80, 0.62, 0.98, 0.95)   # centro de la pared, lejos de la baranda y el goteo del techo
SPLASH_WIDTH = 640
SPLASH_DIFF = 12


def splash_features(frames: list[Image.Image], rain_zone=DEFAULT_RAIN_ZONE, roof_zone=DEFAULT_ROOF_ZONE) -> dict:
    """Gotas que salpican: puntitos que cambian entre fotos seguidas, mirados con más detalle (640 px).

    "splash_road" = % típico de puntos que cambian en los bloques de la zona al aire libre (la mediana de
    24 bloques, así un carro o una persona que ocupa pocos bloques no cuenta). "splash_ref" = % en la zona
    techada (ahí la lluvia no cae; sirve de comparación para el ruido de la cámara). Con lluvia la primera
    sube mucho y la segunda no.
    """
    if len(frames) < 2:
        return {}
    grays = []
    for frame in frames:
        w, h = frame.size
        size = (SPLASH_WIDTH, max(1, round(h * SPLASH_WIDTH / w)))
        grays.append(ImageOps.grayscale(frame.convert("RGB").resize(size)))
    W, H = grays[0].size

    def box(zone):
        return (int(zone[0] * W), int(zone[1] * H), int(zone[2] * W), int(zone[3] * H))

    def changed(img, area):
        hist = img.crop(area).histogram()
        return 100.0 * sum(hist[SPLASH_DIFF:]) / max(1, sum(hist))

    rx0, ry0, rx1, ry1 = box(rain_zone)
    cols, rows = 8, 3
    best = None
    for first, second in zip(grays, grays[1:]):
        diff = ImageChops.difference(first, second)
        blocks = []
        for r in range(rows):
            for c in range(cols):
                x0 = rx0 + (rx1 - rx0) * c // cols
                x1 = rx0 + (rx1 - rx0) * (c + 1) // cols
                y0 = ry0 + (ry1 - ry0) * r // rows
                y1 = ry0 + (ry1 - ry0) * (r + 1) // rows
                blocks.append(changed(diff, (x0, y0, x1, y1)))
        blocks.sort()
        road = blocks[len(blocks) // 2]
        pair = (road, changed(diff, box(roof_zone)))
        if best is None or pair[0] < best[0]:
            best = pair
    return {"splash_road": round(best[0], 2), "splash_ref": round(best[1], 2)}


def grab_burst(rtsp_url: str, timeout: int = 30) -> list[Image.Image]:
    """Saca varias fotos seguidas con una sola conexión. La URL (con tu contraseña) nunca se imprime."""
    with tempfile.TemporaryDirectory() as tmp:
        pattern = str(Path(tmp) / "f%d.jpg")
        command = ["ffmpeg", "-y", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", rtsp_url,
                   "-vf", f"fps={BURST_FPS}", "-frames:v", str(BURST_FRAMES), "-q:v", "3", pattern]
        subprocess.run(command, check=True, timeout=timeout, capture_output=True)
        frames = []
        for path in sorted(Path(tmp).glob("f*.jpg")):
            with Image.open(path) as img:
                img.load()
                frames.append(img.copy())
        if not frames:
            raise subprocess.CalledProcessError(1, "ffmpeg")
        return frames


def grab_frame(rtsp_url: str, timeout: int = 25) -> Image.Image:
    """Una sola foto (se conserva por compatibilidad)."""
    return grab_burst(rtsp_url, timeout)[0]


def analyze(frames: list[Image.Image], camera: dict | None = None) -> dict:
    """Resumen completo: la foto del medio para las características y todas para el movimiento."""
    camera = camera or {}
    features = extract_features(frames[len(frames) // 2])
    features.update(motion_features(frames))
    try:
        features.update(splash_features(frames, tuple(camera.get("zona_lluvia", DEFAULT_RAIN_ZONE)),
                                        tuple(camera.get("zona_techada", DEFAULT_ROOF_ZONE))))
    except Exception:
        pass
    return features


def build_message(camera_id: str, features: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    return {
        "v": 1,
        "cam": camera_id,
        "t": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "q": quality_of(features),
        "f": features,
    }


MIN_INTERVAL_SECONDS = 480   # ntfy
FAST_INTERVAL_SECONDS = 120  # lecturas al Worker


def send(topic: str, message: dict, server: str = "https://ntfy.sh") -> None:
    request = urllib.request.Request(
        f"{server}/{topic}", data=json.dumps(message, separators=(",", ":")).encode("utf-8"),
        headers={"Title": "RainTrack camara", "Priority": "min"}, method="POST")
    urllib.request.urlopen(request, timeout=20).read()


LAST_NTFY: dict[str, float] = {}


def run_round(config: dict) -> int:
    sent = 0
    for camera in config["cameras"]:
        name = camera["id"]
        try:
            features = analyze(grab_burst(camera["rtsp"]), camera)
            message = build_message(name, features)
            live = ""
            try:  # estimación al instante en el Worker (cada ronda)
                import tiempo_casa
                estimate = tiempo_casa.publish_home(message)
                live = f", en vivo: {estimate.get('estimate')}" if estimate else ""
            except Exception as exc:
                live = f", en vivo falló ({type(exc).__name__})"
            # ntfy guarda el historial del bot; su plan gratis aguanta ~250 mensajes al día: uno cada 8 min.
            if time.time() - LAST_NTFY.get(name, 0) >= MIN_INTERVAL_SECONDS - 30:
                send(config["ntfy_topic"], message)
                LAST_NTFY[name] = time.time()
            sent += 1
            print(f"{datetime.now():%H:%M:%S} {name}: enviado (luma {features['luma']}, color {features['saturation']}, movimiento {features.get('motion', '-')}, gotas {features.get('splash_road', '-')}/{features.get('splash_ref', '-')}{live})", flush=True)
        except subprocess.TimeoutExpired:
            print(f"{datetime.now():%H:%M:%S} {name}: la cámara no respondió a tiempo", flush=True)
        except subprocess.CalledProcessError:
            print(f"{datetime.now():%H:%M:%S} {name}: no se pudo leer la imagen (revisa la dirección RTSP)", flush=True)
        except urllib.error.HTTPError as exc:  # el servidor ntfy contestó con error: se anota el código
            wait = exc.headers.get("Retry-After") if exc.headers else None
            extra = f", reintentar en {wait} s" if wait else ""
            print(f"{datetime.now():%H:%M:%S} {name}: ntfy respondió {exc.code}{extra}", flush=True)
        except Exception as exc:  # una cámara con problemas no detiene a las demás
            print(f"{datetime.now():%H:%M:%S} {name}: error {type(exc).__name__}", flush=True)
    return sent


# Direcciones RTSP habituales de cámaras económicas (iCSee/XMeye y similares). {ip} y {clave} se rellenan.
CANDIDATE_PATHS = [
    "rtsp://{ip}:554/user=admin&password={clave}&channel=1&stream=0.sdp?real_stream",
    "rtsp://{ip}:554/user=admin&password={clave}&channel=1&stream=1.sdp?real_stream",
    "rtsp://admin:{clave}@{ip}:554/user=admin&password={clave}&channel=1&stream=0.sdp?real_stream",
    "rtsp://admin:{clave}@{ip}:554/h264/ch1/main/av_stream",
    "rtsp://admin:{clave}@{ip}:554/cam/realmonitor?channel=1&subtype=0",
    "rtsp://admin:{clave}@{ip}:554/Streaming/Channels/101",
    "rtsp://admin:{clave}@{ip}:554/11",
    "rtsp://admin:{clave}@{ip}:554/live/ch0",
    "rtsp://admin:{clave}@{ip}:554/",
]


def discover(ip: str, password: str) -> int:
    """Prueba direcciones comunes y dice cuál funciona. Nunca imprime la clave."""
    print(f"Probando direcciones comunes en {ip} (puede tardar un par de minutos)…")
    for number, template in enumerate(CANDIDATE_PATHS, start=1):
        url = template.format(ip=ip, clave=password)
        shown = template.format(ip=ip, clave="CLAVE")
        try:
            grab_burst(url, timeout=15)
        except subprocess.TimeoutExpired:
            print(f"  {number}. sin respuesta  {shown}")
            continue
        except subprocess.CalledProcessError:
            print(f"  {number}. no funciona    {shown}")
            continue
        print(f"  {number}. FUNCIONA       {shown}")
        print("\nCopia esa dirección en config.json (cambia CLAVE por tu clave).")
        return 0
    print("\nNinguna funcionó. Revisa: IP correcta, que la cámara tenga RTSP/ONVIF activado en su app, y la clave.")
    return 1


def upload_debug_frames(config: dict) -> int:
    """Sube dos fotos seguidas (medio segundo de diferencia) al Worker para ajustar las zonas de gotas."""
    import io
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import aviones_casa
    for camera in config["cameras"]:
        frames = grab_burst(camera["rtsp"])
        print(camera["id"], analyze(frames, camera).get("splash_road"), analyze(frames, camera).get("splash_ref"))
        for i, frame in enumerate(frames[:2], 1):
            out = io.BytesIO()
            frame.convert("RGB").resize((1280, round(frame.height * 1280 / frame.width))).save(out, "JPEG", quality=90)
            req = urllib.request.Request(aviones_casa.WORKER + "/ia", data=out.getvalue(), method="POST", headers={
                **aviones_casa.UA, "Content-Type": "image/jpeg", "X-Clave": aviones_casa._key(),
                "X-Cam": f"debug-{camera['id']}-{i}"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    print("foto", i, "subida:", r.read().decode("utf-8")[:80])
            except Exception as exc:
                print("foto", i, "falló:", exc)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--una-vez", action="store_true")
    parser.add_argument("--descubrir", metavar="IP", help="busca la dirección RTSP que funciona en esa cámara")
    parser.add_argument("--clave", default="", help="clave de la cámara (vacía si nunca la cambiaste)")
    parser.add_argument("--subir-fotos", action="store_true",
                        help="sube 2 fotos seguidas de cada cámara al Worker para revisar las zonas (no se publican)")
    args = parser.parse_args()
    if args.descubrir:
        return discover(args.descubrir, args.clave)
    if not CONFIG_PATH.exists():
        print("Falta config.json: copia config.ejemplo.json a config.json y complétalo.")
        return 1
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if args.subir_fotos:
        return upload_debug_frames(config)
    # Lectura cada 2 min (va al Worker); a ntfy solo una cada 8 min (ver run_round).
    interval = max(FAST_INTERVAL_SECONDS, int(config.get("intervalo_rapido_segundos", FAST_INTERVAL_SECONDS)))
    if not args.una_vez:
        try:  # puente de aviones para la app (hilo aparte; si falla, las cámaras siguen igual)
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import aviones_casa
            aviones_casa.start(config)
            import tiempo_casa
            tiempo_casa.start(config)
            import ia_camaras
            ia_camaras.start(config)
            import bot_tablet
            bot_tablet.start(config)
        except Exception as exc:
            print(f"aviones: no se pudo iniciar ({exc})", flush=True)
    while True:
        run_round(config)
        if args.una_vez:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
