# RainTrack CR — Global Intelligence Architecture

## Repository layout
- `index.html`, `assets/styles.css`, `assets/app.js` — static web client.
- `scripts/ingest_global_events.py` + `config/global-sources.json` — global hazard ingestion (all enabled sources are polled on every run, every 10 minutes).
- `scripts/monitor_cameras.py` + `config/camera-sources.json` — camera and IMN station monitor.
- `schemas/hazard-event.schema.json` — event contract, checked against the published data by `tests/`.
- `global-events.json`, `camera-alerts.json`, `camera-catalog.json` — generated data, committed by the scheduled workflows.

## Implementation status (13 November 2026)
- Operational ingestion: USGS global earthquakes, GDACS, NASA EONET, NOAA NHC Atlantic/Eastern Pacific RSS, and NOAA SWPC alerts.
- Scheduled publication: GitHub Actions polls the enabled public feeds and publishes the normalized `global-events.json` dataset.
- Client: a separate world map plots events with coordinates, while the Costa Rica weather map remains locally focused; hazard and regional filters drive the global event list and map.
- Event cards expose provider, observation time, confidence class, and active/resolved state. Stale records from unavailable sources are explicitly marked.
- Automated ingestion tests and Python compilation checks pass. Source coverage remains dependent on each provider's public feed and latency.


## Product decision
- Geographic scope: global.
- Priority region: Costa Rica and Central America, without excluding events elsewhere.
- Alert policy: ingest and display all supported events; severity filters control presentation, not ingestion.
- The platform is an information and situational-awareness tool, not an official warning authority or an earthquake prediction system.

## Architecture
1. **Source adapters** fetch public feeds and APIs independently.
2. **Normalization layer** converts provider records into the common event contract in `schemas/hazard-event.schema.json`.
3. **Deduplication and correlation** link likely reports of the same physical event while retaining each source observation. Cross-provider physical-event correlation remains a planned enhancement; current ingestion deduplicates stable provider IDs. `correlation_group_id`, `confidence_score` and `geometry` are reserved in the contract and are currently always `null`.
4. **Validation and confidence** preserve provider, timestamp, freshness, uncertainty, and verification state.
5. **Risk and relevance** (planned) calculate transparent display priority from severity, proximity, exposure, and source confidence. Never reinterpret a provider's alert as a confirmed impact.
6. **Storage/API** currently publishes a static normalized JSON dataset for the web client; a queryable event API is a later scaling step.
7. **Map, timeline, and alert center** currently include a global point map, event list, filters, source attribution and source-health indicators. Push notifications and a full historical timeline remain planned.

## Domain modules
- Atmosphere: weather, tropical waves, cyclones, severe storms, fronts, atmospheric rivers, ENSO and other climate patterns.
- Solid Earth: earthquakes, aftershocks, volcanoes, landslides and ground deformation where public data exists.
- Hydrology/ocean: floods, river gauges, drought, tsunami bulletins, tides, waves and storm surge.
- Environment: wildfire, smoke, air quality, heat, cold and other environmental hazards.
- Space: solar flares, geomagnetic storms, solar wind and near-Earth objects.
- Cameras and remote sensing: camera scene analysis, satellite products and radar. Camera evidence is corroborative, not a substitute for instrument data.

## Initial source adapters
| Domain | Initial provider/feed | Notes |
|---|---|---|
| Earthquakes | USGS GeoJSON feeds | Global event catalog; magnitude and depth are provider-reported. |
| Earthquakes (regional) | RSN / OVSICORI | Integrate official regional bulletins when stable machine-readable endpoints are confirmed. |
| Multi-hazard | GDACS | Global disaster event feed; retain GDACS severity and source links. |
| Environment | NASA EONET v3 | Curated event catalog; not a real-time sensor network. |
| Weather/cyclones | NOAA/NHC, WMO and national meteorological services | Use official bulletins and track products; regional agencies remain authoritative. |
| Costa Rica weather | IMN | Preserve current RainTrack radar, weather and camera systems. |
| Volcanoes | OVSICORI, Smithsonian GVP and official observatories | Distinguish observation from forecast or advisory. |
| Space weather | NOAA SWPC and NASA | Separate observed conditions from forecast watches. |

## Event lifecycle
Implemented today: `discovered → normalized → published`. Each run rebuilds the dataset from what the enabled feeds return at that moment, so the published file is a **current snapshot, not a historical archive** (for example, USGS only exposes a rolling 24-hour window). Providers may mark an event as `resolved` or `expired` and that state is preserved while the provider still lists it.

If a feed fails, its records from the previous run are kept for up to 24 hours (`CARRY_FORWARD_MAX_AGE`) and marked `data_freshness = carried_forward_source_unavailable`; after that they are dropped. A failed feed must never be represented as "no hazard".

Planned (not implemented): `validated → correlated → assessed` stages and a persistent event history.

## Confidence and alert semantics
- `official`: issued by the responsible authority.
- `provider_reported`: published by a recognized data provider.
- `automated_detection`: machine-derived signal requiring corroboration.
- `model_estimate`: forecast or inferred scenario.
- `unverified`: source or interpretation needs review.

Alert severity and confidence are independent. A severe but uncertain signal must be visible as uncertain, not silently upgraded to confirmed.

## Reliability and safety
Implemented: UTC timestamps, per-source timeout, source isolation (one failing feed does not stop the others), per-source health, bounded carry-forward of data from failed feeds, and schema validation of the published events in the test suite.

Planned (not implemented): retry/backoff, rate limits, circuit breakers, per-source polling intervals, and persistent history.

Design principles:
- Store UTC timestamps and original provider timestamps.
- Record source URL, provider, fetch time, update time, and raw provider identifier.
- Apply per-source timeouts, retry/backoff, rate limits and circuit breakers.
- Keep source adapters isolated; one outage must not stop other domains.
- Deduplicate without discarding source observations.
- Do not claim prediction of earthquakes. Display detected earthquakes after provider publication.
- No alert may be called an official evacuation instruction unless it links to an official authority bulletin.
- All alerts are informational; users should follow local emergency-management authorities.

## Delivery phases
1. Foundation: event contract, source registry, ingestion runner and validation tests.
2. Live global feeds: USGS earthquakes, GDACS and NASA EONET; status/health for each feed.
3. Official cyclone and space-weather feeds are now connected for the Atlantic, Eastern Pacific and NOAA SWPC. Additional OVSICORI volcano-state and camera metadata, CNE advisories, and other impact products remain to be integrated.
4. Costa Rica regional integrations: IMN, RSN, OVSICORI and CNE public bulletins.
5. Correlation, geospatial relevance, notifications and historical analytics.
6. UI integration: global event map, filters, event cards and source health are implemented; richer event detail and timeline are next.

## Non-goals for the first increment
This foundation does not yet provide continuous worldwide sensor coverage, predictive earthquake warnings, tsunami prediction, or guaranteed instant notifications. Coverage depends on public data availability, licensing, latency and provider uptime.
