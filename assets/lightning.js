/* Rayos reales de Costa Rica (NOAA GOES-19 GLM).
   Un workflow de GitHub lee el satélite cada ~30 s y publica lightning.json en la rama lightning-data.
   Aquí se dibujan como puntos sobre el mapa, con color y tamaño según su antigüedad. */
(function () {
  "use strict";
  const DATA_URL = "https://raw.githubusercontent.com/Allan101010/RAINROAD/lightning-data/lightning.json";
  const SOURCE_ID = "raintrack-lightning-source";
  const GLOW_ID = "raintrack-lightning-glow";
  const DOT_ID = "raintrack-lightning-dot";
  const REFRESH_MS = 30000;
  const MAX_AGE_MIN = 10;

  let payload = null;
  let timer = null;

  const info = () => document.getElementById("lightningInfo");

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

  // Mini rayo dibujado en canvas, un color por rango de antigüedad.
  const BOLT_COLORS = ["#ffffff", "#ffe44d", "#ffa000", "#a1887f"];
  function boltImage(color) {
    const w = 44, h = 64, canvas = document.createElement("canvas");
    canvas.width = w; canvas.height = h;
    const c = canvas.getContext("2d");
    c.beginPath();
    c.moveTo(27, 2); c.lineTo(8, 36); c.lineTo(21, 36); c.lineTo(15, 62); c.lineTo(37, 25); c.lineTo(24, 25); c.lineTo(32, 2);
    c.closePath();
    c.lineJoin = "round";
    c.lineWidth = 5; c.strokeStyle = "rgba(20,20,30,0.9)"; c.stroke();
    c.fillStyle = color; c.fill();
    c.lineWidth = 1.5; c.strokeStyle = "rgba(255,255,255,0.55)"; c.stroke();
    return c.getImageData(0, 0, w, h);
  }
  function ensureBoltImages() {
    BOLT_COLORS.forEach((color, i) => {
      const id = "rt-bolt-" + i;
      if (!map.hasImage(id)) map.addImage(id, boltImage(color), { pixelRatio: 2 });
    });
  }

  function draw() {
    if (typeof mapReady === "undefined" || !mapReady || !map.getStyle()) return;
    const data = featureCollection();
    const source = map.getSource(SOURCE_ID);
    if (source) { source.setData(data); return; }
    map.addSource(SOURCE_ID, { type: "geojson", data });
    const firstSymbol = map.getStyle().layers.find(layer => layer.type === "symbol");
    const before = firstSymbol ? firstSymbol.id : undefined;
    const ageColor = ["interpolate", ["linear"], ["get", "age"],
      0, "#ffffff", 1, "#fff176", 4, "#ffb300", 7, "#ef6c00", MAX_AGE_MIN, "#8d6e63"];
    map.addLayer({
      id: GLOW_ID, type: "circle", source: SOURCE_ID,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "age"], 0, 20, 3, 13, 8, 6],
        "circle-color": ageColor,
        "circle-opacity": ["interpolate", ["linear"], ["get", "age"], 0, 0.4, 3, 0.18, 8, 0],
        "circle-blur": 1
      }
    }, before);
    ensureBoltImages();
    map.addLayer({
      id: DOT_ID, type: "symbol", source: SOURCE_ID,
      layout: {
        "icon-image": ["step", ["get", "age"], "rt-bolt-0", 1, "rt-bolt-1", 4, "rt-bolt-2", 7, "rt-bolt-3"],
        "icon-size": ["interpolate", ["linear"], ["get", "age"], 0, 0.95, 3, 0.8, MAX_AGE_MIN, 0.5],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
        "icon-anchor": "center"
      },
      paint: {
        "icon-opacity": ["interpolate", ["linear"], ["get", "age"], 0, 1, 5, 0.85, MAX_AGE_MIN, 0.4]
      }
    });
  }

  function updateInfo() {
    const el = info();
    if (!el) return;
    if (!payload) { el.textContent = "Rayos reales del satélite GOES-19 (NOAA). Cargando…"; return; }
    const recent = ((payload.flashes) || []).filter(f => ageMinutes(f[0]) <= MAX_AGE_MIN).length;
    const readAge = payload.generated_at ? Math.round((Date.now() - Date.parse(payload.generated_at)) / 60000) : null;
    let text = `${recent} destellos en los últimos ${MAX_AGE_MIN} min`;
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
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  });
})();
