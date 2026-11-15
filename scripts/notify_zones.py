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


APP_URL = "https://allan101010.github.io/RAINROAD/"
MAX_LISTED = 3

# Misma escala de colores que la leyenda de la app: débil, moderada, fuerte, intensa.
LEVELS = [(8.0, "🔴", "Tormenta", "thunder_cloud_and_rain"), (4.0, "🟡", "Lluvia fuerte", "cloud_with_rain"),
          (1.0, "🟢", "Lluvia", "cloud_with_rain"), (0.0, "🔵", "Llovizna", "cloud_with_rain")]


def _level(mm):
    value = mm if mm is not None else 0.0
    return next(level for level in LEVELS if value >= level[0])


def _short_name(alert: dict) -> str:
    name = str(alert.get("station_name") or "Estación IMN")
    for prefix in ("Estación IMN · ", "Estación UCR · "):
        name = name.replace(prefix, "")
    return name


def build_message(zone: dict, alerts: list[dict] | dict) -> dict:
    """Un mensaje corto por zona: título con la intensidad y una línea por estación (la más intensa primero)."""
    items = [alerts] if isinstance(alerts, dict) else list(alerts)
    items.sort(key=lambda a: -(_mm(a) or 0))
    top = _level(_mm(items[0]))
    lines = []
    for a in items[:MAX_LISTED]:
        mm = _mm(a)
        amount = f"{mm:g} mm/h" if mm is not None else "lluvia medida"
        lines.append(f"{_level(mm)[1]} {_short_name(a)} · {amount}")
    if len(items) > MAX_LISTED:
        extra = len(items) - MAX_LISTED
        lines.append(f"+{extra} estación más" if extra == 1 else f"+{extra} estaciones más")
    return {
        "topic": zone["topic"],
        "title": f"🌧️ {top[2]} en {zone['name']}",
        "message": "\n".join(lines),
        "tags": [top[3]],
        "priority": 4 if top[2] == "Tormenta" else 3,
        "click": APP_URL,
        "actions": [{"action": "view", "label": "Ver mapa", "url": APP_URL}],
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
        try:
            response = session.post(server, data=json.dumps(message).encode("utf-8"), timeout=15)
            response.raise_for_status()
            sent += 1
            state[zone["id"]] = now.isoformat()
        except requests.RequestException as error:
            # Un fallo de ntfy nunca debe romper el monitoreo.
            logging.warning("No se pudo enviar el aviso de %s: %s", zone["name"], error)
    return sent
