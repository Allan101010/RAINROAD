"""El bot de GitHub (cámaras públicas, estaciones, temblores) corriendo en la tablet.

GitHub desactivó las Actions del repositorio, así que esto hace lo mismo desde aquí y publica en el Worker
de Cloudflare (POST /datos/<nombre>); la app lee de ahí y, si no hay nada fresco, de GitHub.
  - cámaras y estaciones: scripts/monitor_cameras.py cada 10 min  → "camaras" y "catalogo"
  - temblores: scripts/quakes.py (USGS, EMSC, OVSICORI) cada ~30 s → "temblores"
Los archivos de trabajo quedan en ~/raintrack_bot (fuera del repositorio, para no estorbar a git pull).
Los rayos (GLM) no se pasan: piden numpy y netCDF4, difíciles en Termux.
Apagar: "bot_en_tablet": false en config.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import aviones_casa

REPO = Path(__file__).resolve().parents[2]
WORK = Path.home() / "raintrack_bot"
CAMERAS_EVERY_S = 600
CAMERAS_TIMEOUT_S = 900
QUAKES_RUN_S = 1800


def _log(text: str) -> None:
    aviones_casa._log("bot: " + text)


def _upload(worker: str, name: str, path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        aviones_casa._post(worker, "/datos/" + name, aviones_casa._key(), payload)
        return True
    except Exception as exc:
        _log(f"no se pudo publicar {name} ({type(exc).__name__}: {exc})")
        return False


def _seed() -> None:
    """Primera vez: parte de los JSON que dejó el bot de GitHub, para no perder el historial reciente."""
    WORK.mkdir(exist_ok=True)
    for name in ("camera-alerts.json", "camera-catalog.json"):
        if not (WORK / name).exists() and (REPO / name).exists():
            shutil.copy(REPO / name, WORK / name)


def _home_env(config: dict) -> dict:
    """La cámara de la casa: el bot de GitHub la leía de sus secretos; aquí sale de la config de la tablet."""
    env = dict(os.environ)
    env["HOME_CAM_TOPIC"] = str(config.get("ntfy_topic") or "")
    for key, name in (("casa_lat", "HOME_CAM_LAT"), ("casa_lon", "HOME_CAM_LON"), ("alerta_topic", "HOME_CAM_ALERT_TOPIC")):
        if config.get(key) not in (None, ""):
            env[name] = str(config[key])
    return env


def cameras_loop(worker: str, config: dict) -> None:
    last_error = ""
    env = _home_env(config)
    while True:
        started = time.time()
        try:
            subprocess.run([sys.executable, str(REPO / "scripts" / "monitor_cameras.py")], cwd=WORK, env=env,
                           timeout=CAMERAS_TIMEOUT_S, check=True, capture_output=True, text=True)
            ok = _upload(worker, "camaras", WORK / "camera-alerts.json")
            ok = _upload(worker, "catalogo", WORK / "camera-catalog.json") and ok
            if ok:
                _log(f"cámaras publicadas ({round(time.time() - started)} s)")
            last_error = ""
        except subprocess.CalledProcessError as exc:
            text = ((exc.stderr or exc.stdout or "").strip().splitlines() or ["sin detalle"])[-1][:200]
            if text != last_error:
                _log("monitor de cámaras falló: " + text)
                last_error = text
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            if text != last_error:
                _log("monitor de cámaras: " + text)
                last_error = text
        time.sleep(max(60, CAMERAS_EVERY_S - (time.time() - started)))


def quakes_loop(worker: str) -> None:
    out = WORK / "quakes.json"
    last_error = ""
    while True:
        proc = None
        try:
            proc = subprocess.Popen([sys.executable, str(REPO / "scripts" / "quakes.py"), "--duration", str(QUAKES_RUN_S),
                                     "--interval", "30", "--no-publish", "--out", str(out)],
                                    cwd=WORK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            seen = 0.0
            while proc.poll() is None:
                time.sleep(10)
                if out.exists() and out.stat().st_mtime > seen:
                    seen = out.stat().st_mtime
                    _upload(worker, "temblores", out)
            if out.exists() and out.stat().st_mtime > seen:
                _upload(worker, "temblores", out)
            last_error = ""
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            if text != last_error:
                _log("temblores: " + text)
                last_error = text
            if proc and proc.poll() is None:
                proc.kill()
        time.sleep(5)


def start(config: dict) -> None:
    if config.get("bot_en_tablet") is False:
        return
    worker = str(config.get("aviones_worker") or aviones_casa.WORKER).rstrip("/")
    _seed()
    threading.Thread(target=cameras_loop, args=(worker, config), name="bot-camaras", daemon=True).start()
    threading.Thread(target=quakes_loop, args=(worker,), name="bot-temblores", daemon=True).start()
    _log("listo (cámaras cada 10 min, temblores cada ~30 s)")
