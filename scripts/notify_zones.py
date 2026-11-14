"""Avisos de lluvia por zona mediante ntfy (sin cuenta ni clave).

Se envía un aviso cuando una estación del IMN pasa de "sin lluvia" a "lluvia"
(no se repite mientras siga lloviendo). Cada zona usa su propio canal.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

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


def build_message(zone: dict, alert: dict) -> dict:
    mm = alert.get("rain_last_hour_mm")
    amount = f"{mm:g} mm en la última hora" if isinstance(mm, (int, float)) else "lluvia medida"
    places = ", ".join(zone.get("places", []))
    body = f"{alert.get('station_name', 'Estación IMN')}: {amount}."
    if places:
        body += f"\nZona: {places}.\nEs una estación del IMN de esta zona; la lluvia puede variar de un barrio a otro."
    return {
        "topic": zone["topic"],
        "title": f"Lluvia en {zone['name']}",
        "message": body,
        "tags": ["cloud_with_rain"],
        "priority": 3,
        "click": alert.get("page_url") or "",
    }


def notify_new_rain(
    current: list[dict],
    previous: list[dict],
    session: requests.Session,
    config: dict | None = None,
) -> int:
    config = config if config is not None else load_zones()
    server = str(config.get("server") or "").rstrip("/")
    if not server:
        return 0
    sent = 0
    for alert in new_rain_alerts(current, previous):
        for zone in config.get("zones", []):
            if alert.get("station_id") not in zone.get("station_ids", []):
                continue
            message = build_message(zone, alert)
            if not message["click"]:
                message.pop("click")
            try:
                response = session.post(server, data=json.dumps(message).encode("utf-8"), timeout=15)
                response.raise_for_status()
                sent += 1
            except requests.RequestException as error:
                # Un fallo de ntfy nunca debe romper el monitoreo.
                logging.warning("No se pudo enviar el aviso de %s: %s", zone["name"], error)
    return sent
