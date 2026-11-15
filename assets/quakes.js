/* Temblores y terremotos (OVSICORI + USGS + EMSC).
   Un workflow de GitHub lee las dos fuentes cada ~30 s y publica quakes.json en la rama quakes-data.
   Aquí se dibujan en el mapa (desde M3.5), se listan en su sección y, desde M5, salen en el aviso de arriba.
   IMPORTANTE: informa DESPUÉS del sismo. No es una alerta temprana. */
(function () {
  "use strict";
  const DATA_URL = "https://raw.githubusercontent.com/Allan101010/RAINROAD/quakes-data/quakes.json";
  const STORAGE_KEY = "raintrack-quakes-on";
  const DISMISS_KEY = "raintrack-quakes-dismissed";
  const REFRESH_MS = 60000;
  const BANNER_MIN_MAG = 5;
  const BANNER_HOURS = 3;
  const PULSE_MINUTES = 60;
  const LIST_SHORT = 8;

  let payload = null;
  let markers = [];
  let showAll = false;

  const $q = id => document.getElementById(id);
  const esc = text => String(text == null ? "" : text).replace(/[&<>"']/g,
    ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const eventId = q => q.t + "_" + q.lat + "_" + q.lon;
  const minutesAgo = q => Math.max(0, (Date.now() / 1000 - q.t) / 60);

  function ago(minutes) {
    if (minutes < 1) return "hace un momento";
    if (minutes < 60) return "hace " + Math.round(minutes) + " min";
    if (minutes < 48 * 60) {
      const hours = Math.floor(minutes / 60);
      const rest = Math.round(minutes % 60);
      return "hace " + hours + " h" + (hours < 6 && rest ? " " + rest + " min" : "");
    }
    return "hace más de 2 días";
  }

  function localTime(q) {
    try {
      return new Date(q.t * 1000).toLocaleString("es-CR", {
        timeZone: "America/Costa_Rica", day: "numeric", month: "short", hour: "numeric", minute: "2-digit"
      });
    } catch (e) { return ""; }
  }

  function sourcesText(q) {
    return (q.src || []).map(s => String(s).toUpperCase()).join(" y ");
  }

  function enabled() {
    const checkbox = $q("quakeToggle");
    return !checkbox || checkbox.checked;
  }

  function quakes() {
    return payload && Array.isArray(payload.quakes) ? payload.quakes.filter(q =>
      q && Number.isFinite(q.t) && Number.isFinite(q.lat) && Number.isFinite(q.lon) && Number.isFinite(q.mag)) : [];
  }

  function dismissed() {
    try { return new Set(JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]")); } catch (e) { return new Set(); }
  }

  function saveDismissed(set) {
    try { localStorage.setItem(DISMISS_KEY, JSON.stringify(Array.from(set).slice(-50))); } catch (e) {}
  }

  function stale() {
    if (!payload || !payload.generated_at) return false;
    return (Date.now() - Date.parse(payload.generated_at)) / 60000 > 25;
  }

  // ---------- Mapa ----------
  function clearMarkers() {
    markers.forEach(marker => marker.remove());
    markers = [];
  }

  function markerElement(q) {
    const minutes = minutesAgo(q);
    const size = Math.round(Math.min(44, Math.max(20, 12 + (q.mag - 3) * 9)));
    const hue = minutes < 60 ? "#ef4444" : minutes < 360 ? "#f97316" : "#d6a24a";
    const el = document.createElement("button");
    el.type = "button";
    el.className = "quake-marker" + (q.cr ? " cr" : "") + (q.cr && minutes < PULSE_MINUTES ? " fresh" : "");
    el.style.width = el.style.height = size + "px";
    el.style.background = hue;
    el.style.fontSize = Math.max(10, Math.round(size * 0.42)) + "px";
    el.setAttribute("aria-label", "Sismo de magnitud " + q.mag.toFixed(1));
    el.textContent = q.mag.toFixed(1);
    return el;
  }

  function popupHtml(q) {
    const depth = q.depth == null ? "" : "<br>Profundidad: " + Math.round(q.depth) + " km";
    const mags = q.mags && Object.keys(q.mags).length > 1
      ? "<br>Magnitud: " + Object.keys(q.mags).map(k => k.toUpperCase() + " " + Number(q.mags[k]).toFixed(1)).join(" · ")
      : "";
    return "<div class=\"quake-popup\"><strong>" + (q.cr ? "🇨🇷 " : "🌎 ") + "Sismo M" + q.mag.toFixed(1) + "</strong><br>" +
      esc(q.place || "Región de Costa Rica") + "<br>" + esc(localTime(q)) + " · " + ago(minutesAgo(q)) + depth + mags +
      "<br><small>Fuente: " + esc(sourcesText(q)) + ". Magnitud preliminar; informa después del sismo, no es alerta temprana.</small></div>";
  }

  function drawMarkers() {
    clearMarkers();
    if (typeof map === "undefined" || !map || typeof mapReady === "undefined" || !mapReady || !enabled()) return;
    quakes().forEach(q => {
      const popup = new maplibregl.Popup({ offset: 16, maxWidth: "260px" }).setHTML(popupHtml(q));
      const marker = new maplibregl.Marker({ element: markerElement(q), anchor: "center" })
        .setLngLat([q.lon, q.lat]).setPopup(popup).addTo(map);
      markers.push(marker);
    });
  }

  function flyTo(q) {
    if (typeof map === "undefined" || !map) return;
    map.flyTo({ center: [q.lon, q.lat], zoom: Math.max(map.getZoom(), 8), speed: 1.2 });
    const mapEl = $q("map");
    if (mapEl && mapEl.scrollIntoView) mapEl.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // ---------- Aviso de arriba (M5 o más) ----------
  function renderBanner() {
    const stack = $q("quakeAlertStack");
    if (!stack) return;
    const hidden = dismissed();
    const items = quakes().filter(q => q.mag >= BANNER_MIN_MAG && minutesAgo(q) <= BANNER_HOURS * 60 &&
      !hidden.has(eventId(q))).sort((a, b) => (b.cr - a.cr) || (b.t - a.t)).slice(0, 2);
    if (!items.length || !enabled()) { stack.hidden = true; stack.innerHTML = ""; return; }
    stack.hidden = false;
    stack.innerHTML = items.map(q => {
      const place = esc((q.place || "").replace(/^\d+\s*km\s+\w+\s+of\s+/i, "") || "región de Costa Rica");
      const text = q.cr
        ? "<span class=\"quake-banner-label\">🚨 TEMBLOR EN COSTA RICA</span><b>M" + q.mag.toFixed(1) + "</b> · " + place + " · " + ago(minutesAgo(q))
        : "<span class=\"quake-banner-label\">🌎 Sismo en la región</span><b>M" + q.mag.toFixed(1) + "</b> · " + place + " · " + ago(minutesAgo(q));
      return "<div class=\"quake-banner" + (q.cr ? " cr" : "") + "\" role=\"status\">" +
        "<button type=\"button\" class=\"quake-banner-main\" data-quake-fly=\"" + esc(eventId(q)) + "\">" + text + "</button>" +
        "<button type=\"button\" class=\"quake-banner-close\" data-quake-dismiss=\"" + esc(eventId(q)) + "\" aria-label=\"Ocultar aviso\" title=\"Ocultar\">×</button></div>";
    }).join("");
  }

  // ---------- Sección con la lista ----------
  function renderList() {
    const box = $q("quakeList");
    const info = $q("quakeInfo");
    if (!box) return;
    const all = quakes().sort((a, b) => b.t - a.t);
    if (!payload) {
      box.innerHTML = "<p class=\"tiny\">Cargando temblores…</p>";
      if (info) info.textContent = "Cargando…";
      return;
    }
    const readAge = payload.generated_at ? Math.round((Date.now() - Date.parse(payload.generated_at)) / 60000) : null;
    if (info) {
      info.textContent = all.length + " en las últimas 48 h (M" + (payload.min_mag || 3.5) + " o más)" +
        (readAge != null ? " · lectura hace " + readAge + " min" : "") + (stale() ? " · datos atrasados" : "");
    }
    if (!all.length) {
      box.innerHTML = "<p class=\"tiny\">Sin temblores de M" + (payload.min_mag || 3.5) + " o más en las últimas 48 horas, según OVSICORI, USGS y EMSC.</p>";
      return;
    }
    const shown = showAll ? all : all.slice(0, LIST_SHORT);
    box.innerHTML = shown.map(q => {
      const depth = q.depth == null ? "" : " · prof. " + Math.round(q.depth) + " km";
      return "<button type=\"button\" class=\"quake-row" + (q.cr ? " cr" : "") + (q.mag >= 5 ? " big" : "") + "\" data-quake-fly=\"" + esc(eventId(q)) + "\">" +
        "<span class=\"quake-row-mag\">" + q.mag.toFixed(1) + "</span>" +
        "<span class=\"quake-row-body\"><strong>" + (q.cr ? "🇨🇷 " : "") + esc(q.place || "Región de Costa Rica") + "</strong>" +
        "<small>" + esc(localTime(q)) + " · " + ago(minutesAgo(q)) + depth + " · " + esc(sourcesText(q)) + "</small></span></button>";
    }).join("") + (all.length > LIST_SHORT
      ? "<button type=\"button\" class=\"btn ghost small-btn quake-more\" id=\"quakeMore\">" + (showAll ? "Ver menos ▲" : "Ver los " + all.length + " ▼") + "</button>" : "");
  }

  function renderAll() {
    drawMarkers();
    renderBanner();
    renderList();
  }

  async function refresh() {
    try {
      const response = await fetch(DATA_URL + "?t=" + Math.floor(Date.now() / 60000), { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      payload = await response.json();
    } catch (error) {
      console.info("Temblores no disponibles:", error.message);
    }
    renderAll();
  }

  function findById(id) {
    return quakes().find(q => eventId(q) === id);
  }

  document.addEventListener("click", event => {
    const fly = event.target.closest("[data-quake-fly]");
    if (fly) { const q = findById(fly.getAttribute("data-quake-fly")); if (q) flyTo(q); return; }
    const close = event.target.closest("[data-quake-dismiss]");
    if (close) {
      const set = dismissed();
      set.add(close.getAttribute("data-quake-dismiss"));
      saveDismissed(set);
      renderBanner();
      return;
    }
    if (event.target.id === "quakeMore") { showAll = !showAll; renderList(); }
  });

  window.RainTrackQuakes = { refresh, redraw: renderAll };

  document.addEventListener("DOMContentLoaded", () => {
    const checkbox = $q("quakeToggle");
    if (checkbox) {
      try { if (localStorage.getItem(STORAGE_KEY) === "0") checkbox.checked = false; } catch (e) {}
      checkbox.addEventListener("change", () => {
        try { localStorage.setItem(STORAGE_KEY, checkbox.checked ? "1" : "0"); } catch (e) {}
        renderAll();
      });
    }
    refresh();
    setInterval(refresh, REFRESH_MS);
    setInterval(renderAll, 60000);
    const attach = () => {
      if (typeof map === "undefined" || !map || !map.on) { setTimeout(attach, 500); return; }
      map.on("load", drawMarkers);
      if (typeof mapReady !== "undefined" && mapReady) drawMarkers();
    };
    attach();
  });
})();
