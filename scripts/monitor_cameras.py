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

# Fuentes IMN con paneles públicos de observación en imagen. Las coordenadas
# de estos dos paneles se leen de la cabecera de sus propios productos.
IMN_STATIONS = [
    {
        "id": "imn-aranjuez",
        "station_name": "Estación IMN · Aranjuez",
        "zone": "Valle Central",
        "lat": 9.937944,
        "lon": -84.069722,
        "page_url": "https://www.imn.ac.cr/especial/estacion.html",
        "snapshot_url": "https://www.imn.ac.cr/especial/redimn.png",
        "source_type": "imn_station",
    },
    {
        "id": "imn-volcan-turrialba",
        "station_name": "Estación IMN · Volcán Turrialba",
        "zone": "Valle Central",
        "lat": 10.019167,
        "lon": -83.756389,
        "page_url": "https://www.imn.ac.cr/especial/estacionVturri.html",
        "snapshot_url": "https://www.imn.ac.cr/especial/redvturri.png",
        "source_type": "imn_station",
    },
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
        "date_header": response.headers.get("Date"),
        "etag": response.headers.get("ETag"),
    }
    return image, metadata


def extract_embedded_timestamp(image: Image.Image) -> datetime | None:
    """Read camera-burned timestamps (especially OVSICORI) from image edges."""
    try:
        import pytesseract
    except Exception:
        return None

    width, height = image.size
    band = max(35, int(height * 0.14))
    regions = [
        image.crop((0, 0, width, min(height, band))),
        image.crop((0, max(0, height - band), width, height)),
    ]
    ocr_text = []
    for region in regions:
        gray = ImageOps.autocontrast(region.convert("L"))
        if gray.width < 1200:
            gray = gray.resize((gray.width * 2, gray.height * 2))
        try:
            ocr_text.append(pytesseract.image_to_string(gray, config="--psm 6"))
        except Exception:
            continue

    text = " ".join(ocr_text)
    iso_match = re.search(
        r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})[ T](\d{1,2}):(\d{2}):(\d{2})\b",
        text,
    )
    if iso_match:
        try:
            values = [int(value) for value in iso_match.groups()]
            local_time = datetime(*values, tzinfo=timezone(timedelta(hours=-6)))
            if local_time <= utc_now() + timedelta(minutes=10):
                return local_time.astimezone(timezone.utc)
        except ValueError:
            pass

    spanish_match = re.search(
        r"\b(?:a las\s+)?(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?).{0,100}?(?:del\s+d[ií]a\s+)?(\d{1,2})/(\d{1,2})/(20\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if spanish_match:
        try:
            hour, minute, meridiem, day, month, year = spanish_match.groups()
            hour = int(hour)
            minute = int(minute)
            if meridiem.lower().startswith("p") and hour != 12:
                hour += 12
            elif meridiem.lower().startswith("a") and hour == 12:
                hour = 0
            local_time = datetime(
                int(year), int(month), int(day), hour, minute,
                tzinfo=timezone(timedelta(hours=-6)),
            )
            if local_time <= utc_now() + timedelta(minutes=10):
                return local_time.astimezone(timezone.utc)
        except ValueError:
            pass

    english_match = re.search(
        r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})\s+(20\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if english_match:
        try:
            month, day, hour, minute, second, year = english_match.groups()
            local_time = datetime.strptime(
                f"{month} {day} {hour}:{minute}:{second} {year}",
                "%b %d %H:%M:%S %Y",
            ).replace(tzinfo=timezone(timedelta(hours=-6)))
            if local_time <= utc_now() + timedelta(minutes=10):
                return local_time.astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def parse_http_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def assess_image_freshness(camera: dict, image: Image.Image, metadata: dict) -> dict:
    embedded = extract_embedded_timestamp(image) if camera.get("source_type") in {"ovsicori", "imn_station"} else None
    http_timestamp = parse_http_timestamp(metadata.get("last_modified"))
    timestamp = embedded or http_timestamp
    timestamp_source = "embedded_ocr" if embedded else ("http_last_modified" if http_timestamp else "not_provided")

    if timestamp is None:
        return {
            "availability_status": "unknown",
            "image_age_minutes": None,
            "image_timestamp": None,
            "image_timestamp_source": timestamp_source,
        }

    age_seconds = max(0.0, (utc_now() - timestamp).total_seconds())
    age_minutes = round(age_seconds / 60.0, 1)
    online_limit = timedelta(minutes=20) if camera.get("source_type") == "imn_station" else CAMERA_ONLINE_MAX_AGE
    if age_seconds <= online_limit.total_seconds():
        availability = "online"
    elif age_seconds <= CAMERA_DELAYED_MAX_AGE.total_seconds():
        availability = "delayed"
    else:
        availability = "stale"

    return {
        "availability_status": availability,
        "image_age_minutes": age_minutes,
        "image_timestamp": timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "image_timestamp_source": timestamp_source,
    }


def load_scene_model():
    import torch
    from transformers import CLIPModel, CLIPProcessor

    torch.set_num_threads(2)
    processor = CLIPProcessor.from_pretrained(SCENE_MODEL_ID)
    model = CLIPModel.from_pretrained(SCENE_MODEL_ID)
    model.eval()
    return torch, processor, model


OUTDOOR_PROMPTS = [
    "An outdoor live weather webcam showing a wide landscape with visible sky, clouds and weather.",
    "An outdoor webcam showing a beach, coastline, ocean or open landscape under the sky.",
    "An outdoor webcam showing a forest canopy, treetops, mountains and the open air.",
    "An outdoor wildlife webcam showing an animal in its natural habitat with visible trees, sky or weather-exposed surroundings.",
]
INDOOR_PROMPTS = [
    "A close-up wildlife webcam showing only an animal with no visible outdoor surroundings or sky.",
    "An indoor animal enclosure, nest box, cage, terrarium, aquarium or room.",
    "A close-up of an animal filling nearly the whole image, with no visible landscape or weather-exposed environment.",
    "An indoor security camera view of a room or building.",
]


def assess_weather_view(image: Image.Image, model_bundle) -> tuple[str, float, float]:
    """Use CLIP to decide whether the image shows a useful outdoor environment."""
    torch, processor, model = model_bundle
    prompts = OUTDOOR_PROMPTS + INDOOR_PROMPTS
    inputs = processor(text=prompts, images=image, return_tensors="pt", padding=True)
    with torch.no_grad():
        scores = model(**inputs).logits_per_image[0]
        probabilities = torch.softmax(scores, dim=0).cpu().tolist()

    outdoor_score = float(sum(probabilities[:len(OUTDOOR_PROMPTS)]))
    indoor_score = float(sum(probabilities[len(OUTDOOR_PROMPTS):]))
    if outdoor_score >= 0.55 and outdoor_score - indoor_score >= 0.12:
        assessment = "outdoor"
    elif indoor_score >= 0.55 and indoor_score - outdoor_score >= 0.12:
        assessment = "not_weather_view"
    else:
        assessment = "scene_uncertain"
    return assessment, round(outdoor_score, 4), round(indoor_score, 4)


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




def parse_localized_number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def extract_imn_station_values(image: Image.Image) -> dict:
    """Extract the numerical readings printed in official IMN station panels."""
    try:
        import pytesseract
        text = pytesseract.image_to_string(image, config="--psm 6")
    except Exception as exc:
        return {"ocr_error": str(exc)}

    compact = re.sub(r"\s+", " ", text)
    patterns = {
        "rain_last_hour_mm": r"Precip\.?\s*[uú]ltima\s+hora\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*mm",
        "rain_since_7am_mm": r"Lluvia\s+acumulada\s+Desde\s+las\s+7\s*a\.?m\.?\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*mm",
        "rain_previous_24h_mm": r"De\s+7\s*a\.?m\.?\s+de\s+ayer\s+a\s+7\s*a\.?m\.?\s+de\s+hoy\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*mm",
        "wind_speed_kmh": r"Velocidad\s+Actual\s+del\s+Viento\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*km/?h",
        "temperature_c": r"Temperatura\s+Actual\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*°?\s*C",
        "humidity_percent": r"Humedad\s+Relativa\s+Actual\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*%",
        "pressure_hpa": r"Presi[oó]n\s+Atmosf[eé]rica\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*hPa",
    }
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, compact, re.IGNORECASE)
        values[key] = parse_localized_number(match.group(1)) if match else None
    values["ocr_excerpt"] = compact[:500]
    return values


def collect_imn_stations(session: requests.Session) -> list[dict]:
    stations = []
    for station in IMN_STATIONS:
        result = {
            "id": station["id"],
            "station_name": station["station_name"],
            "zone": station["zone"],
            "lat": station["lat"],
            "lon": station["lon"],
            "page_url": station["page_url"],
            "source_url": station["snapshot_url"],
            "source_type": "imn_station",
            "status": "not_available",
            "availability_status": "not_available",
            "checked_at": iso_now(),
            "image_timestamp": None,
            "image_age_minutes": None,
            "image_timestamp_source": "not_provided",
            "rain_last_hour_mm": None,
            "rain_since_7am_mm": None,
            "rain_previous_24h_mm": None,
            "wind_speed_kmh": None,
            "temperature_c": None,
            "humidity_percent": None,
            "pressure_hpa": None,
            "rain_observed": False,
        }
        try:
            image, metadata = fetch_snapshot(session, station["snapshot_url"])
            freshness = assess_image_freshness(station, image, metadata)
            result.update(freshness)
            values = extract_imn_station_values(image)
            result.update({key: value for key, value in values.items() if key != "ocr_excerpt"})
            result["status"] = freshness["availability_status"]
            result["last_modified"] = metadata.get("last_modified")
            rain_amount = result.get("rain_last_hour_mm")
            result["rain_observed"] = (
                rain_amount is not None
                and rain_amount > 0
                and result["availability_status"] in {"online", "unknown"}
            )
            if result["availability_status"] == "stale":
                result["message"] = "El panel está accesible, pero la observación impresa tiene más de una hora."
            elif result["availability_status"] == "delayed":
                result["message"] = "El panel contiene datos demorados; no se usa para alertas actuales."
            elif result["availability_status"] == "unknown":
                result["message"] = "Panel accesible; no se pudo leer una hora de observación verificable."
            else:
                result["message"] = "Lectura de estación IMN disponible."
        except Exception as exc:
            result["status"] = "offline"
            result["availability_status"] = "offline"
            result["message"] = f"No se pudo obtener el panel de la estación: {exc}"
        stations.append(result)
    return stations


def status_signature(payload: dict) -> tuple:
    rows = payload.get("cameras", []) if isinstance(payload, dict) else []
    station_rows = payload.get("stations", []) if isinstance(payload, dict) else []
    camera_signature = tuple(sorted(
        (
            item.get("id"),
            item.get("status"),
            item.get("availability_status"),
            item.get("scene_assessment"),
        )
        for item in rows
        if item.get("id")
    ))
    station_signature = tuple(sorted(
        (
            item.get("id"),
            item.get("availability_status"),
            item.get("rain_last_hour_mm"),
        )
        for item in station_rows
        if item.get("id")
    ))
    return camera_signature + station_signature


def previous_publish_time(payload: dict) -> datetime | None:
    value = payload.get("generated_at") if isinstance(payload, dict) else None
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def resolve_snapshot_url(session: requests.Session, camera: dict) -> tuple[str | None, str | None]:
    snapshot_url = camera.get("snapshot_url")
    if snapshot_url:
        return snapshot_url, None

    page_url = camera.get("page_url")
    if not page_url:
        return None, "not_available"

    try:
        page_html, resolved_url = get_page(session, page_url)
        soup = BeautifulSoup(page_html, "html.parser")
        if page_is_offline(soup):
            return None, "offline"
        snapshot_url = extract_snapshot_url(soup, resolved_url)
        return (snapshot_url, None) if snapshot_url else (None, "not_available")
    except Exception as exc:
        logging.info("No se pudo recuperar la ficha %s: %s", camera.get("id"), exc)
        return None, "offline"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    session = session_with_headers()
    catalog = load_catalog(session)
    previous_payload = read_previous_payload()
    previous_rows = {
        item.get("id"): item
        for item in previous_payload.get("cameras", [])
        if isinstance(item, dict) and item.get("id")
    }

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
            "source_type": camera.get("source_type", "webcamscostarica"),
            "coordinate_note": camera.get("coordinate_note"),
            "status": "pending",
            "availability_status": "unknown",
            "scene_assessment": "pending",
            "scene_outdoor_score": None,
            "scene_indoor_score": None,
            "rain_probability": None,
            "predicted_label": None,
            "confidence": None,
            "message": camera.get("reason", ""),
            "checked_at": iso_now(),
            "image_last_modified": None,
            "image_age_minutes": None,
            "image_timestamp": None,
            "image_timestamp_source": "not_provided",
            "recovered": False,
        }

        snapshot_url, resolution_status = resolve_snapshot_url(session, camera)
        if not snapshot_url:
            result["availability_status"] = "offline" if resolution_status == "offline" else "not_available"
            result["status"] = "offline" if resolution_status == "offline" else "not_available"
            result["message"] = (
                "La cámara no está transmitiendo o su ficha indica que no emite."
                if resolution_status == "offline"
                else "No se encontró una imagen pública utilizable. Se volverá a comprobar en el siguiente ciclo."
            )
            results.append(result)
            continue

        try:
            image, metadata = fetch_snapshot(session, snapshot_url)
            result["image_last_modified"] = metadata.get("last_modified")
            result.update(assess_image_freshness(camera, image, metadata))

            if result["availability_status"] == "stale":
                result["status"] = "stale"
                result["message"] = (
                    "La imagen se puede descargar, pero su marca de tiempo indica que lleva más de una hora sin actualizarse. "
                    "No se usa para generar alertas actuales."
                )
                results.append(result)
                continue

            images_to_classify.append((result, image, metadata))
        except Exception as exc:
            result["availability_status"] = "offline"
            result["status"] = "offline"
            result["message"] = f"No se pudo obtener una imagen válida: {exc}"
            results.append(result)

    scene_model_bundle = None
    if images_to_classify:
        try:
            logging.info("Cargando modelo de evaluación de encuadre %s…", SCENE_MODEL_ID)
            scene_model_bundle = load_scene_model()
        except Exception as exc:
            logging.exception("No se pudo cargar el modelo de evaluación de encuadre.")
            for result, _, _ in images_to_classify:
                result["status"] = "error"
                result["scene_assessment"] = "error"
                result["message"] = f"No se pudo evaluar si el encuadre es exterior: {exc}"
                results.append(result)
            images_to_classify = []

    outdoor_images: list[tuple[dict, Image.Image, dict]] = []
    for result, image, metadata in images_to_classify:
        try:
            assessment, outdoor_score, indoor_score = assess_weather_view(image, scene_model_bundle)
            result["scene_assessment"] = assessment
            result["scene_outdoor_score"] = outdoor_score
            result["scene_indoor_score"] = indoor_score

            if assessment == "not_weather_view":
                result["status"] = "not_weather_view"
                result["message"] = (
                    "La IA considera que el encuadre muestra principalmente un espacio interior o un primer plano "
                    "sin suficiente entorno exterior para evaluar el tiempo."
                )
                results.append(result)
            elif assessment == "scene_uncertain":
                result["status"] = "scene_uncertain"
                result["message"] = (
                    "La IA no pudo confirmar que el encuadre muestre suficiente entorno exterior. "
                    "No se genera una alerta meteorológica con esta imagen."
                )
                results.append(result)
            else:
                outdoor_images.append((result, image, metadata))
        except Exception as exc:
            result["status"] = "error"
            result["scene_assessment"] = "error"
            result["message"] = f"No se pudo evaluar el encuadre: {exc}"
            results.append(result)

    weather_model_bundle = None
    if outdoor_images:
        try:
            logging.info("Cargando modelo meteorológico %s…", MODEL_ID)
            weather_model_bundle = load_weather_model()
        except Exception as exc:
            logging.exception("No se pudo cargar el modelo meteorológico.")
            for result, _, _ in outdoor_images:
                result["status"] = "error"
                result["message"] = f"Modelo meteorológico no disponible: {exc}"
                results.append(result)
            outdoor_images = []

    for result, image, metadata in outdoor_images:
        try:
            rain_probability, predicted_label, predicted_confidence = classify_image(image, weather_model_bundle)
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

            if result.get("availability_status") == "delayed":
                result["message"] += " La imagen está demorada; no se usa como alerta de lluvia actual."
            elif result.get("availability_status") == "unknown":
                result["message"] += " La fuente no publica una marca de tiempo verificable."
        except Exception as exc:
            result["status"] = "error"
            result["message"] = f"No se pudo analizar la captura: {exc}"
        results.append(result)

    # Marcar explícitamente cámaras que regresaron después de estar caídas o desactualizadas.
    for result in results:
        previous = previous_rows.get(result.get("id"), {})
        previous_availability = previous.get("availability_status")
        current_availability = result.get("availability_status")
        if previous_availability in {"offline", "stale", "not_available"} and current_availability in {"online", "delayed", "unknown"}:
            result["recovered"] = True
            result["message"] = "La cámara volvió a proporcionar una imagen. " + result.get("message", "")

    results.sort(key=lambda item: (item.get("zone", ""), item.get("site_name", ""), item.get("camera_name", "")))

    alerts = [
        item for item in results
        if item.get("status") in {"rain", "possible"}
        and item.get("scene_assessment") == "outdoor"
        and item.get("availability_status") in {"online", "unknown"}
    ]
    recovered_cameras = [item for item in results if item.get("recovered")]
    availability_counts = {
        state: sum(1 for item in results if item.get("availability_status") == state)
        for state in ("online", "delayed", "stale", "offline", "not_available", "unknown")
    }
    scene_counts = {
        state: sum(1 for item in results if item.get("scene_assessment") == state)
        for state in ("outdoor", "not_weather_view", "scene_uncertain", "error", "pending")
    }
    payload = {
        "status": "ok",
        "generated_at": iso_now(),
        "interval_minutes": 15,
        "source_url": BASE_URL,
        "sources": [
            {"name": "Webcams Costa Rica", "url": BASE_URL, "type": "public_webcams"},
            {"name": "OVSICORI-UNA", "url": "https://www.ovsicori.una.ac.cr/index.php/camaras", "type": "official_volcano_cameras"},
            {
                "name": "Parapente Pura Vida",
                "url": "https://parapentepuravida.com/eltiempo/",
                "type": "methodology_reference",
                "note": "Se usa como referencia metodológica de lectura combinada; sus estaciones y embeds no se ingieren como mediciones hasta disponer de un endpoint público estable y verificable."
            },
        ],
        "model": MODEL_ID,
        "scene_model": SCENE_MODEL_ID,
        "model_note": (
            "La evaluación de encuadre y la clasificación meteorológica son experimentales. "
            "Los indicios visuales pueden confundirse con nubes, niebla, vapor, oscuridad o imágenes desactualizadas. "
            "No son una medición oficial de lluvia."
        ),
        "directory_sites": len(SITES),
        "camera_count": len(results),
        "evaluated_count": sum(
            1 for item in results
            if item.get("scene_assessment") == "outdoor" and item.get("status") in {"rain", "possible", "clear"}
        ),
        "availability_counts": availability_counts,
        "scene_counts": scene_counts,
        "alerts": alerts,
        "recovered_cameras": recovered_cameras,
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
        "Monitor terminado: %s cámaras catalogadas, %s evaluables, %s alertas; disponibilidad=%s; encuadres=%s.",
        len(results),
        payload["evaluated_count"],
        len(alerts),
        availability_counts,
        scene_counts,
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
            "scene_model": SCENE_MODEL_ID,
            "camera_count": 0,
            "evaluated_count": 0,
            "alerts": [],
            "cameras": [],
            "error": str(exc),
        }
        ALERTS_PATH.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
