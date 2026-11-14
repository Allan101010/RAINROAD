#!/usr/bin/env python3
"""Rayos de Costa Rica a partir del GLM (Geostationary Lightning Mapper) de NOAA GOES-19.

El satélite publica un archivo NetCDF cada 20 s en un bucket público de AWS. Este script se
queda corriendo unos minutos, baja los archivos nuevos, filtra Costa Rica y publica un JSON
pequeño (lightning.json) en la rama `lightning-data` para que la app lo lea.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BUCKET = "noaa-goes19"
PREFIX = "GLM-L2-LCFA"
BBOX = {"lat_min": 4.5, "lat_max": 12.5, "lon_min": -88.5, "lon_max": -81.5}
KEEP_MINUTES = 60
HTTP_TIMEOUT = 30
PUBLISH_BRANCH = "lightning-data"
HEARTBEAT_SECONDS = 120


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_keys(session: requests.Session, when: datetime) -> list[tuple[str, int]]:
    prefix = f"{PREFIX}/{when.year}/{when.timetuple().tm_yday:03d}/{when.hour:02d}/"
    url = f"https://{BUCKET}.s3.amazonaws.com/?list-type=2&prefix={prefix}"
    response = session.get(url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    keys = re.findall(r"<Key>([^<]+)</Key>", response.text)
    sizes = re.findall(r"<Size>(\d+)</Size>", response.text)
    return [(key, int(size)) for key, size in zip(keys, sizes) if key.endswith(".nc")]


def parse_since(units: str) -> datetime | None:
    match = re.search(r"since\s+(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", units or "")
    if not match:
        return None
    return datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}").replace(tzinfo=timezone.utc)


def parse_glm_file(data: bytes) -> list[list[float]]:
    """Devuelve [[epoch_s, lat, lon], ...] de los destellos de Costa Rica en un archivo GLM."""
    import numpy as np
    from netCDF4 import Dataset

    dataset = Dataset("glm.nc", mode="r", memory=data)
    try:
        if "flash_lat" not in dataset.variables:
            return []
        lat = np.ma.filled(dataset.variables["flash_lat"][:], np.nan).astype(float)
        lon = np.ma.filled(dataset.variables["flash_lon"][:], np.nan).astype(float)
        offset_var = dataset.variables["flash_time_offset_of_first_event"]
        offset = np.ma.filled(offset_var[:], np.nan).astype(float)
        base = parse_since(getattr(offset_var, "units", ""))
        if base is None:
            product_time = float(np.ma.filled(dataset.variables["product_time"][:], np.nan))
            base = datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(seconds=product_time)
        quality_ok = np.ones(lat.shape, dtype=bool)
        if "flash_quality_flag" in dataset.variables:
            quality = np.ma.filled(dataset.variables["flash_quality_flag"][:], 0)
            quality_ok = quality == 0
        inside = (
            (lat >= BBOX["lat_min"]) & (lat <= BBOX["lat_max"])
            & (lon >= BBOX["lon_min"]) & (lon <= BBOX["lon_max"])
            & quality_ok & np.isfinite(offset)
        )
        epoch = base.timestamp()
        return [
            [round(epoch + float(offset[i]), 1), round(float(lat[i]), 3), round(float(lon[i]), 3)]
            for i in np.nonzero(inside)[0]
        ]
    finally:
        dataset.close()


def publish(path: Path) -> None:
    """Publica el archivo como único commit de la rama lightning-data (sin acumular historial)."""
    blob = subprocess.check_output(["git", "hash-object", "-w", str(path)], text=True).strip()
    tree = subprocess.check_output(["git", "mktree"], input=f"100644 blob {blob}\tlightning.json\n", text=True).strip()
    env_msg = f"Rayos GLM {utc_now().strftime('%Y-%m-%d %H:%M:%SZ')}"
    commit = subprocess.check_output(
        ["git", "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
         "commit-tree", tree, "-m", env_msg], text=True).strip()
    subprocess.run(["git", "push", "--force", "origin", f"{commit}:refs/heads/{PUBLISH_BRANCH}"], check=True,
                   capture_output=True, text=True)


def load_previous(path: Path) -> list[list[float]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [f for f in data.get("flashes", []) if isinstance(f, list) and len(f) == 3]
    except (OSError, ValueError):
        return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=570, help="segundos que se queda corriendo")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--out", default="lightning.json")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    out = Path(args.out)
    flashes = load_previous(out)
    seen: set[str] = set()
    session = requests.Session()
    session.headers["User-Agent"] = "RainTrackCR-lightning/1.0 (https://github.com/Allan101010/RAINROAD)"
    started = time.monotonic()
    last_publish = 0.0
    latest_file_time = None
    first_pass = True
    while True:
        changed = False
        try:
            now = utc_now()
            hours = {(now - timedelta(minutes=m)).replace(minute=0, second=0, microsecond=0) for m in (0, 10)}
            keys = []
            for hour in sorted(hours):
                keys.extend(list_keys(session, hour))
            keys.sort()
            # Primera vuelta: solo los últimos ~15 min (45 archivos); después, lo nuevo.
            candidates = [k for k in keys if k[0] not in seen]
            if first_pass:
                candidates = candidates[-45:]
                seen.update(k[0] for k in keys)
            for key, _size in candidates:
                seen.add(key)
                try:
                    body = session.get(f"https://{BUCKET}.s3.amazonaws.com/{key}", timeout=HTTP_TIMEOUT).content
                    found = parse_glm_file(body)
                except Exception as exc:  # un archivo dañado no detiene el ciclo
                    logging.warning("GLM %s: %s", key[-40:], exc)
                    continue
                stamp = re.search(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})", key)
                if stamp:
                    year, doy, hh, mm, ss = (int(x) for x in stamp.groups())
                    latest_file_time = (datetime(year, 1, 1, tzinfo=timezone.utc)
                                        + timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss))
                if found:
                    flashes.extend(found)
                    changed = True
                logging.info("GLM %s -> %s destellos en Costa Rica", key[-52:], len(found))
            first_pass = False
        except Exception as exc:
            logging.warning("Ciclo GLM falló: %s", exc)

        cutoff = utc_now().timestamp() - KEEP_MINUTES * 60
        flashes = sorted({tuple(f) for f in flashes if f[0] >= cutoff})
        flashes = [list(f) for f in flashes]
        due = time.monotonic() - last_publish >= HEARTBEAT_SECONDS
        if changed or due:
            payload = {
                "generated_at": utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "source": "NOAA GOES-19 GLM (Geostationary Lightning Mapper)",
                "latest_file_time": latest_file_time.isoformat().replace("+00:00", "Z") if latest_file_time else None,
                "bbox": BBOX,
                "keep_minutes": KEEP_MINUTES,
                "flashes": flashes,
            }
            out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            if not args.no_publish:
                try:
                    publish(out)
                    last_publish = time.monotonic()
                    logging.info("Publicado: %s destellos", len(flashes))
                except Exception as exc:
                    logging.warning("No se pudo publicar: %s", exc)
            else:
                last_publish = time.monotonic()
                logging.info("(sin publicar) %s destellos", len(flashes))
        if time.monotonic() - started + args.interval > args.duration:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
