"""Avisos de lluvia por zona mediante ntfy (sin cuenta ni clave).

Una estación del IMN dispara aviso cuando pasa de "sin lluvia" a "lluvia".
Para no saturar el teléfono, las estaciones nuevas de una misma zona se
agrupan en UN solo mensaje por corrida y cada zona espera un enfriamiento
(COOLDOWN_MINUTES) antes de volver a avisar. Cada zona usa su propio canal.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

COOLDOWN_MINUTES = 45
MAX_LISTED = 5
ZONES_PATH = Path(__file__).resolve().parent.parent / "config" / "notify-zones.json"


def load_zones(path: Path = ZONES_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logging.warning("No se pudo leer la configuración de avisos; se omiten las notificaciones.")
        return {"server": "", "zones": []}


def new_rain_alerts(current: list[dict], previous: list[dict]) -> list[dict]:
    """Alertas de estación que no estaban en la corrida anterior."""
    before = {item.get("station_id") for item in previous if isinstance(item, dict)}
    return [item for item in current if item.get("station_id") not in before]


def _mm(alert: dict):
    mm = alert.get("rain_last_hour_mm")
    return mm if isinstance(mm, (int, float)) else None


def build_message(zone: dict, alerts: list[dict] | dict) -> dict:
    """Un mensaje por zona con todas sus estaciones nuevas (la más intensa primero)."""
    items = [alerts] if isinstance(alerts, dict) else list(alerts)
    items.sort(key=lambda a: -(_mm(a) or 0))
    lines = []
    for a in items[:MAX_LISTED]:
        mm = _mm(a)
        amount = f"{mm:g} mm/h" if mm is not None else "lluvia medida"
        lines.append(f"🌧️ {a.get('station_name', 'Estación IMN').replace('Estación IMN · ', '')}: {amount}")
    if len(items) > MAX_LISTED:
        lines.append(f"… y {len(items) - MAX_LISTED} estaciones más")
    body = "\n".join(lines)
    if len(items) == 1 and _mm(items[0]) is not None:
        body = f"{items[0].get('station_name', 'Estación IMN')}: {_mm(items[0]):g} mm en la última hora."
    places = ", ".join(zone.get("places", []))
    if places:
        body += f"\n📍 Zona: {places}.\nLa lluvia puede variar de un barrio a otro."
    title = f"Lluvia en {zone['name']}"
    if len(items) > 1:
        title += f" · {len(items)} estaciones"
    return {
        "topic": zone["topic"],
        "title": title,
        "message": body,
        "tags": ["cloud_with_rain"],
        "priority": 3,
        "click": items[0].get("page_url") or "",
    }


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts))
    except ValueError:
        return None


def notify_new_rain(
    current: list[dict],
    previous: list[dict],
    session: requests.Session,
    config: dict | None = None,
    state: dict | None = None,
    now: datetime | None = None,
) -> int:
    """Envía como mucho un aviso por zona y corrida; `state` guarda el último aviso de cada zona."""
    config = config if config is not None else load_zones()
    server = str(config.get("server") or "").rstrip("/")
    if not server:
        return 0
    state = state if state is not None else {}
    now = now or datetime.now(timezone.utc)
    fresh = new_rain_alerts(current, previous)
    sent = 0
    for zone in config.get("zones", []):
        group = [a for a in fresh if a.get("station_id") in zone.get("station_ids", [])]
        if not group:
            continue
        last = _parse(state.get(zone["id"]))
        if last is not None and last.tzinfo and now - last < timedelta(minutes=COOLDOWN_MINUTES):
            logging.info("Aviso de %s en pausa (enfriamiento).", zone["name"])
            continue
        message = build_message(zone, group)
        if not message["click"]:
            message.pop("click")
        try:
            response = session.post(server, data=json.dumps(message).encode("utf-8"), timeout=15)
            response.raise_for_status()
            sent += 1
            state[zone["id"]] = now.isoformat()
        except requests.RequestException as error:
            # Un fallo de ntfy nunca debe romper el monitoreo.
            logging.warning("No se pudo enviar el aviso de %s: %s", zone["name"], error)
    return sent
