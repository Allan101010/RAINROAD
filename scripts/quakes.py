#!/usr/bin/env python3
"""Temblores de Costa Rica y la región a partir de USGS y EMSC (fuentes abiertas, sin clave).

Se queda corriendo unos minutos (como el de rayos), lee las dos fuentes, junta los duplicados,
marca los de Costa Rica y publica un JSON pequeño (quakes.json) en la rama `quakes-data` para que
la app lo lea. Si existe el tema ntfy `QUAKE_ALERT_TOPIC`, también manda un aviso al celular.

IMPORTANTE: esto informa DESPUÉS del sismo (minutos). No es una alerta temprana.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

USGS_HOUR = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
USGS_DAY = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
EMSC_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
BBOX = {"lat_min": 4.5, "lat_max": 13.5, "lon_min": -89.0, "lon_max": -80.5}
CR_BOX = {"lat_min": 8.0, "lat_max": 11.3, "lon_min": -86.0, "lon_max": -82.5}
MIN_MAG = 3.5
KEEP_HOURS = 48
ALERT_CR_MIN = 4.0     # aviso al celular: Costa Rica desde esta magnitud
ALERT_ANY_MIN = 5.0    # aviso al celular: cualquier sismo de la región desde esta magnitud
ALERT_MAX_AGE_MIN = 45  # no avisa de sismos más viejos que esto (evita avisos tardíos)
MATCH_SECONDS = 90
MATCH_KM = 80
MATCH_MAG = 1.2
HTTP_TIMEOUT = 25
PUBLISH_BRANCH = "quakes-data"
HEARTBEAT_SECONDS = 120
USER_AGENT = "RainTrackCR-quakes/1.0 (https://github.com/Allan101010/RAINROAD)"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180
    a = math.sin((lat2 - lat1) * rad / 2) ** 2 + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin((lon2 - lon1) * rad / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def in_box(lat: float, lon: float, box: dict) -> bool:
    return box["lat_min"] <= lat <= box["lat_max"] and box["lon_min"] <= lon <= box["lon_max"]


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_usgs(data: dict) -> list[dict]:
    """Eventos de un GeoJSON de USGS (feed o consulta FDSN), ya filtrados por región y magnitud."""
    events = []
    for feature in (data or {}).get("features", []):
        try:
            props = feature.get("properties") or {}
            lon, lat, depth = feature["geometry"]["coordinates"][:3]
            mag = _number(props.get("mag"))
            when = _number(props.get("time"))
            lat, lon = _number(lat), _number(lon)
            if mag is None or when is None or lat is None or lon is None:
                continue
            if props.get("type") not in (None, "earthquake"):
                continue
            if mag < MIN_MAG or not in_box(lat, lon, BBOX):
                continue
            events.append({"src": "usgs", "t": when / 1000.0, "lat": lat, "lon": lon, "mag": mag,
                           "depth": _number(depth), "place": str(props.get("place") or "")})
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return events


def parse_emsc(data: dict) -> list[dict]:
    """Eventos de la consulta FDSN (JSON) del EMSC."""
    events = []
    for feature in (data or {}).get("features", []):
        try:
            props = feature.get("properties") or {}
            coords = (feature.get("geometry") or {}).get("coordinates") or []
            lat = _number(props.get("lat", coords[1] if len(coords) > 1 else None))
            lon = _number(props.get("lon", coords[0] if coords else None))
            mag = _number(props.get("mag"))
            stamp = str(props.get("time", ""))
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if mag is None or lat is None or lon is None:
                continue
            if mag < MIN_MAG or not in_box(lat, lon, BBOX):
                continue
            depth = _number(props.get("depth"))
            if depth is None and len(coords) > 2:
                depth = abs(_number(coords[2]) or 0)
            events.append({"src": "emsc", "t": when.timestamp(), "lat": lat, "lon": lon, "mag": mag,
                           "depth": depth, "place": str(props.get("flynn_region") or "").title()})
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return events


def is_costa_rica(event: dict) -> bool:
    text = str(event.get("place", "")).upper()
    if "COSTA RICA" in text:
        return True
    if any(name in text for name in ("NICARAGUA", "PANAMA", "COLOMBIA", "HONDURAS", "EL SALVADOR")):
        return False
    return in_box(event["lat"], event["lon"], CR_BOX)


def same_event(a: dict, b: dict) -> bool:
    return (abs(a["t"] - b["t"]) <= MATCH_SECONDS
            and distance_km(a["lat"], a["lon"], b["lat"], b["lon"]) <= MATCH_KM
            and abs(a["mag"] - b["mag"]) <= MATCH_MAG)


def _recompute(event: dict) -> None:
    mags = event["mags"]
    event["mag"] = round(sum(mags.values()) / len(mags), 1)
    event["src"] = sorted(mags)
    event["cr"] = is_costa_rica(event)


def merge_into(store: list[dict], incoming: list[dict], now_epoch: float) -> bool:
    """Suma eventos nuevos al conjunto; junta los de USGS y EMSC que son el mismo sismo."""
    changed = False
    for raw in incoming:
        source = raw["src"]
        match = next((e for e in store if same_event(e, raw)), None)
        if match is None:
            event = {"t": raw["t"], "lat": raw["lat"], "lon": raw["lon"], "depth": raw["depth"],
                     "place": raw["place"], "mags": {source: round(raw["mag"], 1)}, "first_seen": now_epoch}
            _recompute(event)
            store.append(event)
            changed = True
            continue
        before = (match["mags"].get(source), match["depth"], match["place"])
        match["mags"][source] = round(raw["mag"], 1)
        if source == "usgs" or not match["place"]:  # USGS da un lugar más legible
            match["place"] = raw["place"] or match["place"]
            match["lat"], match["lon"] = raw["lat"], raw["lon"]
            if raw["depth"] is not None:
                match["depth"] = raw["depth"]
        elif match["depth"] is None:
            match["depth"] = raw["depth"]
        match["t"] = min(match["t"], raw["t"])
        _recompute(match)
        if before != (match["mags"].get(source), match["depth"], match["place"]):
            changed = True
    return changed


def prune(store: list[dict], now_epoch: float) -> list[dict]:
    cutoff = now_epoch - KEEP_HOURS * 3600
    return sorted((e for e in store if e["t"] >= cutoff and e["mag"] >= MIN_MAG), key=lambda e: -e["t"])


def alert_message(event: dict, now_epoch: float) -> dict:
    minutes = max(0, round((now_epoch - event["t"]) / 60))
    where = event["place"] or "Costa Rica y alrededores"
    depth = f" Profundidad: {event['depth']:.0f} km." if event.get("depth") is not None else ""
    sources = " y ".join(s.upper() for s in event["src"])
    body = (f"{where}.{depth} Hace {minutes} min · fuente: {sources}.\n"
            "Este aviso llega después del sismo; no es una alerta temprana. Magnitud preliminar, puede cambiar.")
    if event["cr"]:
        return {"title": f"🚨 TEMBLOR EN COSTA RICA · M{event['mag']:.1f}", "message": body,
                "tags": ["rotating_light"], "priority": 4 if event["mag"] >= 5 else 3}
    return {"title": f"🌎 Sismo M{event['mag']:.1f} en la región", "message": body, "tags": ["earth_americas"], "priority": 3}


def should_alert(event: dict, now_epoch: float) -> bool:
    if event.get("notified") or now_epoch - event["t"] > ALERT_MAX_AGE_MIN * 60:
        return False
    return (event["cr"] and event["mag"] >= ALERT_CR_MIN) or event["mag"] >= ALERT_ANY_MIN


def send_alerts(store: list[dict], session: requests.Session, topic: str, now_epoch: float) -> int:
    """Un aviso por sismo (se marca en el propio JSON). Un fallo de ntfy no detiene el ciclo."""
    sent = 0
    for event in store:
        if not should_alert(event, now_epoch):
            continue
        payload = {"topic": topic, **alert_message(event, now_epoch)}
        try:
            response = session.post("https://ntfy.sh", data=json.dumps(payload).encode("utf-8"), timeout=15)
            response.raise_for_status()
            event["notified"] = True
            sent += 1
        except requests.RequestException as exc:
            logging.warning("No se pudo enviar el aviso de temblor: %s", exc)
    return sent


def fetch_json(session: requests.Session, url: str, params: dict | None = None) -> dict | None:
    try:
        response = session.get(url, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logging.warning("No se pudo leer %s: %s", url.split("/")[2], exc)
        return None


def fetch_emsc(session: requests.Session, now: datetime) -> list[dict] | None:
    params = {
        "format": "json", "orderby": "time", "limit": 200, "minmag": MIN_MAG,
        "minlat": BBOX["lat_min"], "maxlat": BBOX["lat_max"], "minlon": BBOX["lon_min"], "maxlon": BBOX["lon_max"],
        "start": (now - timedelta(hours=KEEP_HOURS)).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    data = fetch_json(session, EMSC_URL, params)
    return None if data is None else parse_emsc(data)


def publish(path: Path) -> None:
    blob = subprocess.check_output(["git", "hash-object", "-w", str(path)], text=True).strip()
    tree = subprocess.check_output(["git", "mktree"], input=f"100644 blob {blob}\tquakes.json\n", text=True).strip()
    commit = subprocess.check_output(
        ["git", "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
         "commit-tree", tree, "-m", f"Temblores {utc_now().strftime('%Y-%m-%d %H:%M:%SZ')}"], text=True).strip()
    subprocess.run(["git", "push", "--force", "origin", f"{commit}:refs/heads/{PUBLISH_BRANCH}"], check=True,
                   capture_output=True, text=True)


def load_previous(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    store = []
    for item in data.get("quakes", []):
        try:
            event = {"t": float(item["t"]), "lat": float(item["lat"]), "lon": float(item["lon"]),
                     "depth": item.get("depth"), "place": str(item.get("place", "")),
                     "mags": {str(k): float(v) for k, v in item["mags"].items()},
                     "first_seen": float(item.get("first_seen", item["t"])), "notified": bool(item.get("notified"))}
            _recompute(event)
            store.append(event)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return store


def build_payload(store: list[dict], sources_ok: dict) -> dict:
    return {
        "generated_at": utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "USGS + EMSC",
        "min_mag": MIN_MAG, "keep_hours": KEEP_HOURS, "bbox": BBOX, "sources_ok": sources_ok,
        "quakes": [{"t": int(e["t"]), "lat": round(e["lat"], 3), "lon": round(e["lon"], 3), "mag": e["mag"],
                    "depth": None if e["depth"] is None else round(e["depth"], 1), "place": e["place"],
                    "src": e["src"], "mags": e["mags"], "cr": e["cr"], "first_seen": int(e["first_seen"]),
                    "notified": bool(e.get("notified"))} for e in store],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=570)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--out", default="quakes.json")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    out = Path(args.out)
    store = load_previous(out)
    topic = os.environ.get("QUAKE_ALERT_TOPIC", "").strip()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    started = time.monotonic()
    last_publish = 0.0
    cycle = 0
    sources_ok = {"usgs": None, "emsc": None}
    while True:
        now = utc_now()
        now_epoch = now.timestamp()
        changed = False
        # USGS cada ciclo (archivo pequeño, se actualiza cada minuto); el primer ciclo trae el día completo.
        data = fetch_json(session, USGS_DAY if cycle == 0 else USGS_HOUR)
        sources_ok["usgs"] = data is not None
        if data is not None:
            usgs_events = parse_usgs(data)
            logging.info("USGS: %s sismos en la región (de %s en el archivo).", len(usgs_events), len(data.get("features", [])))
            changed |= merge_into(store, usgs_events, now_epoch)
        # EMSC cada 2 ciclos (cada ~60 s).
        if cycle % 2 == 0:
            events = fetch_emsc(session, now)
            sources_ok["emsc"] = events is not None
            if events is not None:
                logging.info("EMSC: %s sismos en la región.", len(events))
                changed |= merge_into(store, events, now_epoch)
        store = prune(store, now_epoch)
        if topic:
            before = sum(1 for e in store if e.get("notified"))
            send_alerts(store, session, topic, now_epoch)
            changed |= sum(1 for e in store if e.get("notified")) != before
        due = time.monotonic() - last_publish >= HEARTBEAT_SECONDS
        if changed or due or cycle == 0:
            out.write_text(json.dumps(build_payload(store, sources_ok), separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
            if args.no_publish:
                last_publish = time.monotonic()
                logging.info("(sin publicar) %s sismos", len(store))
            else:
                try:
                    publish(out)
                    last_publish = time.monotonic()
                    logging.info("Publicado: %s sismos (USGS %s, EMSC %s)", len(store), sources_ok["usgs"], sources_ok["emsc"])
                except Exception as exc:
                    logging.warning("No se pudo publicar: %s", exc)
        cycle += 1
        if time.monotonic() - started + args.interval > args.duration:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
