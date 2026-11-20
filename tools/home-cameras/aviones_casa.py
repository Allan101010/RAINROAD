"""Puente de aviones para RainTrack CR.

Corre dentro de camaras_casa.py (un hilo aparte) en la tablet de la casa. Solo trabaja cuando alguien
tiene encendida la capa "Aviones" en la app: pregunta al Worker cada 20 s si hay interés y, si lo hay,
baja de adsb.fi los aviones alrededor de Costa Rica cada 15 s y se los sube al Worker.

adsb.fi bloquea a los servidores de nube pero acepta conexiones de casa; por eso este puente.
La clave para publicar se crea sola la primera vez y se guarda fuera del repositorio.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

WORKER = "https://raintrack-aviones.raintrackcr.workers.dev"
SOURCE = "https://opendata.adsb.fi/api/v2/lat/9.75/lon/-84.2/dist/250"   # centro de Costa Rica, 250 millas náuticas
KEY_PATH = Path.home() / ".raintrack_aviones_clave"
POLL_DEMAND_S = 20
SEND_EVERY_S = 15
UA = {"User-Agent": "RainTrackCR-tablet/1.0 (uso personal)"}


def _log(text: str) -> None:
    print(f"{datetime.now():%H:%M:%S} aviones: {text}", flush=True)


def _key() -> str:
    if not KEY_PATH.exists():
        KEY_PATH.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        KEY_PATH.chmod(0o600)
    return KEY_PATH.read_text(encoding="utf-8").strip()


def _get_json(url: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _publish(worker: str, key: str, payload: dict) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(worker + "/publicar", data=body, method="POST",
                                 headers={**UA, "Content-Type": "application/json", "X-Clave": key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def loop(worker: str = WORKER) -> None:
    key = _key()
    active = False
    last_error = ""
    while True:
        try:
            wanted = bool(_get_json(worker + "/demanda").get("wanted"))
            if wanted != active:
                _log("alguien está mirando, enviando" if wanted else "nadie mirando, en pausa")
                active = wanted
            if not wanted:
                time.sleep(POLL_DEMAND_S)
                continue
            data = _get_json(SOURCE)
            planes = data.get("aircraft") or data.get("ac") or []
            _publish(worker, key, {"ac": planes, "src": "adsb.fi"})
            last_error = ""
            time.sleep(SEND_EVERY_S)
        except Exception as exc:  # nunca debe tumbar el programa de las cámaras
            text = f"{type(exc).__name__}: {getattr(exc, 'code', '') or exc}"
            if text != last_error:
                _log("error " + text)
                last_error = text
            time.sleep(60)


def start(config: dict) -> None:
    if config.get("aviones") is False:
        return
    worker = str(config.get("aviones_worker") or WORKER).rstrip("/")
    threading.Thread(target=loop, args=(worker,), name="aviones", daemon=True).start()
    _log("puente listo")


if __name__ == "__main__":
    loop()
