#!/usr/bin/env python3
"""
RainTrack CR - monitor visual de cámaras públicas de Costa Rica.

Descubre las cámaras de cada ficha de Webcams Costa Rica, obtiene las
capturas públicas disponibles y clasifica la escena con un modelo abierto
de condiciones meteorológicas. No intenta acceder a cámaras privadas ni
extraer vídeo de plataformas externas.

El análisis es orientativo: "rain/storm" significa indicios visuales,
no una confirmación meteorológica oficial.
"""

from __future__ import annotations

import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

BASE_URL = "https://webcamscostarica.com/"
MODEL_ID = "prithivMLmods/Weather-Image-Classification"
SCENE_MODEL_ID = "openai/clip-vit-base-patch32"
CATALOG_SCHEMA_VERSION = 2
CATALOG_PATH = Path("camera-catalog.json")
ALERTS_PATH = Path("camera-alerts.json")
CATALOG_MAX_AGE = timedelta(hours=6)
CAMERA_ONLINE_MAX_AGE = timedelta(minutes=2)
CAMERA_DELAYED_MAX_AGE = timedelta(hours=1)
HTTP_TIMEOUT = 25
USER_AGENT = "RainTrackCR/1.5 (public weather-camera monitor; contact via project repository)"
MAX_IMAGE_BYTES = 18 * 1024 * 1024

# Coordenadas del sitio publicadas por Webcams Costa Rica. Son referencias
# cartográficas del lugar, no la ubicación exacta de cada cámara.
SITES = [
    ("playa-flamingo", "Playa Flamingo", "Guanacaste", 10.4340, -85.7860),
    ("playa-hermosa-guanacaste", "Playa Hermosa de Guanacaste", "Guanacaste", 10.5750, -85.6770),
    ("playas-del-coco", "Playas del Coco", "Guanacaste", 10.5530, -85.6940),
    ("tamarindo", "Tamarindo", "Guanacaste", 10.3000, -85.8410),
    ("volcan-rincon-de-la-vieja", "Volcán Rincón de la Vieja", "Guanacaste", 10.8300, -85.3240),
    ("jaco", "Jacó", "Pacífico Central", 9.6140, -84.6290),
    ("manuel-antonio", "Manuel Antonio", "Pacífico Central", 9.3920, -84.1400),
    ("playa-herradura", "Playa Herradura", "Pacífico Central", 9.6600, -84.6350),
    ("quepos", "Quepos", "Pacífico Central", 9.4050, -84.1570),
    ("punta-islita", "Lapas rojas de Punta Islita", "Península de Nicoya", 9.8530, -85.3980),
    ("nosara", "Nosara", "Península de Nicoya", 9.9400, -85.6650),
    ("reserva-karen-mogensen", "Reserva Karen Mogensen", "Península de Nicoya", 9.8690, -85.0580),
    ("santa-teresa", "Santa Teresa", "Península de Nicoya", 9.6460, -85.1690),
    ("cartago", "Cartago", "Valle Central", 9.8640, -83.9190),
    ("cerros-de-escazu", "Cerros de Escazú", "Valle Central", 9.9040, -84.1580),
    ("san-jose", "San José", "Valle Central", 9.9330, -84.0800),
    ("toucan-rescue-ranch", "Toucan Rescue Ranch", "Valle Central", 10.0350, -84.1000),
    ("volcan-irazu", "Volcán Irazú", "Valle Central", 9.9790, -83.8520),
    ("volcan-poas", "Volcán Poás", "Valle Central", 10.1980, -84.2310),
    ("sarapiqui", "Lapas verdes de Sarapiquí", "Zona Norte", 10.4560, -84.0190),
]

OFFLINE_PHRASES = (
    "ahora no está emitiendo",
    "no está emitiendo ahora mismo",
    "no está enviando imágenes ahora",
    "esta cámara no está enviando imágenes",
    "no envía imágenes desde",
    "ahora no emite",
)

# No se excluye una cámara por su categoría o nombre. Todas son candidatas;
# un modelo visual independiente decide si el encuadre muestra suficiente
# entorno exterior para que el análisis meteorológico tenga sentido.
def is_weather_view(site_slug: str, camera_name: str) -> tuple[bool, str]:
    return True, "Candidata: la IA evaluará si el encuadre muestra entorno exterior útil para meteorología."


# Cámaras oficiales OVSICORI-UNA. Las coordenadas son referencias del volcán
# para el mapa, no la posición topográfica exacta de cada lente.
OVSICORI_CAMERAS = [
    {
        "id": "ovsicori-poas-crater", "site_slug": "volcan-poas",
        "site_name": "Volcán Poás", "zone": "Valle Central",
        "lat": 10.1980, "lon": -84.2310,
        "camera_name": "OVSICORI · Cráter del Poás",
        "page_url": "https://www.ovsicori.una.ac.cr/index.php/vulcanologia/camara-volcanes-2/camara-crater-v-poas",
        "snapshot_url": "https://www.ovsicori.una.ac.cr/images/stories/camaras/livecraterpoas/camara.jpg",
        "source_type": "ovsicori",
        "coordinate_note": "Coordenada de referencia del Volcán Poás."
    },
    {
        "id": "ovsicori-poas-suroeste", "site_slug": "volcan-poas",
        "site_name": "Volcán Poás", "zone": "Valle Central",
        "lat": 10.1980, "lon": -84.2310,
        "camera_name": "OVSICORI · Poás, suroeste del cráter",
        "page_url": "https://www.ovsicori.una.ac.cr/index.php/vulcanologia/camara-volcanes-2/camara-v-poas-so-del-crater",
        "snapshot_url": "https://www.ovsicori.una.ac.cr/images/stories/camaras/livepoas/camara.jpg",
        "source_type": "ovsicori",
        "coordinate_note": "Coordenada de referencia del Volcán Poás; cámara a 1,8 km al suroeste del cráter."
    },
    {
        "id": "ovsicori-poas-chahuites", "site_slug": "volcan-poas",
        "site_name": "Volcán Poás", "zone": "Valle Central",
        "lat": 10.1980, "lon": -84.2310,
        "camera_name": "OVSICORI · Poás desde Chahuites",
        "page_url": "https://www.ovsicori.una.ac.cr/index.php/vulcanologia/camara-volcanes-2/camara-v-poas-chahuites",
        "snapshot_url": "https://www.ovsicori.una.ac.cr/images/stories/camaras/livechahuites/camara.jpg",
        "source_type": "ovsicori",
        "coordinate_note": "Coordenada de referencia del Volcán Poás."
    },
    {
        "id": "ovsicori-rincon-sensoria", "site_slug": "volcan-rincon-de-la-vieja",
        "site_name": "Volcán Rincón de la Vieja", "zone": "Guanacaste",
        "lat": 10.8300, "lon": -85.3240,
        "camera_name": "OVSICORI · Rincón de la Vieja, Sensoria",
        "page_url": "https://www.ovsicori.una.ac.cr/index.php/vulcanologia/camara-volcanes-2/rincon-de-la-vieja-sensoria2",
        "snapshot_url": "https://www.ovsicori.una.ac.cr/images/stories/camaras/liverincon/camara.jpg",
        "source_type": "ovsicori",
        "coordinate_note": "Coordenada de referencia del volcán; cámara ubicada aproximadamente 4 km al norte."
    },
    {
        "id": "ovsicori-rincon-curubande", "site_slug": "volcan-rincon-de-la-vieja",
        "site_name": "Volcán Rincón de la Vieja", "zone": "Guanacaste",
        "lat": 10.8300, "lon": -85.3240,
        "camera_name": "OVSICORI · Rincón de la Vieja, Curubandé",
        "page_url": "https://www.ovsicori.una.ac.cr/index.php/vulcanologia/camara-volcanes-2/camara-v-rincon-de-la-vieja-curubande",
        "snapshot_url": "https://www.ovsicori.una.ac.cr/images/stories/camaras/livecurubande/camara.jpg",
        "source_type": "ovsicori",
        "coordinate_note": "Coordenada de referencia del volcán; la cámara está en el sector de Curubandé."
    },
    {
        "id": "ovsicori-rincon-gavilan", "site_slug": "volcan-rincon-de-la-vieja",
        "site_name": "Volcán Rincón de la Vieja", "zone": "Guanacaste",
        "lat": 10.8300, "lon": -85.3240,
        "camera_name": "OVSICORI · Rincón de la Vieja, Gavilán",
        "page_url": "https://www.ovsicori.una.ac.cr/index.php/vulcanologia/camara-volcanes-2/rincon-de-la-vieja-gavilan",
        "snapshot_url": "https://www.ovsicori.una.ac.cr/images/stories/camaras/liverincon2/camara.jpg",
        "source_type": "ovsicori",
        "coordinate_note": "Coordenada de referencia del volcán; cámara ubicada en Buenos Aires de Upala."
    },
    {
        "id": "ovsicori-irazu", "site_slug": "volcan-irazu",
        "site_name": "Volcán Irazú", "zone": "Valle Central",
        "lat": 9.9790, "lon": -83.8520,
        "camera_name": "OVSICORI · Volcán Irazú",
        "page_url": "https://www.ovsicori.una.ac.cr/index.php/vulcanologia/camara-volcanes-2/camara-2-v-turrialba",
        "snapshot_url": "https://www.ovsicori.una.ac.cr/images/stories/camaras/liveirazu/camara.jpg",
        "source_type": "ovsicori",
        "coordinate_note": "Coordenada de referencia del Volcán Irazú."
    },
    {
        "id": "ovsicori-turrialba", "site_slug": "volcan-turrialba",
        "site_name": "Volcán Turrialba", "zone": "Valle Central",
        "lat": 10.0250, "lon": -83.7670,
        "camera_name": "OVSICORI · Volcán Turrialba",
        "page_url": "https://www.ovsicori.una.ac.cr/index.php/vulcanologia/camara-volcanes-2/camara-v-turrialba",
        "snapshot_url": "https://www.ovsicori.una.ac.cr/images/stories/camaras/liveturrialba/camara.jpg",
        "source_type": "ovsicori",
        "coordinate_note": "Coordenada de referencia del Volcán Turrialba; cámara instalada al este del cráter."
    },
]




def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def session_with_headers() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    return session


def get_page(session: requests.Session, url: str) -> tuple[str, str]:
    response = session.get(url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text, response.url


def text_content(soup: BeautifulSoup) -> str:
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).lower()


def page_is_offline(soup: BeautifulSoup) -> bool:
    text = text_content(soup)
    return any(phrase in text for phrase in OFFLINE_PHRASES)


def same_site_path(url_a: str, url_b: str) -> bool:
    a = urlparse(url_a)
    b = urlparse(url_b)
    return a.netloc == b.netloc and a.path.rstrip("/") == b.path.rstrip("/")


def extract_camera_variants(
    session: requests.Session, page_url: str, soup: BeautifulSoup
) -> list[tuple[str, str, str]]:
    """Returns camera variants (slug, label, page URL) for a site."""
    variants: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if "cam=" not in href:
            continue
        full_url = urljoin(page_url, href)
        if not same_site_path(full_url, page_url):
            continue
        cam_values = parse_qs(urlparse(full_url).query).get("cam", [])
        if not cam_values:
            continue
        cam_slug = cam_values[0].strip()
        if not cam_slug or cam_slug in seen:
            continue
        seen.add(cam_slug)
        label = anchor.get_text(" ", strip=True)
        label = re.sub(r"\s+", " ", label).strip()
        variants.append((cam_slug, label or cam_slug, full_url))

    if variants:
        # Algunas fichas muestran una cámara por defecto además de los enlaces
        # ?cam=. Se incorpora solo si el título no está ya representado.
        h2 = soup.find("h2")
        default_name = h2.get_text(" ", strip=True) if h2 else ""
        if default_name and not any(default_name.lower() in label.lower() or label.lower() in default_name.lower()
                                    for _, label, _ in variants):
            variants.insert(0, ("default", default_name, page_url))
        return variants

    h2 = soup.find("h2")
    name = h2.get_text(" ", strip=True) if h2 else ""
    if not name:
        h1 = soup.find("h1")
        name = h1.get_text(" ", strip=True) if h1 else "Cámara"
    return [("default", name, page_url)]


def snapshot_score(url: str, alt: str) -> int:
    parsed = urlparse(url)
    host_path = (parsed.netloc + parsed.path).lower()
    alt = (alt or "").lower()
    score = 0
    if "/snap/" in parsed.path.lower():
        score += 20
    if "ovsicori.una.ac.cr/images/stories/camaras/" in host_path and "camara" in host_path:
        score += 20
    if "meteo.unimore.it/meteo/ossgeo/" in host_path:
        score += 20
    if "phenocam" in host_path:
        score += 18
    if "cámara" in alt or "camara" in alt or "imagen en directo" in alt or "webcam" in alt:
        score += 8
    if "/assets/fotos/" in parsed.path.lower():
        score -= 25
    if any(ext in parsed.path.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")):
        score += 2
    return score


def extract_snapshot_url(soup: BeautifulSoup, page_url: str) -> str | None:
    candidates: list[tuple[int, str]] = []

    for img in soup.find_all("img"):
        alt = img.get("alt", "")
        for attr in ("src", "data-src", "data-lazy-src"):
            raw = img.get(attr)
            if raw:
                full = urljoin(page_url, raw.strip())
                score = snapshot_score(full, alt)
                if score >= 10:
                    candidates.append((score, full))

        srcset = img.get("srcset")
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0]
            full = urljoin(page_url, first)
            score = snapshot_score(full, alt)
            if score >= 10:
                candidates.append((score, full))

    for meta in soup.find_all("meta"):
        if meta.get("property") == "og:image" or meta.get("name") == "twitter:image":
            raw = meta.get("content")
            if raw:
                full = urljoin(page_url, raw.strip())
                score = snapshot_score(full, "camera snapshot")
                if score >= 15:
                    candidates.append((score, full))

    for video in soup.find_all("video"):
        raw = video.get("poster")
        if raw:
            full = urljoin(page_url, raw.strip())
            score = snapshot_score(full, "camera poster")
            if score >= 10:
                candidates.append((score, full))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def build_catalog(session: requests.Session) -> list[dict]:
    catalog: list[dict] = []

    for site_slug, site_name, zone, lat, lon in SITES:
        site_url = urljoin(BASE_URL, site_slug + "/")
        try:
            page_html, final_page_url = get_page(session, site_url)
            site_soup = BeautifulSoup(page_html, "html.parser")
            variants = extract_camera_variants(session, final_page_url, site_soup)
        except Exception as exc:
            logging.warning("No se pudo consultar %s: %s", site_name, exc)
            catalog.append({
                "id": site_slug + "-unavailable",
                "site_slug": site_slug,
                "site_name": site_name,
                "zone": zone,
                "lat": lat,
                "lon": lon,
                "camera_name": "Ficha no disponible",
                "page_url": site_url,
                "snapshot_url": None,
                "source_type": "webcamscostarica",
                "weather_relevant": True,
                "reason": "Ficha pendiente de revisión; se intentará recuperar la captura en cada ciclo.",
                "initial_status": "not_available",
            })
            continue

        for cam_slug, link_label, camera_page_url in variants:
            try:
                if camera_page_url == final_page_url:
                    camera_html, resolved_url, camera_soup = page_html, final_page_url, site_soup
                else:
                    camera_html, resolved_url = get_page(session, camera_page_url)
                    camera_soup = BeautifulSoup(camera_html, "html.parser")

                h2 = camera_soup.find("h2")
                camera_name = h2.get_text(" ", strip=True) if h2 else link_label
                if not camera_name or camera_name.lower() in {"qué se ve", "qué se ve"}:
                    camera_name = link_label or site_name

                offline = page_is_offline(camera_soup)
                snapshot_url = extract_snapshot_url(camera_soup, resolved_url)
                weather_relevant, reason = is_weather_view(site_slug, camera_name)

                if offline:
                    initial_status = "offline"
                    snapshot_url = None
                elif not weather_relevant:
                    initial_status = "not_monitored"
                elif not snapshot_url:
                    initial_status = "not_available"
                    reason = "La ficha no expone una captura pública que pueda analizarse automáticamente."
                else:
                    initial_status = "pending"

                catalog.append({
                    "id": f"{site_slug}-{cam_slug}",
                    "site_slug": site_slug,
                    "site_name": site_name,
                    "zone": zone,
                    "lat": lat,
                    "lon": lon,
                    "camera_name": camera_name,
                    "page_url": resolved_url,
                    "snapshot_url": snapshot_url,
                    "source_type": "webcamscostarica",
                    "weather_relevant": True,
                    "reason": reason,
                    "initial_status": initial_status,
                })
                time.sleep(0.15)
            except Exception as exc:
                logging.warning("No se pudo leer cámara %s / %s: %s", site_name, link_label, exc)
                catalog.append({
                    "id": f"{site_slug}-{cam_slug}",
                    "site_slug": site_slug,
                    "site_name": site_name,
                    "zone": zone,
                    "lat": lat,
                    "lon": lon,
                    "camera_name": link_label or site_name,
                    "page_url": camera_page_url,
                    "snapshot_url": None,
                    "source_type": "webcamscostarica",
                    "weather_relevant": True,
                    "reason": "No se pudo consultar la cámara en esta revisión; se reintentará.",
                    "initial_status": "not_available",
                })

    # Añadir las ocho cámaras oficiales del OVSICORI-UNA.
    for camera in OVSICORI_CAMERAS:
        row = dict(camera)
        row.update({
            "weather_relevant": True,
            "reason": "Cámara exterior oficial OVSICORI-UNA; evaluación visual y control de antigüedad de imagen.",
            "initial_status": "pending",
        })
        catalog.append(row)

    # Evitar analizar varias veces la misma imagen repetida en distintas
    # variantes de una ficha. Se conserva la fuente oficial OVSICORI cuando
    # comparte la misma URL de imagen con una ficha agregadora.
    deduplicated: dict[tuple[str, str], dict] = {}
    without_snapshot: list[dict] = []
    for camera in catalog:
        snapshot = camera.get("snapshot_url")
        if not snapshot:
            without_snapshot.append(camera)
            continue
        parsed = urlparse(snapshot)
        normalized = urlunparse(parsed._replace(query="", fragment=""))
        key = (camera.get("site_slug", ""), normalized)
        existing = deduplicated.get(key)
        if existing is None or camera.get("source_type") == "ovsicori":
            deduplicated[key] = camera

    return list(deduplicated.values()) + without_snapshot


def load_catalog(session: requests.Session) -> list[dict]:
    if CATALOG_PATH.exists():
        try:
            saved = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            generated_text = saved.get("generated_at") if isinstance(saved, dict) else None
            saved_cameras = saved.get("cameras", []) if isinstance(saved, dict) else saved
            schema_version = saved.get("schema_version", 0) if isinstance(saved, dict) else 0
            required_ovsicori = {camera["id"] for camera in OVSICORI_CAMERAS}
            present_ovsicori = {
                camera.get("id") for camera in saved_cameras
                if isinstance(camera, dict) and camera.get("source_type") == "ovsicori"
            }
            if generated_text and saved_cameras and schema_version >= CATALOG_SCHEMA_VERSION and required_ovsicori.issubset(present_ovsicori):
                generated = datetime.fromisoformat(generated_text.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - generated
                if age < CATALOG_MAX_AGE:
                    return saved_cameras
        except Exception:
            pass

    logging.info("Actualizando catálogo de cámaras desde Webcams Costa Rica…")
    catalog = build_catalog(session)
    if catalog:
        CATALOG_PATH.write_text(
            json.dumps(
                {
                    "schema_version": CATALOG_SCHEMA_VERSION,
                    "generated_at": iso_now(),
                    "cameras": catalog,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return catalog

    if CATALOG_PATH.exists():
        saved = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            return saved.get("cameras", [])
        return saved
    raise RuntimeError("No fue posible construir el catálogo de cámaras.")


def cache_busted(url: str) -> str:
    parts = urlparse(url)
    query = parse_qs(parts.query)
    query["raintrack_ts"] = [str(int(time.time()))]
    return urlunparse(parts._replace(query=urlencode(query, doseq=True)))


def fetch_snapshot(session: requests.Session, url: str) -> tuple[Image.Image, dict]:
    response = session.get(cache_busted(url), timeout=HTTP_TIMEOUT, headers={
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    if not content_type.startswith("image/"):
        raise ValueError(f"La fuente no devolvió una imagen ({content_type or 'tipo desconocido'}).")
    if len(response.content) > MAX_IMAGE_BYTES:
        raise ValueError("La captura supera el tamaño permitido.")

    image = Image.open(io.BytesIO(response.content))
    image = ImageOps.exif_transpose(image).convert("RGB")
    if image.width < 120 or image.height < 80:
        raise ValueError("La imagen recibida es demasiado pequeña para analizarla.")

    metadata = {
        "content_type": content_type,
        "last_modified": response.headers.get("Last-Modified"),
        "etag": response.headers.get("ETag"),
    }
    return image, metadata


def load_weather_model():
    import torch
    from transformers import AutoImageProcessor, SiglipForImageClassification

    torch.set_num_threads(2)

    # Este repositorio publica un clasificador SigLIP2 de imágenes.
    # Se carga el procesador visual y la arquitectura específica documentada
    # por el modelo, sin intentar inicializar el tokenizador de texto.
    processor = AutoImageProcessor.from_pretrained(MODEL_ID)
    model = SiglipForImageClassification.from_pretrained(MODEL_ID)
    model.eval()
    return torch, processor, model


def classify_image(image: Image.Image, model_bundle) -> tuple[float, str, float]:
    torch, processor, model = model_bundle
    inputs = processor(images=image, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
        probabilities = torch.softmax(logits, dim=-1)[0].cpu().tolist()

    labels = model.config.id2label
    if not isinstance(labels, dict):
        labels = {str(i): label for i, label in enumerate(labels)}

    label_pairs = []
    for index, probability in enumerate(probabilities):
        label = str(labels.get(str(index), labels.get(index, index))).lower()
        label_pairs.append((label, float(probability)))

    predicted_label, predicted_confidence = max(label_pairs, key=lambda item: item[1])
    rain_probability = max(
        (probability for label, probability in label_pairs if "rain" in label or "storm" in label),
        default=0.0,
    )
    return rain_probability, predicted_label, predicted_confidence


def read_previous_payload() -> dict:
    if not ALERTS_PATH.exists():
        return {}
    try:
        data = json.loads(ALERTS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def status_signature(payload: dict) -> tuple:
    rows = payload.get("cameras", []) if isinstance(payload, dict) else []
    return tuple(sorted(
        (item.get("id"), item.get("status"))
        for item in rows
        if item.get("id")
    ))


def previous_publish_time(payload: dict) -> datetime | None:
    value = payload.get("generated_at") if isinstance(payload, dict) else None
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    session = session_with_headers()
    catalog = load_catalog(session)
    previous_payload = read_previous_payload()

    results: list[dict] = []
    images_to_classify: list[tuple[dict, Image.Image, dict]] = []

    for camera in catalog:
        result = {
            "id": camera["id"],
            "site_slug": camera["site_slug"],
            "site_name": camera["site_name"],
            "zone": camera["zone"],
            "lat": camera["lat"],
            "lon": camera["lon"],
            "camera_name": camera["camera_name"],
            "page_url": camera["page_url"],
            "status": camera.get("initial_status", "not_available"),
            "rain_probability": None,
            "predicted_label": None,
            "confidence": None,
            "message": camera.get("reason", ""),
            "checked_at": iso_now(),
            "image_last_modified": None,
        }

        if not camera.get("weather_relevant"):
            result["status"] = "not_monitored"
            result["message"] = camera.get("reason") or "El encuadre no es adecuado para detectar lluvia."
            results.append(result)
            continue

        snapshot_url = camera.get("snapshot_url")
        if not snapshot_url:
            results.append(result)
            continue

        try:
            image, metadata = fetch_snapshot(session, snapshot_url)
            result["image_last_modified"] = metadata.get("last_modified")
            images_to_classify.append((result, image, metadata))
        except Exception as exc:
            result["status"] = "not_available"
            result["message"] = f"No se pudo obtener una captura reciente: {exc}"
            results.append(result)

    model_bundle = None
    if images_to_classify:
        try:
            logging.info("Cargando modelo visual %s…", MODEL_ID)
            model_bundle = load_weather_model()
        except Exception as exc:
            logging.exception("No se pudo cargar el modelo de visión.")
            for result, _, _ in images_to_classify:
                result["status"] = "error"
                result["message"] = f"Modelo visual no disponible: {exc}"
                results.append(result)
            images_to_classify = []

    for result, image, metadata in images_to_classify:
        try:
            rain_probability, predicted_label, predicted_confidence = classify_image(image, model_bundle)
            result["rain_probability"] = round(rain_probability, 4)
            result["predicted_label"] = predicted_label
            result["confidence"] = round(predicted_confidence, 4)

            if rain_probability >= 0.82:
                result["status"] = "rain"
                result["message"] = "Indicios visuales fuertes de lluvia. Confirmar abriendo la cámara."
            elif rain_probability >= 0.62:
                result["status"] = "possible"
                result["message"] = "La IA observa posibles indicios de lluvia; requiere comprobación visual."
            else:
                result["status"] = "clear"
                result["message"] = "El análisis no encontró indicios visuales suficientes de lluvia."
        except Exception as exc:
            result["status"] = "error"
            result["message"] = f"No se pudo analizar la captura: {exc}"
        results.append(result)

    # Mantener orden estable por zona y sitio.
    results.sort(key=lambda item: (item.get("zone", ""), item.get("site_name", ""), item.get("camera_name", "")))

    alerts = [
        item for item in results
        if item.get("status") in {"rain", "possible"}
    ]
    payload = {
        "status": "ok",
        "generated_at": iso_now(),
        "interval_minutes": 15,
        "source_url": BASE_URL,
        "model": MODEL_ID,
        "model_note": (
            "Clasificación experimental de escenas meteorológicas. "
            "Los resultados son indicios visuales y pueden confundirse con nubes, niebla, "
            "vapor, poca luz o imágenes desactualizadas. No son una medición oficial de lluvia."
        ),
        "directory_sites": len(SITES),
        "camera_count": len(results),
        "evaluated_count": sum(1 for item in results if item.get("status") in {"rain", "possible", "clear"}),
        "alerts": alerts,
        "cameras": results,
    }

    old_time = previous_publish_time(previous_payload)
    heartbeat_due = old_time is None or (utc_now() - old_time) >= timedelta(hours=1)
    state_changed = status_signature(payload) != status_signature(previous_payload)

    if state_changed or heartbeat_due:
        ALERTS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logging.info("Resultados publicados (cambio de estado o actualización horaria).")
    else:
        logging.info("Sin cambios de estado; se conserva el último JSON publicado para evitar commits repetidos.")

    logging.info(
        "Monitor terminado: %s cámaras catalogadas, %s evaluables, %s alertas.",
        len(results),
        payload["evaluated_count"],
        len(alerts),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("Falló el monitor de cámaras: %s", exc)
        fallback = {
            "status": "error",
            "generated_at": iso_now(),
            "interval_minutes": 15,
            "source_url": BASE_URL,
            "model": MODEL_ID,
            "camera_count": 0,
            "evaluated_count": 0,
            "alerts": [],
            "cameras": [],
            "error": str(exc),
        }
        ALERTS_PATH.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
