#!/usr/bin/env python3
"""Juez de IA de visión para las cámaras de RainTrack CR.

Envía una captura de cámara a un modelo de visión (API de Anthropic) y recibe
un veredicto estricto: ¿se ve lluvia CAYENDO en este momento?

Diseño:
- Se llama solo para cámaras "candidatas" (los modelos pequeños sospechan lluvia).
- Una captura idéntica a la anterior reutiliza el veredicto previo (sin costo).
- Hay un tope por ejecución y un tope diario de llamadas.
- Sin ANTHROPIC_API_KEY el juez queda desactivado y no se llama a ninguna API.
- Ante cualquier error el veredicto es "unclear": nunca se inventa una alerta.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests
from PIL import Image

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-5-5"
MIN_CONFIDENCE = 0.80
MAX_IMAGE_SIDE = 1024
REQUEST_TIMEOUT = 45

SYSTEM_PROMPT = (
    "Eres un observador meteorológico muy estricto. Recibes UNA captura de una cámara web "
    "pública de Costa Rica y debes decidir si en ese momento se ve lluvia CAYENDO. "
    "Responde únicamente con un objeto JSON, sin texto adicional."
)

USER_PROMPT = (
    "Cámara: {label}.\n"
    "¿Se ve lluvia cayendo ahora mismo en esta captura?\n"
    "Reglas:\n"
    "- Superficies mojadas, charcos, reflejos o cielo gris NO bastan: eso indica que llovió antes.\n"
    "- Niebla, bruma, nubes bajas, gotas pegadas en el lente o la ventana, ruido de sensor, "
    "luz infrarroja nocturna y hojas brillantes NO son lluvia cayendo.\n"
    "- Responde \"yes\" solo si ves rayas de lluvia, cortinas de lluvia o gotas cayendo, o salpicaduras "
    "claras de gotas golpeando el suelo o el agua.\n"
    "- Si la imagen es oscura, borrosa o no permite decidir, responde \"unclear\".\n"
    "Formato exacto: {{\"raining\": \"yes\" | \"no\" | \"unclear\", \"confidence\": número entre 0 y 1, "
    "\"evidence\": \"una frase corta en español con lo que observas\"}}"
)

VERDICTS = {"yes": "rain", "no": "no_rain", "unclear": "unclear"}


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def prepare_image(image: Image.Image) -> tuple[str, str]:
    """Reduce la captura y devuelve (base64 JPEG, huella sha1 del JPEG)."""
    rgb = image.convert("RGB")
    rgb.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=80)
    data = buffer.getvalue()
    return base64.b64encode(data).decode("ascii"), hashlib.sha1(data).hexdigest()


def parse_verdict(text: str) -> dict:
    """Interpreta la respuesta del modelo. Cualquier cosa rara se vuelve 'unclear'."""
    fallback = {"verdict": "unclear", "confidence": 0.0, "evidence": "Respuesta no interpretable."}
    if not text:
        return fallback
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return fallback
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback
    verdict = VERDICTS.get(str(raw.get("raining", "")).strip().lower())
    if verdict is None:
        return fallback
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    evidence = str(raw.get("evidence", "")).strip()[:300]
    if verdict == "rain" and confidence < MIN_CONFIDENCE:
        verdict = "unclear"
    return {"verdict": verdict, "confidence": round(confidence, 3), "evidence": evidence}


class VisionJudge:
    def __init__(self, api_key: str | None, model: str = DEFAULT_MODEL, daily_limit: int = 300,
                 max_per_run: int = 12, calls_today: int = 0, today: str | None = None,
                 session: requests.Session | None = None):
        self.api_key = (api_key or "").strip()
        self.model = model
        self.daily_limit = daily_limit
        self.max_per_run = max_per_run
        self.today = today or utc_today()
        self.calls_today = calls_today
        self.calls_this_run = 0
        self.reused_this_run = 0
        self.skipped_budget = 0
        self.errors = 0
        self.session = session or requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls, previous_state: dict | None = None, session: requests.Session | None = None) -> "VisionJudge":
        previous_state = previous_state or {}
        today = utc_today()
        calls_today = int(previous_state.get("calls_today", 0)) if previous_state.get("date") == today else 0
        return cls(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            model=os.environ.get("VISION_JUDGE_MODEL") or DEFAULT_MODEL,
            daily_limit=int(os.environ.get("VISION_JUDGE_DAILY_LIMIT") or 300),
            max_per_run=int(os.environ.get("VISION_JUDGE_MAX_PER_RUN") or 12),
            calls_today=calls_today,
            today=today,
            session=session,
        )

    def can_call(self) -> bool:
        return (self.enabled and self.calls_this_run < self.max_per_run
                and self.calls_today < self.daily_limit)

    def state(self) -> dict:
        return {
            "enabled": self.enabled,
            "model": self.model if self.enabled else None,
            "date": self.today,
            "calls_today": self.calls_today,
            "daily_limit": self.daily_limit,
            "max_per_run": self.max_per_run,
            "calls_this_run": self.calls_this_run,
            "reused_this_run": self.reused_this_run,
            "skipped_budget": self.skipped_budget,
            "errors": self.errors,
        }

    def _call_api(self, image_b64: str, label: str) -> str:
        body = {
            "model": self.model,
            "max_tokens": 300,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                {"type": "text", "text": USER_PROMPT.format(label=label)},
            ]}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": API_VERSION,
                   "content-type": "application/json"}
        last_error = None
        for attempt in range(2):
            try:
                response = self.session.post(API_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
                if response.status_code in (429, 500, 502, 503, 529) and attempt == 0:
                    time.sleep(3)
                    continue
                response.raise_for_status()
                blocks = response.json().get("content", [])
                return "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
            except requests.RequestException as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(3)
        raise last_error  # type: ignore[misc]

    def assess(self, image: Image.Image, label: str, previous: dict | None = None) -> dict:
        """Devuelve {'verdict','confidence','evidence','model','image_hash','source','checked_at'}.

        source: 'api' (llamada nueva), 'reused' (misma imagen que la vez anterior),
        'budget' (sin cupo) o 'error'. Nunca lanza excepciones.
        """
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        base = {"model": self.model, "checked_at": now}
        try:
            image_b64, image_hash = prepare_image(image)
        except Exception as exc:  # imagen corrupta
            logging.warning("Juez de visión: no se pudo preparar la imagen de %s: %s", label, exc)
            return {**base, "verdict": "unclear", "confidence": 0.0,
                    "evidence": "No se pudo preparar la imagen.", "image_hash": None, "source": "error"}

        if (previous and previous.get("image_hash") == image_hash and previous.get("verdict")
                and previous.get("source") in ("api", "reused")):
            self.reused_this_run += 1
            return {**base, **{k: previous[k] for k in ("verdict", "confidence", "evidence") if k in previous},
                    "image_hash": image_hash, "source": "reused",
                    "checked_at": previous.get("checked_at", now)}

        if not self.can_call():
            self.skipped_budget += 1
            return {**base, "verdict": "unclear", "confidence": 0.0,
                    "evidence": "Sin cupo de llamadas a la IA de visión en este ciclo.",
                    "image_hash": image_hash, "source": "budget"}

        self.calls_this_run += 1
        self.calls_today += 1
        try:
            parsed = parse_verdict(self._call_api(image_b64, label))
        except Exception as exc:
            self.errors += 1
            logging.warning("Juez de visión: error de API en %s: %s", label, type(exc).__name__)
            return {**base, "verdict": "unclear", "confidence": 0.0,
                    "evidence": "No se pudo consultar la IA de visión.",
                    "image_hash": image_hash, "source": "error"}
        return {**base, **parsed, "image_hash": image_hash, "source": "api"}
