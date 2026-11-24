"""Puente de aviones para RainTrack CR.

Corre dentro de camaras_casa.py (un hilo aparte) en la tablet de la casa. Solo trabaja cuando alguien
tiene encendida la capa "Aviones" en la app: pregunta al Worker cada 20 s si hay interés y, si lo hay,
baja de adsb.fi los aviones alrededor de Costa Rica cada 15 s y se los sube al Worker.
Además, cada 10 min guarda el viento y la temperatura que reportan los aviones (para estimar hacia
dónde se mueve la lluvia).

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
WIND_EVERY_S = 600   # viento de los aviones: se guarda cada 10 min aunque nadie mire la capa
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


def wind_obs(planes: list) -> list:
    """Aviones que reportan viento (calculado por los receptores a partir de rumbo y velocidad)."""
    out = []
    for a in planes:
        if a.get("wd") is None or a.get("ws") is None or a.get("lat") is None or a.get("lon") is None:
            continue
        alt = a.get("alt_baro")
        if alt == "ground":
            continue
        out.append({"hex": a.get("hex"), "lat": a.get("lat"), "lon": a.get("lon"), "alt": alt if alt is not None else a.get("alt_geom"),
                    "wd": a.get("wd"), "ws": a.get("ws"), "oat": a.get("oat"), "track": a.get("track"), "gs": a.get("gs"),
                    "seen": a.get("seen_pos", a.get("seen"))})
    return out


ARCHIVE_DIR = Path.home() / "raintrack_vientos_archivo"
ARCHIVE_FIELDS = ("t", "hex", "lat", "lon", "alt", "wd", "ws", "oat", "track", "gs")


def _archive(rows: list, month: str) -> None:
    """Guarda los vientos en la tablet (un archivo por mes) para estudiarlos cuando vuelva la época lluviosa."""
    if not rows:
        return
    ARCHIVE_DIR.mkdir(exist_ok=True)
    with open(ARCHIVE_DIR / f"{month}.jsonl", "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps([r.get(k) for k in ARCHIVE_FIELDS], separators=(",", ":")) + "\n")


def _backfill(worker: str) -> None:
    """Una sola vez: copia a la tablet lo que el Worker ya tenía guardado (hasta 30 días)."""
    marker = ARCHIVE_DIR / "listo.txt"
    if marker.exists():
        return
    rows = _get_json(worker + "/vientos?horas=720", timeout=60).get("rows", [])
    by_month: dict = {}
    for r in rows:
        by_month.setdefault(time.strftime("%Y-%m", time.localtime(r["t"])), []).append(r)
    for month, part in by_month.items():
        _archive(part, month)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    marker.write_text(f"{len(rows)} lecturas copiadas del Worker\n", encoding="utf-8")
    _log(f"archivo de vientos creado ({len(rows)} lecturas anteriores)")


def _post(worker: str, path: str, key: str, payload: dict) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(worker + path, data=body, method="POST",
                                 headers={**UA, "Content-Type": "application/json", "X-Clave": key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def loop(worker: str = WORKER) -> None:
    key = _key()
    try:
        _backfill(worker)
    except Exception as exc:
        _log(f"no se pudo copiar el historial de vientos ({type(exc).__name__}); se guarda desde ahora")
    active = False
    last_error = ""
    last_wind = 0.0
    while True:
        try:
            if time.time() - last_wind >= WIND_EVERY_S:
                last_wind = time.time()
                obs = wind_obs((lambda d: d.get("aircraft") or d.get("ac") or [])(_get_json(SOURCE)))
                if obs:
                    _post(worker, "/vientos", key, {"obs": obs})
                    now = int(time.time())
                    _archive([{**o, "t": now} for o in obs], time.strftime("%Y-%m"))
            wanted = bool(_get_json(worker + "/demanda").get("wanted"))
            if wanted != active:
                _log("alguien está mirando, enviando" if wanted else "nadie mirando, en pausa")
                active = wanted
            if not wanted:
                time.sleep(POLL_DEMAND_S)
                continue
            data = _get_json(SOURCE)
            planes = data.get("aircraft") or data.get("ac") or []
            _post(worker, "/publicar", key, {"ac": planes, "src": "adsb.fi"})
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
