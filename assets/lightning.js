/* Rayos reales de Costa Rica (NOAA GOES-19 GLM).
   Un workflow de GitHub lee el satélite cada ~30 s y publica lightning.json en la rama lightning-data.
   Aquí se dibujan como puntos sobre el mapa, con color y tamaño según su antigüedad. */
(function () {
  "use strict";
  const DATA_URL = "https://raw.githubusercontent.com/Allan101010/RAINROAD/lightning-data/lightning.json";
  const STORAGE_KEY = "raintrack-lightning-on";
  const SOURCE_ID = "raintrack-lightning-source";
  const GLOW_ID = "raintrack-lightning-glow";
  const DOT_ID = "raintrack-lightning-dot";
  const REFRESH_MS = 30000;
  const MAX_AGE_MIN = 30;

  let payload = null;
  let timer = null;

  const toggle = () => document.getElementById("lightningToggle");
  const info = () => document.getElementById("lightningInfo");
  const isOn = () => !!(toggle() && toggle().checked);

  function ageMinutes(epochSeconds) {
    return Math.max(0, (Date.now() / 1000 - epochSeconds) / 60);
  }

  function featureCollection() {
    const features = [];
    ((payload && payload.flashes) || []).forEach(f => {
      const age = ageMinutes(f[0]);
      if (age > MAX_AGE_MIN) return;
      features.push({
        type: "Feature",
        properties: { age: Math.round(age * 10) / 10 },
        geometry: { type: "Point", coordinates: [f[2], f[1]] }
      });
    });
    return { type: "FeatureCollection", features };
  }

  function removeLayers() {
    if (typeof map === "undefined" || !map || !map.getStyle || !map.getStyle()) return;
    [DOT_ID, GLOW_ID].forEach(id => { if (map.getLayer(id)) map.removeLayer(id); });
    if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
  }

  function draw() {
    if (typeof mapReady === "undefined" || !mapReady || !map.getStyle()) return;
    if (!isOn()) { removeLayers(); return; }
    const data = featureCollection();
    const source = map.getSource(SOURCE_ID);
    if (source) { source.setData(data); return; }
    map.addSource(SOURCE_ID, { type: "geojson", data });
    const firstSymbol = map.getStyle().layers.find(layer => layer.type === "symbol");
    const before = firstSymbol ? firstSymbol.id : undefined;
    const ageColor = ["interpolate", ["linear"], ["get", "age"],
      0, "#ffffff", 2, "#fff176", 10, "#ffb300", 20, "#ef6c00", MAX_AGE_MIN, "#8d6e63"];
    map.addLayer({
      id: GLOW_ID, type: "circle", source: SOURCE_ID,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "age"], 0, 16, 5, 11, MAX_AGE_MIN, 4],
        "circle-color": ageColor,
        "circle-opacity": ["interpolate", ["linear"], ["get", "age"], 0, 0.45, 5, 0.25, MAX_AGE_MIN, 0.04],
        "circle-blur": 1
      }
    }, before);
    map.addLayer({
      id: DOT_ID, type: "circle", source: SOURCE_ID,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "age"], 0, 5, 5, 4, MAX_AGE_MIN, 2.5],
        "circle-color": ageColor,
        "circle-stroke-color": "rgba(0,0,0,0.55)",
        "circle-stroke-width": 0.8,
        "circle-opacity": ["interpolate", ["linear"], ["get", "age"], 0, 1, 15, 0.8, MAX_AGE_MIN, 0.35]
      }
    }, before);
  }

  function updateInfo() {
    const el = info();
    if (!el) return;
    if (!payload) { el.textContent = "Rayos reales del satélite GOES-19 (NOAA). Cargando…"; return; }
    const recent = ((payload.flashes) || []).filter(f => ageMinutes(f[0]) <= 15).length;
    const readAge = payload.generated_at ? Math.round((Date.now() - Date.parse(payload.generated_at)) / 60000) : null;
    let text = `${recent} destellos en los últimos 15 min`;
    if (readAge != null) text += ` · lectura hace ${readAge} min`;
    if (readAge != null && readAge > 15) text += " (datos atrasados)";
    el.textContent = text + " · satélite GOES-19, precisión de varios km.";
  }

  async function refresh() {
    try {
      const response = await fetch(`${DATA_URL}?t=${Math.floor(Date.now() / 60000)}`, { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      payload = await response.json();
    } catch (error) {
      console.info("Rayos GLM no disponibles:", error.message);
    }
    draw();
    updateInfo();
    document.dispatchEvent(new CustomEvent("raintrack:lightning"));
  }

  // ¿Hubo rayos cerca de un punto en los últimos minutos?
  function nearby(lat, lon, radiusKm, minutes) {
    if (!payload || !Array.isArray(payload.flashes)) return 0;
    const rad = Math.PI / 180;
    let count = 0;
    payload.flashes.forEach(f => {
      if (ageMinutes(f[0]) > minutes) return;
      const a = Math.sin((f[1] - lat) * rad / 2) ** 2 +
        Math.cos(lat * rad) * Math.cos(f[1] * rad) * Math.sin((f[2] - lon) * rad / 2) ** 2;
      if (12742 * Math.asin(Math.sqrt(a)) <= radiusKm) count += 1;
    });
    return count;
  }

  window.RainTrackLightning = { nearby, refresh, redraw: draw };

  document.addEventListener("DOMContentLoaded", () => {
    const checkbox = toggle();
    if (!checkbox) return;
    try { if (localStorage.getItem(STORAGE_KEY) === "0") checkbox.checked = false; } catch (e) {}
    checkbox.addEventListener("change", () => {
      try { localStorage.setItem(STORAGE_KEY, checkbox.checked ? "1" : "0"); } catch (e) {}
      draw();
    });
    refresh();
    timer = setInterval(() => { refresh(); }, REFRESH_MS);
    // Reponer la capa cuando el mapa termina de cargar o cambia de estilo (claro/oscuro).
    const attach = () => {
      if (typeof map === "undefined" || !map || !map.on) { setTimeout(attach, 500); return; }
      map.on("style.load", draw);
      map.on("load", draw);
      if (typeof mapReady !== "undefined" && mapReady) draw();
    };
    attach();
    setInterval(updateInfo, 30000);
  });
})();
