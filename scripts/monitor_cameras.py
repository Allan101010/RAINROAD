#!/usr/bin/env python3
"""
RainTrack CR - monitor visual de cámaras públicas de Costa Rica.

Descubre las cámaras de cada ficha de Webcams Costa Rica, obtiene las
capturas públicas disponibles y clasifica la escena con un modelo abierto
de condiciones meteorológicas. No intenta acceder a cámaras privadas ni
extraer vídeo de plataformas externas.

El análisis es orientativo: "rain/storm" es una clase del modelo, no una medición ni una probabilidad meteorológica calibrada.
Una cámara por sí sola nunca confirma lluvia; los registros instrumentales se informan por separado.
"""

from __future__ import annotations

import io
import json
import logging
import re
import sys
import time
import unicodedata
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
CAMERA_ONLINE_MAX_AGE = timedelta(minutes=20)
CAMERA_DELAYED_MAX_AGE = timedelta(hours=1)
CAMERA_NAME_OVERRIDES = {
    "punta-islita-default": "Comedero bajo",
    "punta-islita-lapas-rojas-copa": "Vista de copa de las lapas rojas",
}
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

# Estaciones IMN con tablas HTML públicas de observaciones.
# Las coordenadas de las estaciones nuevas son referencias de localidad para el mapa;
# no deben interpretarse como la posición topográfica exacta de cada sensor.
IMN_STATIONS = [
    {
        "id": "imn-aranjuez",
        "station_name": "Estación IMN · Aranjuez",
        "zone": "Valle Central",
        "lat": 9.937944,
        "lon": -84.069722,
        "page_url": "https://www.imn.ac.cr/especial/estacion.html",
        "snapshot_url": "https://www.imn.ac.cr/especial/redimn.png",
        "table_url": "https://www.imn.ac.cr/especial/tablas/imn.html",
        "coordinate_note": "Coordenadas de referencia del producto público del IMN.",
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
        "table_url": "https://www.imn.ac.cr/especial/tablas/turrialba.html",
        "coordinate_note": "Coordenada de referencia del Volcán Turrialba.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-quepos",
        "station_name": "Estación IMN · Quepos",
        "zone": "Pacífico Central",
        "lat": 9.4310,
        "lon": -84.1610,
        "page_url": "https://www.imn.ac.cr/especial/redquepos.png",
        "snapshot_url": "https://www.imn.ac.cr/especial/redquepos.png",
        "table_url": "https://www.imn.ac.cr/especial/tablas/quepos.html",
        "coordinate_note": "Ubicación de referencia de Quepos; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-la-ligia",
        "station_name": "Estación IMN · La Ligia (Parrita)",
        "zone": "Pacífico Central",
        "lat": 9.5200,
        "lon": -84.3250,
        "page_url": "https://www.imn.ac.cr/especial/estacionligia.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/laligia.html",
        "coordinate_note": "Ubicación de referencia de Parrita/La Ligia; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-horquetas",
        "station_name": "Estación IMN · Horquetas",
        "zone": "Zona Norte",
        "lat": 10.3270,
        "lon": -83.9370,
        "page_url": "https://www.imn.ac.cr/especial/tablas/horquetas.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/horquetas.html",
        "coordinate_note": "Ubicación de referencia de Horquetas, Sarapiquí; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-universidad-para-la-paz",
        "station_name": "Estación IMN · Universidad para la Paz",
        "zone": "Valle Central",
        "lat": 9.9160,
        "lon": -84.2420,
        "page_url": "https://www.imn.ac.cr/especial/tablas/upaz.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/upaz.html",
        "coordinate_note": "Ubicación de referencia de Universidad para la Paz, Mora; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-santa-clara",
        "station_name": "Estación IMN · ITCR Santa Clara",
        "zone": "Zona Norte",
        "lat": 10.3650,
        "lon": -84.5120,
        "page_url": "https://www.imn.ac.cr/especial/tablas/staclara.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/staclara.html",
        "coordinate_note": "Ubicación de referencia de Santa Clara de San Carlos; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-montana-sagrada",
        "station_name": "Estación IMN · Montaña Sagrada",
        "zone": "Zona Norte",
        "lat": 10.3810,
        "lon": -84.3450,
        "page_url": "https://www.imn.ac.cr/especial/tablas/msagrada.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/msagrada.html",
        "coordinate_note": "Ubicación de referencia de Aguas Zarcas; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-sitio-mata",
        "station_name": "Estación IMN · Sitio Mata",
        "zone": "Caribe Sur",
        "lat": 9.9900,
        "lon": -83.6390,
        "page_url": "https://www.imn.ac.cr/especial/tablas/sitiomata.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/sitiomata.html",
        "coordinate_note": "Ubicación de referencia de Sitio Mata, Turrialba; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-la-pastora",
        "station_name": "Estación IMN · Escuela La Pastora",
        "zone": "Caribe Sur",
        "lat": 9.9400,
        "lon": -83.7800,
        "page_url": "https://www.imn.ac.cr/especial/tablas/lapastora.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/lapastora.html",
        "coordinate_note": "Ubicación de referencia de La Pastora, Turrialba; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-aeropuerto-sjo-07",
        "station_name": "Estación IMN · Aeropuerto Juan Santamaría 07",
        "zone": "Valle Central",
        "lat": 9.9939,
        "lon": -84.2088,
        "page_url": "https://www.imn.ac.cr/especial/tablas/aijs07.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/aijs07.html",
        "coordinate_note": "Coordenada de referencia del aeropuerto; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-sixaola",
        "station_name": "Estación IMN · Sixaola",
        "zone": "Caribe Sur",
        "lat": 9.5300,
        "lon": -82.6200,
        "page_url": "https://www.imn.ac.cr/especial/tablas/sixaola.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/sixaola.html",
        "coordinate_note": "Ubicación de referencia de Sixaola, Talamanca; no representa necesariamente el sensor exacto.",
        "source_type": "imn_station",
    },
    {
        "id": "imn-aeropuerto-liberia-07",
        "station_name": "Estación IMN · Aeropuerto Daniel Oduber 07",
        "zone": "Pacífico Norte",
        "lat": 10.5933,
        "lon": -85.5444,
        "page_url": "https://www.imn.ac.cr/especial/tablas/lib07.html",
        "snapshot_url": None,
        "table_url": "https://www.imn.ac.cr/especial/tablas/lib07.html",
        "coordinate_note": "Coordenada de referencia del aeropuerto; no representa necesariamente el sensor exacto.",
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
                camera_name = CAMERA_NAME_OVERRIDES.get(f"{site_slug}-{cam_slug}", camera_name)

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
    headers = {
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    candidates = [cache_busted(url)]
    if candidates[0] != url:
        candidates.append(url)

    last_error = None
    for candidate_url in candidates:
        try:
            response = session.get(candidate_url, timeout=HTTP_TIMEOUT, headers=headers)
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
                "retrieved_url": candidate_url,
            }
            return image, metadata
        except Exception as exc:
            last_error = exc

    raise ValueError(f"No se pudo leer la imagen con ni sin parámetro anticaché: {last_error}")


def extract_embedded_timestamp(image: Image.Image, source_type: str | None = None) -> datetime | None:
    """Read camera-burned timestamps (especially OVSICORI) from image edges."""
    try:
        import pytesseract
    except Exception:
        return None

    width, height = image.size
    band = max(35, int(height * 0.14))
    if source_type == "imn_station":
        # Los paneles IMN imprimen la fecha dentro del encabezado y el texto
        # de actualización puede ocupar más de la franja superior.
        regions = [
            image,
            image.crop((0, 0, width, min(height, max(band, int(height * 0.28))))),
        ]
    else:
        regions = [
            image.crop((0, 0, width, min(height, band))),
            image.crop((0, max(0, height - band), width, height)),
        ]
    ocr_text = []
    for region in regions:
        gray = ImageOps.autocontrast(region.convert("L"))
        if gray.width < 1600:
            gray = gray.resize((gray.width * 2, gray.height * 2))
        configs = ("--psm 6", "--psm 11") if source_type == "imn_station" else ("--psm 6",)
        for config in configs:
            try:
                ocr_text.append(pytesseract.image_to_string(gray, config=config))
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

    date_first_match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(20\d{2}).{0,100}?(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)",
        text,
        re.IGNORECASE,
    )
    if date_first_match:
        try:
            day, month, year, hour, minute, meridiem = date_first_match.groups()
            hour = int(hour)
            if meridiem.lower().startswith("p") and hour != 12:
                hour += 12
            elif meridiem.lower().startswith("a") and hour == 12:
                hour = 0
            local_time = datetime(
                int(year), int(month), int(day), hour, int(minute),
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
    embedded = extract_embedded_timestamp(image, camera.get("source_type")) if camera.get("source_type") in {"ovsicori", "imn_station"} else None
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
    "An outdoor animal feeder, open-air aviary or wildlife rehabilitation patio with visible branches, leaves, natural daylight or open sky, even when an animal fills most of the frame.",
]
INDOOR_PROMPTS = [
    "A close-up wildlife webcam showing only an animal, with no visible foliage, sky, natural daylight or outdoor surroundings.",
    "A fully enclosed indoor animal enclosure, nest box, cage, terrarium, aquarium or room with no visible exterior environment.",
    "A close-up of an animal filling nearly the whole image, with no visible outdoor context or weather-exposed environment.",
    "An indoor security camera view of a room or building.",
    "A rescued animal resting on blankets inside a room, with no visible outdoor habitat or natural environment.",
]

# Contextos exteriores confirmados en las fichas públicas y capturas de estas cámaras.
# Se conservan como aptas aunque el animal ocupe gran parte del encuadre.
CAMERA_OUTDOOR_CONTEXT_OVERRIDES = {
    "punta-islita-default": "comedero exterior entre ramas y vegetación, con luz natural en el bosque de Punta Islita",
    "punta-islita-lapas-rojas-copa": "comedero en la copa de los árboles, con ramas y bosque seco visibles",
    "toucan-rescue-ranch-toucan-tv": "aviario con malla, ramas, plantas y luz natural del entorno exterior",
    "toucan-rescue-ranch-toucan-sloth-playground": "patio al aire libre con árboles, ramas y césped",
}


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
    if value is None:
        return None
    try:
        text = re.sub(r"\s+", "", str(value)).replace("\u00a0", "")
        if not text:
            return None
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        return float(text)
    except (TypeError, ValueError):
        return None





def normalize_imn_header(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")


def parse_imn_local_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value.strip().lower())
    text = text.replace("a. m.", "am").replace("p. m.", "pm")
    text = text.replace("a.m.", "am").replace("p.m.", "pm")
    text = text.replace("a. m", "am").replace("p. m", "pm")
    text = re.sub(r"\s+", " ", text)
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M %p", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            local = datetime.strptime(text, fmt).replace(tzinfo=timezone(timedelta(hours=-6)))
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def extract_imn_table_values(html: str) -> dict:
    """Read the IMN's accessible HTML observation tables instead of OCRing its PNG."""
    soup = BeautifulSoup(html, "html.parser")
    parsed_tables = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for index, row in enumerate(rows):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if not cells or normalize_imn_header(cells[0]) != "fecha":
                continue

            headers = [normalize_imn_header(cell) for cell in cells]
            data_row = None
            for candidate in rows[index + 1:]:
                values = [
                    cell.get_text(" ", strip=True)
                    for cell in candidate.find_all(["th", "td"])
                    if cell.get_text(" ", strip=True)
                ]
                if values and len(headers) > 1:
                    # Algunas tablas del IMN envuelven la fila en una sola celda;
                    # otras dejan celdas vacías o separan la fecha del resto.
                    raw = " ".join(values)
                    match = re.match(
                        r"^(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:a\.?\s*m\.?|p\.?\s*m\.?)?)?)\s+(.+)$",
                        raw,
                        re.IGNORECASE,
                    )
                    if match:
                        date_text, remainder = match.groups()
                        numeric_values = re.findall(
                            r"[-+]?(?:\d{1,3}(?:[.\s]\d{3})+|\d+)(?:[.,]\d+)?",
                            remainder,
                        )
                        if len(numeric_values) >= len(headers) - 1:
                            values = [date_text] + numeric_values[:len(headers) - 1]
                if len(values) >= len(headers) and values[0]:
                    data_row = dict(zip(headers, values))
                    break
            if data_row:
                parsed_tables.append(data_row)
            break

    hourly_candidates = [row for row in parsed_tables if "lluvia" in row]
    hourly = next(
        (row for row in hourly_candidates if "temp" in row or "temperatura" in row),
        hourly_candidates[0] if hourly_candidates else {},
    )
    accumulated = next(
        (row for row in parsed_tables if "sum_lluv" in row or "lluv_ayer" in row),
        {},
    )
    current = next(
        (row for row in parsed_tables if any(key in row for key in ("hr", "velocidad", "direccion", "td"))),
        {},
    )
    if not current:
        current = next(
            (row for row in parsed_tables if "vmax" in row or "vpmax" in row),
            {},
        )

    timestamps = [
        parsed
        for parsed in (parse_imn_local_datetime(row.get("fecha")) for row in parsed_tables)
        if parsed is not None
    ]
    timestamp = max(timestamps) if timestamps else None
    table_debug = " || ".join(
        f"headers={','.join(row.keys())}; fecha={row.get('fecha', '')}"
        for row in parsed_tables[:5]
    )
    return {
        "image_timestamp": timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z") if timestamp else None,
        "image_timestamp_source": "imn_html_table" if timestamp else "not_provided",
        "rain_last_hour_mm": parse_localized_number(hourly.get("lluvia")),
        "rain_since_7am_mm": parse_localized_number(accumulated.get("sum_lluv")),
        "rain_previous_24h_mm": parse_localized_number(accumulated.get("lluv_ayer")),
        "temperature_c": parse_localized_number(current.get("temp")) or parse_localized_number(hourly.get("temp")),
        "humidity_percent": parse_localized_number(current.get("hr")),
        "wind_speed_kmh": parse_localized_number(current.get("velocidad")),
        "wind_direction_deg": parse_localized_number(current.get("direccion") or current.get("direction")),
        "wind_gust_kmh": parse_localized_number(current.get("vmax") or current.get("vpmax") or accumulated.get("vmax") or accumulated.get("vpmax")),
        "dew_point_c": parse_localized_number(current.get("td")),
        "pressure_hpa": parse_localized_number(hourly.get("p_atm") or hourly.get("pres_mb") or hourly.get("pres_atm") or current.get("p_atm") or current.get("pres_mb") or current.get("pres_atm")),
        "table_row_count": len(parsed_tables),
        "table_debug": table_debug,
        "data_source": "imn_html_table",
    }


def assess_station_freshness(timestamp_value: str | None) -> dict:
    if not timestamp_value:
        return {
            "availability_status": "unknown",
            "image_age_minutes": None,
        }
    try:
        timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        age_seconds = (utc_now() - timestamp.astimezone(timezone.utc)).total_seconds()
        if age_seconds < -600:
            return {"availability_status": "unknown", "image_age_minutes": None}
        age_minutes = round(max(0.0, age_seconds) / 60.0, 1)
        if age_seconds <= timedelta(minutes=20).total_seconds():
            status = "online"
        elif age_seconds <= timedelta(hours=1).total_seconds():
            status = "delayed"
        else:
            status = "stale"
        return {"availability_status": status, "image_age_minutes": age_minutes}
    except (TypeError, ValueError):
        return {"availability_status": "unknown", "image_age_minutes": None}


def fetch_imn_table(session: requests.Session, url: str) -> dict:
    response = session.get(
        url,
        timeout=HTTP_TIMEOUT,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    response.raise_for_status()
    if len(response.content) > 3 * 1024 * 1024:
        raise ValueError("La tabla meteorológica supera el tamaño permitido.")
    try:
        html = response.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        html = response.text
    values = extract_imn_table_values(html)
    if not values.get("table_row_count"):
        raise ValueError("La página del IMN no contiene tablas de observaciones reconocibles.")
    return values


def extract_imn_station_values(image: Image.Image) -> dict:
    """Extract the numerical readings printed in official IMN station panels."""
    try:
        import pytesseract
        text = pytesseract.image_to_string(image, config="--psm 6")
    except Exception as exc:
        return {"ocr_error": str(exc)}

    compact = re.sub(r"\s+", " ", text)
    patterns = {
        "rain_last_hour_mm": r"(?:pre)?cip\w*.*?ultim\w*\s+hor\w*.*?([0-9]+(?:[.,][0-9]+)?)",
        "rain_since_7am_mm": r"lluvia.*?acumulad\w*.*?7\s*a\.?m\.?\s*.*?([0-9]+(?:[.,][0-9]+)?)",
        "rain_previous_24h_mm": r"de\s+7\s*a\.?m\.?\s+de\s+ayer.*?7\s*a\.?m\.?\s+de\s+hoy.*?([0-9]+(?:[.,][0-9]+)?)",
        "wind_speed_kmh": r"velocid\w*.*?([0-9]+(?:[.,][0-9]+)?)\s*km/?h",
        "temperature_c": r"temper\w*.*?([0-9]+(?:[.,][0-9]+)?)\s*°?\s*c",
        "humidity_percent": r"hum\w*.*?([0-9]+(?:[.,][0-9]+)?)\s*%",
        "pressure_hpa": r"pres\w*.*?([0-9]+(?:[.,][0-9]+)?)\s*hpa",
    }
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, compact, re.IGNORECASE)
        values[key] = parse_localized_number(match.group(1)) if match else None

    # Fallbacks conservadores cuando el OCR confunde las etiquetas, pero
    # conserva la unidad junto al número.
    if values["wind_speed_kmh"] is None:
        match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*km/?h", compact, re.IGNORECASE)
        values["wind_speed_kmh"] = parse_localized_number(match.group(1)) if match else None
    if values["temperature_c"] is None:
        matches = re.findall(r"([0-9]{1,2}(?:[.,][0-9]+)?)\s*°?\s*c\b", compact, re.IGNORECASE)
        plausible = [parse_localized_number(value) for value in matches]
        plausible = [value for value in plausible if value is not None and -5 <= value <= 50]
        values["temperature_c"] = plausible[0] if plausible else None
    if values["humidity_percent"] is None:
        matches = re.findall(r"([0-9]{1,3})\s*%", compact)
        plausible = [int(value) for value in matches if 0 <= int(value) <= 100]
        values["humidity_percent"] = plausible[0] if plausible else None

    values["ocr_excerpt"] = compact[:1500]
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
            "coordinate_note": station.get("coordinate_note"),
            "page_url": station.get("page_url") or station["table_url"],
            "source_url": station.get("table_url") or station["snapshot_url"],
            "table_url": station.get("table_url"),
            "snapshot_url": station["snapshot_url"],
            "source_type": "imn_station",
            "data_source": "imn_html_table",
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
            "wind_direction_deg": None,
            "wind_gust_kmh": None,
            "dew_point_c": None,
            "temperature_c": None,
            "humidity_percent": None,
            "pressure_hpa": None,
            "rain_observed": False,
        }
        try:
            table_values = fetch_imn_table(session, station["table_url"])
            result.update(table_values)
            result.update(assess_station_freshness(result.get("image_timestamp")))
            result["status"] = result["availability_status"]
            rain_amount = result.get("rain_last_hour_mm")
            result["rain_observed"] = (
                rain_amount is not None
                and rain_amount > 0
                and result["availability_status"] == "online"
                and result.get("image_timestamp_source") == "imn_html_table"
            )
            if result["availability_status"] == "stale":
                result["message"] = "La tabla del IMN está accesible, pero su última observación tiene más de una hora."
            elif result["availability_status"] == "delayed":
                result["message"] = "La observación del IMN tiene entre 20 y 60 minutos; no se usa para alertas inmediatas."
            elif result["availability_status"] == "unknown":
                result["message"] = "La tabla está accesible, pero no se pudo verificar la hora de observación."
            else:
                result["message"] = "Lectura instrumental reciente obtenida directamente de la tabla HTML del IMN."
            logging.info(
                "IMN %s tabla: filas=%s detalle=%s hora=%s lluvia_hora=%s lluvia_7am=%s temperatura=%s viento=%s humedad=%s estado=%s",
                station["id"],
                result.get("table_row_count"),
                result.get("table_debug"),
                result.get("image_timestamp"),
                result.get("rain_last_hour_mm"),
                result.get("rain_since_7am_mm"),
                result.get("temperature_c"),
                result.get("wind_speed_kmh"),
                result.get("humidity_percent"),
                result.get("availability_status"),
            )
            result.pop("table_debug", None)
        except Exception as exc:
            result["status"] = "offline"
            result["availability_status"] = "offline"
            result["data_source"] = "imn_html_table_unavailable"
            result["message"] = f"No se pudo obtener la tabla de observaciones del IMN: {exc}"
            logging.warning("IMN %s: %s", station["id"], result["message"])
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
            item.get("image_timestamp"),
            item.get("rain_last_hour_mm"),
            item.get("rain_since_7am_mm"),
            item.get("temperature_c"),
            item.get("wind_speed_kmh"),
            item.get("wind_direction_deg"),
            item.get("wind_gust_kmh"),
            item.get("dew_point_c"),
            item.get("humidity_percent"),
            item.get("pressure_hpa"),
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
            "scene_context_override": None,
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
            context_override = CAMERA_OUTDOOR_CONTEXT_OVERRIDES.get(result.get("id"))
            if context_override:
                assessment = "outdoor"
                result["scene_context_override"] = context_override
                logging.info("Cámara %s: entorno exterior verificado; se conserva para análisis meteorológico.", result.get("id"))
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
            model_score = round(rain_probability, 4)
            result["model_score"] = model_score
            # Campo heredado para compatibilidad con lectores anteriores.
            # No debe interpretarse como probabilidad meteorológica calibrada.
            result["rain_probability"] = model_score
            result["predicted_label"] = predicted_label
            result["confidence"] = round(predicted_confidence, 4)

            if rain_probability >= 0.82:
                result["signal_level"] = "high"
                result["status"] = "possible"
                result["message"] = (
                    "El clasificador detecta una señal visual elevada compatible con lluvia, "
                    "pero no la confirma. Contrastar con otras cámaras, radar o estaciones."
                )
            elif rain_probability >= 0.62:
                result["signal_level"] = "moderate"
                result["status"] = "possible"
                result["message"] = (
                    "El clasificador detecta una señal visual compatible con lluvia; "
                    "requiere corroboración independiente."
                )
            else:
                result["signal_level"] = "low"
                result["status"] = "clear"
                result["message"] = "El clasificador no encontró una señal visual suficiente de lluvia."

            if result.get("scene_context_override"):
                result["message"] += " Contexto exterior verificado: " + result["scene_context_override"] + "."
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

    # Estaciones IMN: lecturas instrumentales independientes del análisis visual.
    stations = collect_imn_stations(session)
    station_alerts = [
        {
            "alert_type": "station",
            "status": "rain",
            "station_id": station["id"],
            "station_name": station["station_name"],
            "site_name": station["station_name"],
            "camera_name": station["station_name"],
            "page_url": station["page_url"],
            "rain_last_hour_mm": station.get("rain_last_hour_mm"),
            "rain_since_7am_mm": station.get("rain_since_7am_mm"),
            "availability_status": station.get("availability_status"),
            "image_timestamp": station.get("image_timestamp"),
        }
        for station in stations
        if station.get("rain_observed")
    ]

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
                "name": "IMN · estaciones automáticas",
                "url": "https://www.imn.ac.cr/es/web/imn/estaciones-automaticas",
                "type": "official_station_observations",
                "note": "Se consultan 13 tablas HTML públicas: Aranjuez, Volcán Turrialba, Quepos, La Ligia, Horquetas, Universidad para la Paz, ITCR Santa Clara, Montaña Sagrada, Sitio Mata, La Pastora, los aeropuertos Juan Santamaría y Daniel Oduber, y Sixaola. El IMN advierte que sus datos son preliminares y pueden retrasarse."
            },
            {
                "name": "Parapente Pura Vida",
                "url": "https://parapentepuravida.com/eltiempo/",
                "type": "methodology_reference",
                "note": "Se toma como referencia su triangulación por zona: estaciones, viento, satélite, pronóstico y cámaras. RainTrack consulta directamente las tablas del IMN cuando están disponibles y no depende de los embeds de terceros."
            },
            {
                "name": "NEOJACO · WeatherLink",
                "url": "https://www.weatherlink.com/embeddablePage/show/893d2aa1a69d47928c05b4c1c8e1b6c0/slim",
                "type": "external_station_widget",
                "note": "Panel público visible desde el marcador de Jacó; no se ingieren sus valores para alertas automáticas porque la API de condiciones actuales requiere token de cuenta."
            },
        ],
        "model": MODEL_ID,
        "scene_model": SCENE_MODEL_ID,
        "model_note": (
            "La evaluación de encuadre y la clasificación meteorológica son experimentales. "
            "La puntuación model_score/rain_probability es una salida interna del clasificador, no una probabilidad meteorológica calibrada. "
            "Una cámara por sí sola no confirma lluvia: las señales visuales requieren corroboración y las mediciones instrumentales se muestran por separado."
        ),
        "directory_sites": len(SITES),
        "camera_count": len(results),
        "station_count": len(stations),
        "evaluated_count": sum(
            1 for item in results
            if item.get("scene_assessment") == "outdoor" and item.get("status") in {"rain", "possible", "clear"}
        ),
        "availability_counts": availability_counts,
        "scene_counts": scene_counts,
        "station_availability_counts": {
            state: sum(1 for item in stations if item.get("availability_status") == state)
            for state in ("online", "delayed", "stale", "offline", "unknown", "not_available")
        },
        "alerts": alerts,
        "station_alerts": station_alerts,
        "recovered_cameras": recovered_cameras,
        "cameras": results,
        "stations": stations,
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
        len(alerts) + len(station_alerts),
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
            "station_count": 0,
            "evaluated_count": 0,
            "alerts": [],
            "station_alerts": [],
            "cameras": [],
            "stations": [],
            "error": str(exc),
        }
        ALERTS_PATH.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
