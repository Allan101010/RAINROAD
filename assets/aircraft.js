/* Aviones en vivo + aeropuertos (capa opcional, apagada por defecto).
   Fuente: redes abiertas de receptores ADS-B de voluntarios (airplanes.live; adsb.lol y adsb.fi de respaldo).
   Solo se piden aviones mientras la capa está encendida y la pestaña visible. Se envía al servicio el centro del
   mapa redondeado (2 decimales) y un radio; nada más, y no se guarda nada.
   La cobertura depende de receptores de voluntarios: puede haber huecos y retrasos. No sirve para navegar. */
(function () {
  "use strict";
  const PROVIDERS = [
    { name: "airplanes.live", url: (lat, lon, nm) => "https://api.airplanes.live/v2/point/" + lat + "/" + lon + "/" + nm },
    { name: "adsb.lol", url: (lat, lon, nm) => "https://api.adsb.lol/v2/point/" + lat + "/" + lon + "/" + nm },
    { name: "adsb.fi", url: (lat, lon, nm) => "https://opendata.adsb.fi/api/v2/lat/" + lat + "/lon/" + lon + "/dist/" + nm }
  ];
  const REFRESH_MS = 10000;
  const MAX_BACKOFF_MS = 60000;
  const MIN_ZOOM = 6;          // más lejos que esto el área es enorme: se pide acercar
  const MAX_PLANES = 150;
  const MAX_AGE_S = 60;        // un avión sin posición nueva en 60 s ya no se dibuja
  const KEEP_ON_ERROR_MS = 60000;

  // Coordenadas aproximadas de los aeropuertos principales.
  const AIRPORTS = [
    { icao: "MROC", iata: "SJO", name: "Aeropuerto Internacional Juan Santamaría", lat: 9.9939, lon: -84.2088, wiki: "Aeropuerto_Internacional_Juan_Santamaría" },
    { icao: "MRPV", iata: "SYQ", name: "Aeropuerto Nacional Tobías Bolaños", lat: 9.9571, lon: -84.1398, wiki: "Aeropuerto_Internacional_Tobías_Bolaños_Palma" },
    { icao: "MRLB", iata: "LIR", name: "Aeropuerto Internacional Daniel Oduber (Liberia)", lat: 10.5933, lon: -85.5444, wiki: "Aeropuerto_Internacional_Daniel_Oduber_Quirós" },
    { icao: "MRLM", iata: "LIO", name: "Aeropuerto Internacional de Limón", lat: 9.9567, lon: -83.0220, wiki: "Aeropuerto_Internacional_de_Limón" }
  ];

  const $q = id => document.getElementById(id);
  const esc = text => String(text == null ? "" : text).replace(/[&<>"']/g,
    ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

  let enabled = false;
  let planeMarkers = new Map();   // hex -> { marker, el, plane }
  let airportMarkers = [];
  let timer = null;
  let moveTimer = null;
  let inFlight = false;
  let failures = 0;
  let providerIndex = 0;
  let lastGoodAt = 0;
  let planesByHex = new Map();
  const photoCache = new Map();   // hex -> Promise<foto|null>
  const wikiCache = new Map();    // título -> Promise<{src, url}|null>

  // ---------- Funciones puras (con prueba en tests/aircraft.test.js) ----------
  function kmBetween(lat1, lon1, lat2, lon2) {
    const rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  // Radio en millas náuticas que cubre el área visible (esquina a esquina), entre 15 y 250 (máximo de las APIs).
  function radiusNm(south, west, north, east) {
    const clat = (south + north) / 2, clon = (west + east) / 2;
    const km = kmBetween(clat, clon, north, east);
    return Math.min(250, Math.max(15, Math.ceil(km / 1.852)));
  }

  function parsePlanes(payload) {
    const list = payload && (payload.ac || payload.aircraft);
    if (!Array.isArray(list)) return [];
    const out = [];
    list.forEach(item => {
      if (!item || !item.hex) return;
      const lat = Number(item.lat), lon = Number(item.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || item.lat == null || item.lon == null) return;
      const seen = item.seen_pos != null ? Number(item.seen_pos) : (item.seen != null ? Number(item.seen) : 0);
      if (Number.isFinite(seen) && seen > MAX_AGE_S) return;
      const onGround = item.alt_baro === "ground";
      const alt = onGround ? 0 : (Number.isFinite(Number(item.alt_baro)) ? Number(item.alt_baro) : (Number.isFinite(Number(item.alt_geom)) ? Number(item.alt_geom) : null));
      const track = Number.isFinite(Number(item.track)) && item.track != null ? Number(item.track) : null;
      out.push({
        hex: String(item.hex).replace(/^~/, "").toLowerCase(),
        call: String(item.flight || "").trim(),
        reg: String(item.r || "").trim(),
        type: String(item.t || "").trim(),
        desc: String(item.desc || "").trim(),
        lat, lon, onGround, altFt: alt,
        gsKt: Number.isFinite(Number(item.gs)) && item.gs != null ? Number(item.gs) : null,
        track,
        vrFpm: Number.isFinite(Number(item.baro_rate)) && item.baro_rate != null ? Number(item.baro_rate) : null,
        squawk: String(item.squawk || "").trim(),
        seen: Number.isFinite(seen) ? seen : 0
      });
    });
    return out;
  }

  const ftToM = ft => Math.round(ft * 0.3048);
  const ktToKmh = kt => Math.round(kt * 1.852);

  function squawkNote(code) {
    if (code === "7700") return "Emergencia general";
    if (code === "7600") return "Falla de radio";
    if (code === "7500") return "Interferencia ilícita";
    return "";
  }

  function altitudeColor(plane) {
    if (plane.onGround) return "#94a3b8";
    if (plane.altFt == null) return "#cbd5e1";
    if (plane.altFt < 10000) return "#fbbf24";
    if (plane.altFt < 25000) return "#38bdf8";
    return "#a78bfa";
  }

  // ---------- Fotos ----------
  // Foto del avión por código de transpondedor (Planespotters.net, pide mostrar autor y enlace).
  function planePhoto(hex) {
    if (!photoCache.has(hex)) {
      photoCache.set(hex, fetch("https://api.planespotters.net/pub/photos/hex/" + encodeURIComponent(hex), { cache: "force-cache" })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          const photo = data && Array.isArray(data.photos) && data.photos[0];
          if (!photo) return null;
          const thumb = photo.thumbnail_large || photo.thumbnail;
          if (!thumb || !/^https:\/\//.test(thumb.src || "")) return null;
          return { src: thumb.src, link: /^https:\/\//.test(photo.link || "") ? photo.link : "https://www.planespotters.net/", by: photo.photographer || "" };
        })
        .catch(() => null));
    }
    return photoCache.get(hex);
  }

  // Foto del aeropuerto: miniatura del artículo de Wikipedia (se pide solo al tocar).
  function airportPhoto(airport) {
    if (!wikiCache.has(airport.wiki)) {
      wikiCache.set(airport.wiki, fetch("https://es.wikipedia.org/api/rest_v1/page/summary/" + encodeURIComponent(airport.wiki), { cache: "force-cache" })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          const img = data && (data.thumbnail || data.originalimage);
          if (!img || !/^https:\/\//.test(img.source || "")) return null;
          const page = data.content_urls && data.content_urls.desktop && data.content_urls.desktop.page;
          return { src: img.source, link: /^https:\/\//.test(page || "") ? page : "https://es.wikipedia.org/wiki/" + encodeURIComponent(airport.wiki) };
        })
        .catch(() => null));
    }
    return wikiCache.get(airport.wiki);
  }

  // ---------- Dibujo ----------
  const PLANE_SVG = "<svg viewBox=\"0 0 24 24\" width=\"26\" height=\"26\" aria-hidden=\"true\"><path d=\"M12 1.5c.9 0 1.5.9 1.5 2v6.2l8 4.6v2.2l-8-2.3v4.6l2.2 1.7v1.9L12 20.6 8.3 22.4v-1.9l2.2-1.7v-4.6l-8 2.3v-2.2l8-4.6V3.5c0-1.1.6-2 1.5-2z\" fill=\"currentColor\" stroke=\"#0b1220\" stroke-width=\"1\" stroke-linejoin=\"round\"/></svg>";

  function planeLabel(plane) {
    return plane.call || plane.reg || plane.hex.toUpperCase();
  }

  function planeElement(plane) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "aircraft-marker";
    el.innerHTML = PLANE_SVG;
    el.style.color = altitudeColor(plane);
    el.setAttribute("aria-label", "Avión " + planeLabel(plane));
    return el;
  }

  function clearPlanes() {
    planeMarkers.forEach(item => item.marker.remove());
    planeMarkers.clear();
    planesByHex = new Map();
  }

  function clearAirports() {
    airportMarkers.forEach(marker => marker.remove());
    airportMarkers = [];
  }

  function drawAirports() {
    clearAirports();
    if (!enabled || !mapOk()) return;
    AIRPORTS.forEach(airport => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "airport-marker";
      el.textContent = "🛫";
      el.title = airport.name;
      el.setAttribute("aria-label", airport.name);
      el.addEventListener("click", event => { event.stopPropagation(); openAirport(airport, el); });
      airportMarkers.push(new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat([airport.lon, airport.lat]).addTo(map));
    });
  }

  function drawPlanes(planes) {
    const center = map.getCenter();
    const nearest = planes.slice().sort((a, b) =>
      kmBetween(center.lat, center.lng, a.lat, a.lon) - kmBetween(center.lat, center.lng, b.lat, b.lon)).slice(0, MAX_PLANES);
    const keep = new Set();
    nearest.forEach(plane => {
      keep.add(plane.hex);
      planesByHex.set(plane.hex, plane);
      const known = planeMarkers.get(plane.hex);
      if (known) {
        known.plane = plane;
        known.marker.setLngLat([plane.lon, plane.lat]);
        known.marker.setRotation(plane.track == null ? 0 : plane.track);
        known.el.style.color = altitudeColor(plane);
        return;
      }
      const el = planeElement(plane);
      const marker = new maplibregl.Marker({ element: el, anchor: "center", rotation: plane.track == null ? 0 : plane.track, rotationAlignment: "map" })
        .setLngLat([plane.lon, plane.lat]).addTo(map);
      const item = { marker, el, plane };
      el.addEventListener("click", event => { event.stopPropagation(); openPlane(item.plane, el); });
      planeMarkers.set(plane.hex, item);
    });
    Array.from(planeMarkers.keys()).forEach(hex => {
      if (keep.has(hex)) return;
      planeMarkers.get(hex).marker.remove();
      planeMarkers.delete(hex);
      planesByHex.delete(hex);
    });
  }

  // ---------- Ventana de detalle ----------
  function row(label, value) {
    return value ? "<div class=\"aircraft-row\"><span>" + esc(label) + "</span><strong>" + value + "</strong></div>" : "";
  }

  function photoHtml(id, loading) {
    return "<div class=\"aircraft-photo\" id=\"" + esc(id) + "\">" + (loading ? "<div class=\"aircraft-photo-empty\">Buscando foto…</div>" : "") + "</div>";
  }

  function fillPhoto(id, photo, creditHtml) {
    const box = $q(id);
    if (!box) return;   // ya se cerró o se abrió otro detalle
    if (!photo) { box.innerHTML = "<div class=\"aircraft-photo-empty\">Sin foto de referencia disponible</div>"; return; }
    box.innerHTML = "<img src=\"" + esc(photo.src) + "\" alt=\"Foto de referencia\" loading=\"lazy\" referrerpolicy=\"no-referrer\">" +
      "<div class=\"aircraft-photo-credit\">" + creditHtml(photo) + "</div>";
    const img = box.querySelector("img");
    if (img) img.addEventListener("error", () => fillPhoto(id, null, creditHtml));
  }

  function openPlane(plane, el) {
    if (typeof showMapDetail !== "function") return;
    const photoId = "acPhoto-" + plane.hex;
    const alt = plane.onGround ? "En tierra" : plane.altFt == null ? "" : ftToM(plane.altFt).toLocaleString("es-CR") + " m (" + Math.round(plane.altFt).toLocaleString("es-CR") + " ft)";
    const vr = plane.vrFpm == null || plane.onGround ? "" : (plane.vrFpm > 100 ? "▲ subiendo " : plane.vrFpm < -100 ? "▼ bajando " : "→ nivelado ") + Math.round(Math.abs(plane.vrFpm) * 0.3048 / 60 * 10) / 10 + " m/s";
    const note = squawkNote(plane.squawk);
    const content = "<div class=\"aircraft-detail\">" + photoHtml(photoId, true) +
      row("Altitud", esc(alt)) +
      row("Velocidad", plane.gsKt == null ? "" : ktToKmh(plane.gsKt) + " km/h") +
      row("Rumbo", plane.track == null ? "" : Math.round(plane.track) + "°") +
      row("Vertical", esc(vr)) +
      row("Matrícula", esc(plane.reg)) +
      row("Código ICAO", esc(plane.hex.toUpperCase())) +
      row("Transpondedor", esc(plane.squawk) + (note ? " · " + esc(note) : "")) +
      "<p class=\"aircraft-note\">Posición recibida hace " + Math.round(plane.seen) + " s por receptores de voluntarios. " +
      "La foto es de referencia (puede ser otro momento o configuración del mismo avión). No usar para navegación.</p></div>";
    showMapDetail({ eyebrow: "AVIÓN EN VIVO", title: planeLabel(plane), subtitle: [plane.type, plane.desc].filter(Boolean).join(" · "), content, markerElement: el });
    planePhoto(plane.hex).then(photo => fillPhoto(photoId, photo, p =>
      "Foto" + (p.by ? ": " + esc(p.by) : "") + " · <a href=\"" + esc(p.link) + "\" target=\"_blank\" rel=\"noopener\">Planespotters.net ↗</a>"));
  }

  function openAirport(airport, el) {
    if (typeof showMapDetail !== "function") return;
    const photoId = "acPhoto-" + airport.icao;
    const content = "<div class=\"aircraft-detail\">" + photoHtml(photoId, true) +
      row("Código", esc(airport.icao + " · " + airport.iata)) +
      "<p class=\"aircraft-note\">Ubicación aproximada. Foto de referencia de Wikipedia.</p></div>";
    showMapDetail({ eyebrow: "AEROPUERTO", title: airport.name, subtitle: airport.icao + " · " + airport.iata, content, markerElement: el });
    airportPhoto(airport).then(photo => fillPhoto(photoId, photo, p =>
      "Foto: <a href=\"" + esc(p.link) + "\" target=\"_blank\" rel=\"noopener\">Wikipedia ↗</a>"));
  }

  // ---------- Carga ----------
  function mapOk() {
    return typeof map !== "undefined" && map && typeof mapReady !== "undefined" && mapReady && typeof maplibregl !== "undefined";
  }

  function setInfo(text) {
    const box = $q("aircraftInfo");
    if (box) box.textContent = text;
  }

  function schedule(ms) {
    clearTimeout(timer);
    timer = null;
    if (enabled) timer = setTimeout(refresh, ms == null ? REFRESH_MS : ms);
  }

  async function fetchFrom(provider, lat, lon, nm) {
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const abort = controller ? setTimeout(() => controller.abort(), 12000) : null;
    try {
      const response = await fetch(provider.url(lat, lon, nm), { cache: "no-store", signal: controller ? controller.signal : undefined });
      if (!response.ok) throw new Error("HTTP " + response.status);
      return await response.json();
    } finally { if (abort) clearTimeout(abort); }
  }

  async function refresh() {
    if (!enabled || inFlight) return;
    if (document.hidden) { schedule(); return; }
    if (!mapOk()) { schedule(1000); return; }
    if (map.getZoom() < MIN_ZOOM) {
      clearPlanes();
      setInfo("Acerca el mapa para ver los aviones del área.");
      schedule();
      return;
    }
    inFlight = true;
    try {
      const bounds = map.getBounds();
      const nm = radiusNm(bounds.getSouth(), bounds.getWest(), bounds.getNorth(), bounds.getEast());
      const center = map.getCenter();
      const lat = center.lat.toFixed(2), lon = center.lng.toFixed(2);
      let payload = null, used = null, lastError = null;
      for (let i = 0; i < PROVIDERS.length && !payload; i++) {
        const provider = PROVIDERS[(providerIndex + i) % PROVIDERS.length];
        try { payload = await fetchFrom(provider, lat, lon, nm); used = provider; providerIndex = (providerIndex + i) % PROVIDERS.length; }
        catch (error) { lastError = error; }
      }
      if (!payload) throw lastError || new Error("sin respuesta");
      if (!enabled) return;
      const planes = parsePlanes(payload);
      drawPlanes(planes);
      failures = 0;
      lastGoodAt = Date.now();
      const time = new Date().toLocaleTimeString("es-CR", { hour: "numeric", minute: "2-digit" });
      setInfo(planes.length
        ? planeMarkers.size + " aviones en el área · " + used.name + " · " + time
        : "Sin aviones recibidos en esta área ahora · " + used.name + " · " + time);
      schedule();
    } catch (error) {
      failures += 1;
      if (Date.now() - lastGoodAt > KEEP_ON_ERROR_MS) clearPlanes();
      setInfo("No se pudieron cargar los aviones. Reintentando…");
      schedule(Math.min(MAX_BACKOFF_MS, REFRESH_MS * Math.pow(2, failures)));
    } finally { inFlight = false; }
  }

  function setEnabled(on) {
    enabled = !!on;
    clearTimeout(timer);
    clearTimeout(moveTimer);
    if (!enabled) {
      clearPlanes();
      clearAirports();
      setInfo("Apagado. Se piden aviones solo mientras esta capa está encendida.");
      return;
    }
    setInfo("Buscando aviones…");
    failures = 0;
    drawAirports();
    refresh();
  }

  function init() {
    const toggle = $q("aircraftToggle");
    if (!toggle) return;
    toggle.addEventListener("change", () => setEnabled(toggle.checked));
    document.addEventListener("visibilitychange", () => { if (enabled && !document.hidden) refresh(); });
    const attach = () => {
      if (typeof map === "undefined" || !map || !map.on) { setTimeout(attach, 500); return; }
      map.on("moveend", () => {
        if (!enabled) return;
        clearTimeout(moveTimer);
        moveTimer = setTimeout(refresh, 1500);
      });
      map.on("load", () => { if (enabled) drawAirports(); });
    };
    attach();
    setInfo("Apagado. Se piden aviones solo mientras esta capa está encendida.");
  }

  window.RainTrackAircraft = { setEnabled, refresh, _test: { parsePlanes, radiusNm, kmBetween, altitudeColor, squawkNote, ftToM, ktToKmh, AIRPORTS, PROVIDERS } };
  document.addEventListener("DOMContentLoaded", init);
})();
