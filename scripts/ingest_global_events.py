#!/usr/bin/env python3
"""Fetch and normalize first-wave global hazard feeds for RainTrack CR.

This is a feed aggregator, not a hazard predictor. Provider timestamps and
confidence are preserved; a failed feed is recorded as stale/unavailable.
"""
from __future__ import annotations

import json
import logging
import re
import time
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "global-sources.json"
OUTPUT = ROOT / "global-events.json"
TIMEOUT = 20
USER_AGENT = "RainTrackCR-GlobalMonitor/1.0 (+https://github.com/Allan101010/raintrack-cr)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json, application/rss+xml, application/xml, text/xml"})
LOG = logging.getLogger("raintrack.global")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_from_epoch(value) -> str:
    try:
        return datetime.fromtimestamp(float(value) / (1000 if float(value) > 10**11 else 1), timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return now_iso()


def stable_id(provider: str, raw_id: str) -> str:
    return hashlib.sha256((provider + ":" + raw_id).encode()).hexdigest()[:24]


def event_record(*, provider, raw_id, hazard_type, title, url, observed_at,
                 ingested_at, confidence, status="active", severity=None,
                 description=None, location=None, metrics=None, issued_at=None):
    return {
        "event_id": stable_id(provider, str(raw_id)),
        "provider_event_id": str(raw_id),
        "hazard_type": hazard_type,
        "title": title or "Evento sin título",
        "description": description,
        "status": status,
        "severity": severity,
        "confidence_class": confidence,
        "confidence_score": None,
        "location": location,
        "geometry": None,
        "metrics": metrics or {},
        "source": {"provider": provider, "url": url, "license": None, "raw_id": str(raw_id)},
        "observed_at": observed_at,
        "issued_at": issued_at,
        "ingested_at": ingested_at,
        "updated_at": None,
        "expires_at": None,
        "region_priority": ("costa_rica_central_america" if location and 5.0 <= location.get("latitude", 999) <= 18.5 and -94.0 <= location.get("longitude", 999) <= -77.0 else "global"),
        "correlation_group_id": None,
        "official_advisory_url": url if url.startswith("https://") else None,
    }


def fetch_json(url):
    response = SESSION.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_text(url):
    response = SESSION.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.content


def parse_usgs(source, fetched_at):
    payload = fetch_json(source["url"])
    output = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            location = None
        else:
            location = {"longitude": float(coords[0]), "latitude": float(coords[1]),
                        "depth_km": float(coords[2]) if len(coords) > 2 and coords[2] is not None else None,
                        "place_name": props.get("place"), "country_code": None}
        mag = props.get("mag")
        severity = "extreme" if mag is not None and mag >= 7 else "severe" if mag is not None and mag >= 6 else "moderate" if mag is not None and mag >= 4.5 else "minor" if mag is not None else "unknown"
        raw_id = feature.get("id") or props.get("code") or props.get("ids") or str(props.get("time"))
        output.append(event_record(
            provider=source["provider"], raw_id=raw_id, hazard_type="earthquake",
            title=props.get("title") or props.get("place") or "Sismo reportado",
            description=props.get("status") and ("Estado del catálogo USGS: " + str(props["status"])) or None,
            url=props.get("url") or source["url"], observed_at=iso_from_epoch(props.get("time")),
            issued_at=iso_from_epoch(props.get("updated")) if props.get("updated") else None,
            ingested_at=fetched_at, confidence="provider_reported", severity=severity,
            location=location, metrics={"magnitude": mag, "magnitude_type": props.get("magType"),
                                        "felt_reports": props.get("felt"), "tsunami_flag": props.get("tsunami"),
                                        "sig": props.get("sig"), "depth_km": location.get("depth_km") if location else None}))
    return output


def parse_eonet(source, fetched_at):
    payload = fetch_json(source["url"])
    output = []
    for item in payload.get("events", []):
        geometries = item.get("geometry") or []
        latest = geometries[-1] if geometries else {}
        coords = latest.get("coordinates")
        location = None
        if isinstance(coords, list) and len(coords) >= 2 and isinstance(coords[0], (int, float)):
            location = {"longitude": float(coords[0]), "latitude": float(coords[1]),
                        "depth_km": None, "place_name": None, "country_code": None}
        cats = [c.get("title", "") for c in item.get("categories", [])]
        category_text = " ".join(cats).lower()
        hazard = ("wildfire" if any(w in category_text for w in ("wildfire", "fire")) else "severe_storm" if any(w in category_text for w in ("storm", "severe weather")) else "volcano" if "volcano" in category_text else "flood" if "flood" in category_text else "drought" if "drought" in category_text else "other")
        output.append(event_record(
            provider=source["provider"], raw_id=item.get("id"), hazard_type=hazard,
            title=item.get("title"), description=item.get("description"),
            url=item.get("link") or source["url"], observed_at=latest.get("date") or fetched_at,
            ingested_at=fetched_at, confidence="provider_reported",
            status="resolved" if item.get("closed") else "active", location=location,
            metrics={"categories": ", ".join(cats), "geometry_type": latest.get("type") or "unknown"}))
    return output


def parse_swpc_alerts(source, fetched_at):
    payload = fetch_json(source["url"])
    output = []
    items = payload if isinstance(payload, list) else payload.get("alerts", [])
    for item in items:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or item.get("summary") or item.get("product_id") or "Aviso de clima espacial")
        product_id = str(item.get("product_id") or item.get("id") or message[:120])
        lower = message.lower()
        hazard = "geomagnetic_storm" if any(x in lower for x in ("geomagnetic storm", "geomagnetic", "g-scale")) else "solar_flare" if any(x in lower for x in ("solar flare", "radio blackout", "x-ray", "type ii radio emission", "type iv radio emission", "solar radiation storm", "proton event")) else "space_weather"
        severity = "unknown"
        match = re.search(r"\bG([1-5])\b", message, re.I)
        if match:
            level = int(match.group(1))
            severity = "minor" if level == 1 else "moderate" if level == 2 else "severe" if level in (3, 4) else "extreme"
        else:
            kp_match = re.search(r"K-index of ([0-9])", message, re.I)
            if kp_match:
                kp = int(kp_match.group(1))
                severity = "minor" if kp == 5 else "moderate" if kp == 6 else "severe" if kp in (7, 8) else "extreme" if kp >= 9 else "unknown"
        observed_raw = item.get("issue_datetime") or item.get("issue_time") or item.get("message_issue_time") or fetched_at
        observed = observed_raw
        # Normalize ISO-like provider timestamps that may omit their timezone.
        try:
            parsed_observed = datetime.fromisoformat(str(observed_raw).replace("Z", "+00:00"))
            if parsed_observed.tzinfo is None:
                parsed_observed = parsed_observed.replace(tzinfo=timezone.utc)
            observed = parsed_observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
        # NOAA messages also use timestamps such as "2026 Nov 05 1857 UTC".
        if observed == observed_raw:
            for date_format in ("%Y %b %d %H%M UTC", "%Y %b %d %H:%M:%S.%f", "%Y %b %d %H:%M:%S"):
                try:
                    observed = datetime.strptime(str(observed_raw), date_format).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                    break
                except ValueError:
                    continue
        age_hours = None
        try:
            observed_dt = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            if observed_dt.tzinfo is None:
                observed_dt = observed_dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.fromisoformat(fetched_at.replace("Z", "+00:00")) - observed_dt).total_seconds() / 3600
        except (TypeError, ValueError):
            pass
        event_status = "resolved" if age_hours is not None and age_hours > 24 else "active"
        title = product_id + " - " + next((line.strip() for line in message.splitlines() if line.strip().startswith(("ALERT:", "WATCH:", "WARNING:"))), message.splitlines()[0])
        output.append(event_record(provider=source["provider"], raw_id=product_id, hazard_type=hazard, title=title[:220], description=message, url=item.get("link") or source["url"], observed_at=observed, issued_at=observed, ingested_at=fetched_at, confidence="official", status=event_status, severity=severity, metrics={"product_id": product_id, "message_type": item.get("message_type"), "age_hours": round(age_hours, 1) if age_hours is not None else None}))
    return output

def repair_mojibake(value):
    """Repair common UTF-8 text decoded as Latin-1 by an upstream feed."""
    if not isinstance(value, str) or not any(marker in value for marker in ("Ã", "Â", "â€")):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
        old_markers = sum(value.count(marker) for marker in ("Ã", "Â", "â€"))
        new_markers = sum(repaired.count(marker) for marker in ("Ã", "Â", "â€"))
        return repaired if new_markers < old_markers else value
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def parse_gdacs_rss(source, fetched_at):
    root = ET.fromstring(fetch_text(source["url"]))
    output = []
    for item in root.findall(".//item"):
        title = repair_mojibake(item.findtext("title") or "GDACS alert")
        link = item.findtext("link") or source["url"]
        guid = item.findtext("guid") or link or title
        description = repair_mojibake(item.findtext("description"))
        # GeoRSS commonly supplies point as "latitude longitude".
        point = None
        for node in item.iter():
            if node.tag.lower().endswith("point") and node.text:
                point = node.text.strip()
                break
        location = None
        if point:
            nums = re.split(r"[ ,]+", point)
            try:
                if len(nums) >= 2:
                    location = {"latitude": float(nums[0]), "longitude": float(nums[1]),
                                "depth_km": None, "place_name": None, "country_code": None}
            except ValueError:
                pass
        lower = title.lower()
        hazard = "tropical_cyclone" if any(word in lower for word in ("cyclone", "hurricane", "typhoon")) else "earthquake" if "earthquake" in lower else "flood" if "flood" in lower else "wildfire" if any(word in lower for word in ("wildfire", "fire")) else "other"
        # Do not infer severity from title wording. Preserve uncertainty unless
        # a structured provider field is parsed and mapped explicitly.
        published = item.findtext("pubDate") or item.findtext("date")
        try:
            from email.utils import parsedate_to_datetime
            observed_at = parsedate_to_datetime(published).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if published else fetched_at
        except (TypeError, ValueError, OverflowError):
            observed_at = fetched_at
        output.append(event_record(provider=source["provider"], raw_id=guid, hazard_type=hazard,
            title=title, description=description, url=link, observed_at=observed_at,
            ingested_at=fetched_at, confidence="provider_reported", severity="unknown",
            location=location, metrics={"feed_type": source["kind"]}))
    return output


PARSERS = {"geojson": parse_usgs, "json": parse_eonet, "rss": parse_gdacs_rss, "swpc_json": parse_swpc_alerts}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    fetched_at = now_iso()
    events, health = {}, []
    for source in config.get("sources", []):
        if not source.get("enabled"):
            continue
        started = time.monotonic()
        row = {"source_id": source["id"], "provider": source["provider"], "url": source["url"],
               "status": "unknown", "checked_at": fetched_at, "event_count": 0, "error": None}
        try:
            parser = PARSERS[source["kind"]]
            records = parser(source, fetched_at)
            for record in records:
                events[record["event_id"]] = record
            row.update(status="ok", event_count=len(records))
        except Exception as exc:
            row.update(status="error", error=str(exc)[:500])
            LOG.exception("Source failed: %s", source["id"])
        row["duration_seconds"] = round(time.monotonic() - started, 2)
        health.append(row)

    previous = {}
    if OUTPUT.exists():
        try:
            previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    # Retain prior records from failed feeds, but mark them as carried-forward;
    # never interpret an outage as an empty hazard situation.
    successful_ids = {row["source_id"] for row in health if row["status"] == "ok"}
    for old in previous.get("events", []):
        source_name = old.get("source", {}).get("provider")
        if old.get("event_id") not in events and source_name and any(
            row["status"] != "ok" and row["provider"] == source_name for row in health
        ):
            old["data_freshness"] = "carried_forward_source_unavailable"
            events[old["event_id"]] = old

    payload = {"schema_version": 1, "generated_at": fetched_at,
               "scope": "global", "priority_region": "Costa Rica and Central America",
               "source_health": health, "events": sorted(events.values(), key=lambda e: e["observed_at"], reverse=True)}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG.info("Published %s events from %s feeds", len(events), len(health))
    # A partial outage should be visible in source_health but not discard good data.
    return 0 if any(row["status"] == "ok" for row in health) else 1


if __name__ == "__main__":
    raise SystemExit(main())
