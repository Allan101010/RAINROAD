#!/usr/bin/env python3
"""
RainTrack CR — recolector de eventos multi-amenaza.
Publica un snapshot JSON para GitHub Pages. Usa datos públicos, conserva
el último snapshot válido si una fuente falla y marca los datos como stale.
La ausencia de datos nunca se interpreta como ausencia de peligro.
"""
from __future__ import annotations
import json, math, os, re, sys, tempfile, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "hazards.json"
SCHEMA_VERSION = 1
COLLECTOR_VERSION = "1.0.0"
USER_AGENT = "RainTrackCR/2.0 (+https://github.com/Allan101010/raintrack-cr)"
TIMEOUT_SECONDS = 22
MAX_RESPONSE_BYTES = 18 * 1024 * 1024
CR_REFERENCE = (9.9, -84.1)
CR_NEAR_KM = 250
CENTRAL_AMERICA_KM = 850

SOURCE_REGISTRY = [
    {"id":"imn","name":"IMN Costa Rica","url":"https://www.imn.ac.cr/"},
    {"id":"cne","name":"CNE Costa Rica","url":"https://www.cne.go.cr/"},
    {"id":"ovs","name":"OVSICORI-UNA","url":"https://www.ovsicori.una.ac.cr/sistemas/actividad-volcanica/"},
    {"id":"sinamot","name":"SINAMOT","url":"https://www.sinamot.una.ac.cr/"},
    {"id":"usgs","name":"USGS Earthquakes","url":"https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php"},
    {"id":"nhc","name":"NOAA National Hurricane Center","url":"https://www.nhc.noaa.gov/CurrentStorms.json"},
    {"id":"gdacs","name":"GDACS","url":"https://www.gdacs.org/gdacsapi/swagger/index.html"},
    {"id":"swpc","name":"NOAA Space Weather Prediction Center","url":"https://www.swpc.noaa.gov/"},
    {"id":"nasa","name":"NASA DONKI / EONET","url":"https://api.nasa.gov/"},
    {"id":"tsunami","name":"NOAA Tsunami Warning Centers","url":"https://www.tsunami.gov/?page=productRetrieval"},
]

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            seconds = float(value)
            if seconds > 10_000_000_000:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    for pattern in ("%Y %b %d %H%M UTC", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None

def text_value(value: Any, fallback: str = "") -> str:
    if value is None or isinstance(value, (dict, list)):
        return fallback
    return str(value).strip() or fallback

def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None

def haversine_km(lat: float, lon: float, ref_lat: float = CR_REFERENCE[0], ref_lon: float = CR_REFERENCE[1]) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat), math.radians(ref_lat)
    dp, dl = math.radians(ref_lat - lat), math.radians(ref_lon - lon)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def location_relevance(lat: float | None, lon: float | None, text: str = "") -> tuple[str, str, float | None]:
    lowered = text.lower()
    if any(term in lowered for term in ("costa rica", "san josé", "san jose", "guanacaste", "puntarenas", "limón", "limon")):
        return "costa_rica", "Costa Rica", 0.0
    if lat is None or lon is None:
        return "global", "Global", None
    distance = haversine_km(lat, lon)
    if distance <= CR_NEAR_KM:
        return "costa_rica", "Costa Rica y alrededores", round(distance)
    if distance <= CENTRAL_AMERICA_KM:
        return "regional", "Centroamérica y Caribe", round(distance)
    return "global", "Global", round(distance)

def severity_from_alertlevel(value: Any) -> str:
    level = text_value(value).lower()
    if "red" in level: return "critical"
    if "orange" in level: return "high"
    if "yellow" in level: return "moderate"
    if "green" in level: return "low"
    return "info"

def severity_rank(value: str) -> int:
    return {"critical":5,"high":4,"moderate":3,"low":2,"info":1}.get(value, 0)

def make_event(*, event_id: str, event_type: str, title: str, summary: str,
               source_id: str, source_name: str, source_url: str, event_url: str = "",
               observed_at: datetime | None = None, lat: float | None = None,
               lon: float | None = None, severity: str = "info", status: str = "reported",
               region: str = "", relevance: str | None = None,
               relevance_label: str | None = None, distance_km: float | None = None,
               tags: list[str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    inferred, inferred_label, inferred_distance = location_relevance(lat, lon, region or title)
    return {
        "id":f"{source_id}:{event_id}", "source_event_id":str(event_id),
        "type":event_type, "title":title[:220], "summary":summary[:900],
        "source_id":source_id, "source_name":source_name, "source_url":source_url,
        "url":event_url if event_url.startswith("https://") else source_url,
        "observed_at":iso(observed_at) if observed_at else None,
        "lat":round(lat,5) if lat is not None else None,
        "lon":round(lon,5) if lon is not None else None,
        "severity":severity if severity in {"critical","high","moderate","low","info"} else "info",
        "status":status, "region":region or inferred_label,
        "relevance":relevance or inferred, "relevance_label":relevance_label or inferred_label,
        "distance_to_cr_km":distance_km if distance_km is not None else inferred_distance,
        "tags":tags or [], "metadata":metadata or {}, "stale":False,
    }

def parse_usgs(payload: dict[str, Any], now: datetime, source_id: str = "usgs_global") -> list[dict[str, Any]]:
    source_name = "USGS · Earthquake Hazards Program"
    source_url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php"
    events = []
    for feature in payload.get("features", []) or []:
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2: continue
        lon, lat = number(coords[0]), number(coords[1])
        magnitude = number(props.get("mag"))
        if lat is None or lon is None or magnitude is None: continue
        depth = number(coords[2]) if len(coords) > 2 else None
        tsunami_indicator = props.get("tsunami") == 1
        severity = "critical" if magnitude >= 7 else "high" if magnitude >= 6 else "moderate" if magnitude >= 5 else "low"
        place = text_value(props.get("place"), "Ubicación no especificada")
        summary = [f"Magnitud M{magnitude:.1f}"]
        if depth is not None: summary.append(f"profundidad {depth:.1f} km")
        if tsunami_indicator:
            summary.append("USGS registra un indicador de tsunami asociado; no confirma una amenaza para Costa Rica")
        events.append(make_event(
            event_id=text_value(feature.get("id"), text_value(props.get("code"), f"{props.get('time','')}-{place}")),
            event_type="earthquake", title=f"Sismo M{magnitude:.1f} · {place}",
            summary=" · ".join(summary), source_id=source_id, source_name=source_name,
            source_url=source_url, event_url=text_value(props.get("url"), source_url),
            observed_at=parse_datetime(props.get("time")), lat=lat, lon=lon,
            severity=severity, region=place, tags=["tsunami_indicator"] if tsunami_indicator else [],
            metadata={"magnitude":magnitude,"depth_km":depth,"felt":props.get("felt"),
                      "mmi":props.get("mmi"),"usgs_alert":props.get("alert"),
                      "tsunami_indicator":tsunami_indicator,"network_status":props.get("status")},
        ))
    return events

def parse_nhc(payload: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    events = []
    for storm in payload.get("activeStorms") or []:
        if not isinstance(storm, dict): continue
        name = text_value(storm.get("name"), "Ciclón tropical activo")
        classification = text_value(storm.get("classification") or storm.get("type"), "Sistema tropical")
        identifier = text_value(storm.get("id") or storm.get("atcf"), name)
        lat = number(storm.get("latitude") or storm.get("lat"))
        lon = number(storm.get("longitude") or storm.get("lon") or storm.get("long"))
        wind = number(storm.get("windSpeed") or storm.get("maxWind"))
        lower = classification.lower()
        severity = "critical" if "major" in lower else "high" if "hurricane" in lower or "typhoon" in lower else "moderate" if "tropical storm" in lower else "low"
        movement = text_value(storm.get("movement"), "")
        parts = [classification]
        if wind is not None: parts.append(f"viento máximo publicado: {wind:g} mph")
        if movement: parts.append(movement)
        event_url = text_value(storm.get("publicAdvisory") or storm.get("forecastAdvisory"), "https://www.nhc.noaa.gov/")
        events.append(make_event(
            event_id=identifier, event_type="cyclone", title=f"{name} · {classification}",
            summary=" · ".join(parts), source_id="nhc", source_name="NOAA · National Hurricane Center",
            source_url="https://www.nhc.noaa.gov/CurrentStorms.json", event_url=event_url,
            observed_at=parse_datetime(storm.get("lastUpdate") or storm.get("updated")),
            lat=lat, lon=lon, severity=severity,
            region=text_value(storm.get("basin"), "Atlántico / Pacífico oriental"),
            metadata={"classification":classification,"wind_mph":wind,"pressure_mb":number(storm.get("pressure")),
                      "movement":movement,"storm_id":identifier},
        ))
    return events

def _iter_gdacs_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list): return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict): return []
    for key in ("features","events","data","eventlist","items"):
        value = payload.get(key)
        if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _iter_gdacs_items(value)
            if nested: return nested
    return [payload] if payload.get("type") == "Feature" else []

def _geometry_centroid(geometry: dict[str, Any]) -> tuple[float | None, float | None]:
    coords = geometry.get("coordinates")
    points: list[tuple[float,float]] = []
    def walk(node: Any) -> None:
        if isinstance(node, (list,tuple)):
            if len(node) >= 2 and isinstance(node[0],(int,float)) and isinstance(node[1],(int,float)):
                points.append((float(node[0]),float(node[1])))
            else:
                for child in node: walk(child)
    walk(coords)
    if not points: return None, None
    return sum(p[1] for p in points)/len(points), sum(p[0] for p in points)/len(points)

def _gdacs_type(props: dict[str, Any]) -> str:
    raw = text_value(props.get("eventtype") or props.get("eventType") or props.get("type") or props.get("eventtypeName")).lower()
    mapping = {"eq":"earthquake","earthquake":"earthquake","tc":"cyclone","tropical cyclone":"cyclone",
               "cyclone":"cyclone","fl":"flood","flood":"flood","vo":"volcano","volcano":"volcano",
               "wf":"wildfire","wildfire":"wildfire","forest fire":"wildfire","dr":"drought","drought":"drought",
               "ts":"tsunami","tsunami":"tsunami"}
    return mapping.get(raw,"other")

def parse_gdacs(payload: Any, now: datetime) -> list[dict[str, Any]]:
    events = []
    for item in _iter_gdacs_items(payload):
        props = item.get("properties") if isinstance(item.get("properties"),dict) else item
        geometry = item.get("geometry") if isinstance(item.get("geometry"),dict) else {}
        lat, lon = _geometry_centroid(geometry)
        if lat is None or lon is None:
            lat = number(props.get("latitude") or props.get("lat"))
            lon = number(props.get("longitude") or props.get("lon"))
        event_type = _gdacs_type(props)
        name = text_value(props.get("eventname") or props.get("eventName") or props.get("name") or props.get("title"),"Evento reportado")
        country = text_value(props.get("country") or props.get("countryname") or props.get("countryName"),"")
        alert = props.get("alertlevel") or props.get("alertLevel") or props.get("alert")
        identifier = text_value(props.get("eventid") or props.get("eventId") or props.get("id") or item.get("id"),name)
        event_time = parse_datetime(props.get("fromdate") or props.get("fromDate") or props.get("date") or props.get("toDate"))
        url = text_value(props.get("url") or props.get("link"),"https://www.gdacs.org/")
        summary = text_value(props.get("description") or props.get("episodealertscore") or props.get("alertlevel"),"Evento registrado por GDACS.")
        events.append(make_event(
            event_id=identifier,event_type=event_type,title=name,
            summary=f"{country} · {summary}" if country else summary,
            source_id="gdacs",source_name="GDACS · Global Disaster Awareness and Coordination System",
            source_url="https://www.gdacs.org/",event_url=url,observed_at=event_time,
            lat=lat,lon=lon,severity=severity_from_alertlevel(alert),region=country or name,
            metadata={"alert_level":text_value(alert),"event_type_code":text_value(props.get("eventtype") or props.get("eventType"))},
        ))
    return events

def _eonet_category(categories: list[dict[str,Any]]) -> str:
    names = " ".join(text_value(x.get("title") or x.get("id")) for x in categories if isinstance(x,dict)).lower()
    if "wildfire" in names or "fire" in names: return "wildfire"
    if "volcan" in names: return "volcano"
    if "flood" in names: return "flood"
    if "landslide" in names: return "landslide"
    if "drought" in names: return "drought"
    if "storm" in names or "cyclone" in names or "hurricane" in names: return "storm"
    if "dust" in names or "haze" in names: return "atmosphere"
    if "snow" in names or "ice" in names: return "cryosphere"
    return "other"

def parse_eonet(payload: dict[str,Any], now: datetime) -> list[dict[str,Any]]:
    events = []
    for item in payload.get("events",[]) or []:
        if not isinstance(item,dict): continue
        geometry = item.get("geometry") or []
        last = geometry[-1] if geometry and isinstance(geometry[-1],dict) else {}
        coords = last.get("coordinates") or []
        lon = number(coords[0]) if len(coords)>=2 else None
        lat = number(coords[1]) if len(coords)>=2 else None
        categories = item.get("categories") or []
        category_names = ", ".join(text_value(c.get("title")) for c in categories if isinstance(c,dict))
        title = text_value(item.get("title"),"Evento ambiental")
        description = text_value(item.get("description"),category_names or "Evento ambiental registrado por NASA EONET.")
        events.append(make_event(
            event_id=text_value(item.get("id"),title),event_type=_eonet_category(categories),
            title=title,summary=description,source_id="eonet",
            source_name="NASA · Earth Observatory Natural Event Tracker",
            source_url="https://eonet.gsfc.nasa.gov/",event_url=text_value(item.get("link"),"https://eonet.gsfc.nasa.gov/"),
            observed_at=parse_datetime(last.get("date")),lat=lat,lon=lon,severity="info",region=category_names,
            metadata={"categories":categories,"closed":item.get("closed")},
        ))
    return events

def _swpc_severity(product_id: str, message: str) -> str:
    match = re.search(r"\bNOAA Scale:\s*([GRS])\s*([1-5])",message,re.I)
    if match:
        level = int(match.group(2))
        return "high" if level>=4 else "moderate" if level>=2 else "low"
    if product_id.startswith(("R","S")): return "moderate"
    if product_id.startswith("K"): return "low"
    return "info"

def parse_swpc_alerts(payload: list[Any], now: datetime) -> list[dict[str,Any]]:
    events = []
    cutoff = now - timedelta(days=4)
    for item in payload or []:
        if not isinstance(item,dict): continue
        issued = parse_datetime(item.get("issue_datetime"))
        if issued and issued < cutoff: continue
        product_id = text_value(item.get("product_id"),"SWPC")
        message = text_value(item.get("message"),"Aviso de clima espacial.")
        first = next((line.strip() for line in message.splitlines() if line.strip()),"Aviso de clima espacial")
        events.append(make_event(
            event_id=f"{product_id}-{item.get('issue_datetime',first)}",event_type="space_weather",
            title=f"NOAA SWPC · {first[:130]}",summary=message[:700],source_id="swpc_alerts",
            source_name="NOAA · Space Weather Prediction Center",source_url="https://www.swpc.noaa.gov/",
            event_url="https://www.swpc.noaa.gov/products/alerts-watches-and-warnings",
            observed_at=issued,severity=_swpc_severity(product_id,message),
            region="Impacto tecnológico global; depende del fenómeno y su intensidad",
            relevance="global",relevance_label="Global",metadata={"product_id":product_id},
        ))
    return events

def parse_swpc_scales(payload: dict[str,Any], now: datetime) -> dict[str,Any]:
    current = payload.get("0") or {}
    forecast = [payload.get(k) for k in ("1","2","3") if payload.get(k)]
    def scale_block(value: dict[str,Any], key: str) -> dict[str,str]:
        block = value.get(key) or {}
        return {"scale":text_value(block.get("Scale"),"0"),"text":text_value(block.get("Text"),"none")}
    return {
        "observed_at":f"{text_value(current.get('DateStamp'))}T{text_value(current.get('TimeStamp'))}Z" if current.get("DateStamp") and current.get("TimeStamp") else None,
        "current":{"radio_blackout":scale_block(current,"R"),"solar_radiation":scale_block(current,"S"),"geomagnetic":scale_block(current,"G")},
        "forecast":[{"date":text_value(day.get("DateStamp")),
            "radio_blackout_probability_minor":(day.get("R") or {}).get("MinorProb"),
            "radio_blackout_probability_major":(day.get("R") or {}).get("MajorProb"),
            "solar_radiation_probability":(day.get("S") or {}).get("Prob"),
            "geomagnetic":scale_block(day,"G")} for day in forecast],
        "source_url":"https://services.swpc.noaa.gov/products/noaa-scales.json","stale":False,
    }

def parse_donki(payload: list[Any], now: datetime, endpoint: str) -> list[dict[str,Any]]:
    events = []
    for item in payload or []:
        if not isinstance(item,dict): continue
        kp = None
        speed = None
        if endpoint == "GST":
            kp_values = item.get("allKpIndex") or []
            kp = max((number(x.get("kpIndex")) or 0 for x in kp_values if isinstance(x,dict)),default=0)
            severity = "high" if kp>=7 else "moderate" if kp>=5 else "low"
            observed = parse_datetime(item.get("startTime"))
            title = f"Tormenta geomagnética · Kp máximo {kp:g}"
            summary = text_value(item.get("link"),"Evento de tormenta geomagnética registrado por NASA DONKI.")
            event_type = "space_weather"
            identifier = text_value(item.get("gstID") or item.get("activityID"),title)
        elif endpoint == "FLR":
            class_type = text_value(item.get("classType"),"Clase no indicada")
            first = class_type[:1].upper()
            severity = "high" if first=="X" else "moderate" if first=="M" else "low"
            observed = parse_datetime(item.get("beginTime"))
            title = f"Llamarada solar clase {class_type}"
            summary = f"Región activa: {text_value(item.get('activeRegionNum'),'no indicada')} · ubicación: {text_value(item.get('sourceLocation'),'no indicada')}"
            event_type = "solar_flare"
            identifier = text_value(item.get("flrID") or item.get("activityID"),title)
        else:
            observed = parse_datetime(item.get("startTime"))
            analyses = item.get("cmeAnalyses") or []
            if analyses and isinstance(analyses[0],dict): speed = number(analyses[0].get("speed"))
            severity = "moderate" if speed is not None and speed>=1000 else "low"
            title = "Eyección de masa coronal (CME)"
            summary = text_value(item.get("note"),"Evento CME registrado por NASA DONKI.")
            if speed is not None: summary += f" · velocidad analizada: {speed:g} km/s"
            event_type = "coronal_mass_ejection"
            identifier = text_value(item.get("activityID"),title)
        events.append(make_event(
            event_id=identifier,event_type=event_type,title=title,summary=summary,
            source_id=f"nasa_donki_{endpoint.lower()}",source_name="NASA · DONKI Space Weather Database",
            source_url="https://api.nasa.gov/",event_url=text_value(item.get("link"),"https://kauai.ccmc.gsfc.nasa.gov/DONKI/"),
            observed_at=observed,severity=severity,region="Espacio cercano a la Tierra",
            relevance="global",relevance_label="Global",
            metadata={"class_type":item.get("classType"),"kp_max":kp,"speed_km_s":speed},
        ))
    return events

def _xml_child_text(element: ET.Element, name: str) -> str:
    for child in element.iter():
        if child.tag.split("}")[-1].lower()==name.lower() and child.text:
            return child.text.strip()
    return ""

def parse_tsunami_atom(root: ET.Element, now: datetime, center: str) -> list[dict[str,Any]]:
    events = []
    cutoff = now - timedelta(days=7)
    for entry in root.iter():
        if entry.tag.split("}")[-1].lower()!="entry": continue
        title = _xml_child_text(entry,"title") or "Boletín de tsunami"
        summary = _xml_child_text(entry,"summary") or _xml_child_text(entry,"content")
        issued = parse_datetime(_xml_child_text(entry,"updated") or _xml_child_text(entry,"published"))
        if issued and issued < cutoff: continue
        lowered = f"{title} {summary}".lower()
        if "warning" in lowered: severity = "critical"
        elif "advisory" in lowered or "watch" in lowered: severity = "high"
        elif "threat" in lowered and "no tsunami threat" not in lowered: severity = "moderate"
        else: severity = "info"
        link = ""
        for child in entry:
            if child.tag.split("}")[-1].lower()=="link":
                link = child.attrib.get("href","")
                if link: break
        regional_terms = ("costa rica","panama","central america","caribbean","pacific")
        relevance,label = ("regional","Pacífico / Caribe") if any(term in lowered for term in regional_terms) else ("global","Global")
        events.append(make_event(
            event_id=_xml_child_text(entry,"id") or f"{center}-{issued or title}",event_type="tsunami",
            title=f"{center} · {title}",summary=re.sub(r"\s+"," ",summary)[:700] or "Boletín oficial de un centro de alerta de tsunamis.",
            source_id=f"tsunami_{center.lower()}",source_name=f"NOAA · {center}",
            source_url="https://www.tsunami.gov/?page=productRetrieval",
            event_url=link or "https://www.tsunami.gov/",observed_at=issued,severity=severity,
            region=label,relevance=relevance,relevance_label=label,tags=["official_bulletin"],
            metadata={"center":center,"is_official_warning_center_bulletin":True},
        ))
    return events

def fetch_url(url: str) -> str:
    request = urllib.request.Request(url,headers={
        "User-Agent":USER_AGENT,
        "Accept":"application/json, application/geo+json, application/atom+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(request,timeout=TIMEOUT_SECONDS) as response:
        content = response.read(MAX_RESPONSE_BYTES+1)
        if len(content)>MAX_RESPONSE_BYTES: raise ValueError("La respuesta excede el tamaño máximo permitido")
        charset = response.headers.get_content_charset() or "utf-8"
        return content.decode(charset,errors="replace")

def source_specs(now: datetime) -> list[dict[str,Any]]:
    today = now.date()
    nasa_key = os.environ.get("NASA_API_KEY","").strip() or "DEMO_KEY"
    donki_params = urllib.parse.urlencode({"startDate":(today-timedelta(days=7)).isoformat(),"endDate":today.isoformat(),"api_key":nasa_key})
    cr_params = urllib.parse.urlencode({
        "format":"geojson","starttime":(now-timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S"),
        "minlatitude":"7.0","maxlatitude":"12.0","minlongitude":"-87.0","maxlongitude":"-82.0",
        "minmagnitude":"1.5","orderby":"time","limit":"250",
    })
    return [
        {"id":"usgs_global","name":"USGS · Sismos M2.5+ mundiales (24 h)","urls":["https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"],"parser":lambda p:parse_usgs(p,now,"usgs_global"),"kind":"json","max_stale":90},
        {"id":"usgs_costarica","name":"USGS · Sismicidad regional (7 días)","urls":[f"https://earthquake.usgs.gov/fdsnws/event/1/query?{cr_params}"],"parser":lambda p:parse_usgs(p,now,"usgs_costarica"),"kind":"json","max_stale":90},
        {"id":"nhc","name":"NOAA NHC · Ciclones activos","urls":["https://www.nhc.noaa.gov/CurrentStorms.json"],"parser":lambda p:parse_nhc(p,now),"kind":"json","max_stale":360},
        {"id":"gdacs","name":"GDACS · Desastres globales","urls":["https://www.gdacs.org/gdacsapi/api/Events/geteventlist/EVENTS4APP","https://www.gdacs.org/contentdata/xml/gdacs_app_feed.json"],"parser":lambda p:parse_gdacs(p,now),"kind":"json","max_stale":180},
        {"id":"eonet","name":"NASA EONET · Eventos ambientales","urls":["https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=100"],"parser":lambda p:parse_eonet(p,now),"kind":"json","max_stale":360},
        {"id":"swpc_alerts","name":"NOAA SWPC · Alertas espaciales","urls":["https://services.swpc.noaa.gov/products/alerts.json"],"parser":lambda p:parse_swpc_alerts(p,now),"kind":"json","max_stale":180},
        {"id":"swpc_scales","name":"NOAA SWPC · Escalas y pronóstico espacial","urls":["https://services.swpc.noaa.gov/products/noaa-scales.json"],"parser":lambda p:([],{"space_weather":parse_swpc_scales(p,now)}),"kind":"json","max_stale":180},
        {"id":"nasa_donki_cme","name":"NASA DONKI · Eyecciones de masa coronal","urls":[f"https://api.nasa.gov/DONKI/CME?{donki_params}"],"parser":lambda p:parse_donki(p,now,"CME"),"kind":"json","max_stale":720},
        {"id":"nasa_donki_gst","name":"NASA DONKI · Tormentas geomagnéticas","urls":[f"https://api.nasa.gov/DONKI/GST?{donki_params}"],"parser":lambda p:parse_donki(p,now,"GST"),"kind":"json","max_stale":720},
        {"id":"nasa_donki_flr","name":"NASA DONKI · Llamaradas solares","urls":[f"https://api.nasa.gov/DONKI/FLR?{donki_params}"],"parser":lambda p:parse_donki(p,now,"FLR"),"kind":"json","max_stale":720},
        {"id":"tsunami_ptwc","name":"NOAA PTWC · Boletines del Pacífico","urls":["https://www.tsunami.gov/events/xml/PHEBAtom.xml"],"parser":lambda p:parse_tsunami_atom(p,now,"PTWC"),"kind":"xml","max_stale":240},
        {"id":"tsunami_ntwc","name":"NOAA NTWC · Boletines nacionales","urls":["https://www.tsunami.gov/events/xml/PAAQAtom.xml"],"parser":lambda p:parse_tsunami_atom(p,now,"NTWC"),"kind":"xml","max_stale":240},
    ]

def _load_previous() -> dict[str,Any]:
    try: return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError): return {}

def collect_hazards(previous: dict[str,Any] | None = None, now: datetime | None = None,
                    fetcher: Callable[[str],str] = fetch_url,
                    specs: list[dict[str,Any]] | None = None) -> dict[str,Any]:
    now = now or utc_now()
    previous = previous or {}
    old_events = previous.get("events") or []
    old_sources = {x.get("id"):x for x in (previous.get("sources") or []) if isinstance(x,dict)}
    collected: list[dict[str,Any]] = []
    statuses: list[dict[str,Any]] = []
    space_weather = None
    for spec in (specs if specs is not None else source_specs(now)):
        source_id = spec["id"]
        fetched, last_error = False, ""
        parsed_events: list[dict[str,Any]] = []
        extra: dict[str,Any] = {}
        successful_url = spec["urls"][0]
        for url in spec["urls"]:
            try:
                raw = fetcher(url)
                payload = ET.fromstring(raw) if spec["kind"]=="xml" else json.loads(raw)
                result = spec["parser"](payload)
                if isinstance(result,tuple): parsed_events,extra = result
                else: parsed_events = result
                successful_url, fetched = url, True
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"[:240]
        old_status = old_sources.get(source_id) or {}
        if fetched:
            collected.extend(parsed_events)
            if "space_weather" in extra: space_weather = extra["space_weather"]
            statuses.append({"id":source_id,"name":spec["name"],"status":"online","checked_at":iso(now),
                "last_success_at":iso(now),"event_count":len(parsed_events),"url":successful_url,
                "message":"Consulta correcta" if parsed_events else "Consulta correcta; la fuente no reporta eventos en esta ventana.","error":None})
        else:
            last_success = parse_datetime(old_status.get("last_success_at"))
            age_minutes = (now-last_success).total_seconds()/60 if last_success else None
            max_stale = int(spec.get("max_stale",180))
            retained = [dict(e) for e in old_events if isinstance(e,dict) and e.get("source_id")==source_id
                        and age_minutes is not None and age_minutes<=max_stale]
            for event in retained:
                event["stale"] = True
                event["stale_age_minutes"] = round(age_minutes or 0)
                collected.append(event)
            statuses.append({"id":source_id,"name":spec["name"],"status":"stale" if retained else "unavailable",
                "checked_at":iso(now),"last_success_at":old_status.get("last_success_at"),
                "event_count":len(retained),"url":old_status.get("url") or spec["urls"][0],
                "message":"Se conserva temporalmente el último dato válido; no es una lectura actual." if retained else "No se pudo consultar esta fuente; no se interpreta como ausencia de peligro.",
                "error":last_error or "Fuente no disponible"})
            if source_id=="swpc_scales" and previous.get("space_weather"):
                space_weather = dict(previous["space_weather"])
                space_weather["stale"] = True

    deduped: dict[str,dict[str,Any]] = {}
    for event in collected:
        key = event.get("id") or f"{event.get('source_id')}:{event.get('title')}"
        existing = deduped.get(key)
        if existing is None or (existing.get("stale") and not event.get("stale")):
            deduped[key] = event
    events = list(deduped.values())
    events.sort(key=lambda e:(e.get("relevance")=="costa_rica",e.get("relevance")=="regional",
        severity_rank(e.get("severity","info")),parse_datetime(e.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc)),reverse=True)
    counts: dict[str,int] = {}
    for event in events:
        kind = event.get("type","other")
        counts[kind] = counts.get(kind,0)+1
    online = sum(1 for x in statuses if x["status"]=="online")
    failed = len(statuses)-online
    overall = "ok" if failed==0 else "partial" if online else "unavailable"
    return {
        "schema_version":SCHEMA_VERSION,"collector_version":COLLECTOR_VERSION,"generated_at":iso(now),"status":overall,
        "summary":{"total_events":len(events),"costa_rica_or_regional":sum(1 for e in events if e.get("relevance") in {"costa_rica","regional"}),
            "critical":sum(1 for e in events if e.get("severity")=="critical"),
            "high":sum(1 for e in events if e.get("severity")=="high"),
            "by_type":counts,"sources_online":online,"sources_with_problems":failed},
        "events":events,"sources":statuses,"space_weather":space_weather,"institutional_sources":SOURCE_REGISTRY,
        "coverage_notes":[
            "El registro mundial es una selección de fuentes públicas; no representa cobertura total de todos los fenómenos del planeta.",
            "Un feed sin eventos no significa que no exista peligro. Las fuentes no disponibles se muestran como tales y nunca se convierten en una alerta verde.",
            "Los boletines PTWC/NTWC no sustituyen las decisiones de SINAMOT ni de las autoridades costarricenses.",
            "Los sismos no pueden predecirse con precisión. La magnitud de un evento no determina por sí sola el impacto local.",
            "La actividad volcánica de OVSICORI se enlaza como fuente oficial y se complementa con el monitor visual existente; no se infiere un nivel instrumental desde imágenes de cámaras.",
            "La actividad solar y geomagnética se presenta como vigilancia espacial y tecnológica; no implica automáticamente peligro directo para las personas en superficie.",
            "Los avisos oficiales del IMN y la CNE prevalecen sobre cualquier clasificación interna de RainTrack."
        ]
    }

def write_snapshot(payload: dict[str,Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True,exist_ok=True)
    fd,temp_name = tempfile.mkstemp(prefix="hazards-",suffix=".json",dir=str(OUTPUT_PATH.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as handle:
            json.dump(payload,handle,ensure_ascii=False,indent=2)
            handle.write("\n")
        os.replace(temp_name,OUTPUT_PATH)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)

def main() -> int:
    payload = collect_hazards(previous=_load_previous())
    write_snapshot(payload)
    summary = payload["summary"]
    print(f"RainTrack hazards: status={payload['status']} events={summary['total_events']} "
          f"CR/regional={summary['costa_rica_or_regional']} sources_ok={summary['sources_online']} "
          f"sources_problem={summary['sources_with_problems']}")
    for source in payload["sources"]:
        print(f"- {source['id']}: {source['status']} ({source['event_count']} events)")
    return 0 if payload["status"]!="unavailable" else 1

if __name__ == "__main__":
    sys.exit(main())
