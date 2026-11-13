# RainTrack CR — Global Intelligence Architecture

## Product decision
- Geographic scope: global.
- Priority region: Costa Rica and Central America, without excluding events elsewhere.
- Alert policy: ingest and display all supported events; severity filters control presentation, not ingestion.
- The platform is an information and situational-awareness tool, not an official warning authority or an earthquake prediction system.

## Architecture
1. **Source adapters** fetch public feeds and APIs independently.
2. **Normalization layer** converts provider records into the common event contract in `schemas/hazard-event.schema.json`.
3. **Deduplication and correlation** link likely reports of the same physical event while retaining each source observation.
4. **Validation and confidence** preserve provider, timestamp, freshness, uncertainty, and verification state.
5. **Risk and relevance** calculate transparent display priority from severity, proximity, exposure, and source confidence. Never reinterpret a provider's alert as a confirmed impact.
6. **Storage/API** serves normalized events to the existing web client.
7. **Map, timeline, and alert center** show all events with filters and source attribution.

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
`discovered → normalized → validated → correlated → assessed → published → updated/resolved`

Events are not deleted when resolved; their lifecycle status and timestamps are updated. Failed or stale feeds must show their last successful update and must never be represented as "no hazard".

## Confidence and alert semantics
- `official`: issued by the responsible authority.
- `provider_reported`: published by a recognized data provider.
- `automated_detection`: machine-derived signal requiring corroboration.
- `model_estimate`: forecast or inferred scenario.
- `unverified`: source or interpretation needs review.

Alert severity and confidence are independent. A severe but uncertain signal must be visible as uncertain, not silently upgraded to confirmed.

## Reliability and safety
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
3. Official weather and cyclone feeds, then space-weather and wildfire products.
4. Costa Rica regional integrations: IMN, RSN, OVSICORI and CNE public bulletins.
5. Correlation, geospatial relevance, notifications and historical analytics.
6. UI integration: global event map, timeline, filters, event detail and source health.

## Non-goals for the first increment
This foundation does not yet provide continuous worldwide sensor coverage, predictive earthquake warnings, tsunami prediction, or guaranteed instant notifications. Coverage depends on public data availability, licensing, latency and provider uptime.
