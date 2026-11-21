/* Datos más en vivo desde la tablet de la casa (vía el Worker de Cloudflare).
   - Cámara de casa: estimación cada 2 min (el bot la publica cada 10).
   - Estaciones del IMN del Valle Central: lectura cada 3 min mientras la app está abierta.
   Se usan solo si son más recientes que lo que publicó el bot; si la tablet está apagada, todo sigue como antes. */
(function () {
  "use strict";
  const WORKER = "https://raintrack-aviones.raintrackcr.workers.dev";
  const POLL_MS = 120000;
  let timer = null;
  let lastInfo = null;

  const ms = iso => { const t = Date.parse(iso || ""); return Number.isFinite(t) ? t : 0; };

  function freshness(iso, nowMs) {
    const t = ms(iso);
    if (!t) return { availability_status: "unknown", image_age_minutes: null };
    const minutes = Math.max(0, (nowMs - t) / 60000);
    return {
      availability_status: minutes <= 30 ? "online" : minutes <= 60 ? "delayed" : "stale",
      image_age_minutes: Math.round(minutes * 10) / 10
    };
  }

  // Mezcla los datos de la tablet en los del bot. Devuelve cuántas cosas cambió. (Prueba en tests/live.test.js)
  function merge(data, live, nowMs) {
    if (!data || !live) return 0;
    let changed = 0;
    const stations = live.estaciones && Array.isArray(live.estaciones.stations) ? live.estaciones.stations : [];
    if (stations.length && Array.isArray(data.stations)) {
      const byId = new Map(data.stations.map(s => [s.id, s]));
      stations.forEach(fresh => {
        const current = byId.get(fresh.id);
        if (!current || ms(fresh.image_timestamp) <= ms(current.image_timestamp)) return;
        Object.assign(current, fresh, freshness(fresh.image_timestamp, nowMs));
        current.status = current.availability_status;
        current.rain_observed = current.rain_last_hour_mm != null && current.rain_last_hour_mm > 0 &&
          current.availability_status === "online" && current.image_timestamp_source === "imn_html_table";
        current.live_source = "tablet";
        changed += 1;
      });
    }
    const cams = live.casa && Array.isArray(live.casa.cams) ? live.casa.cams : [];
    if (cams.length && Array.isArray(data.home_cameras)) {
      cams.forEach(fresh => {
        const current = data.home_cameras.find(c => c.id === fresh.id);
        if (!current || ms(fresh.t) <= ms(current.t)) return;
        if (nowMs - ms(fresh.t) > 20 * 60000) return;   // lectura vieja: la tablet no está enviando
        ["estimate", "reason", "mode", "saturation", "baseline", "basis"].forEach(k => { delete current[k]; });
        Object.assign(current, fresh, { stale: false, live_source: "tablet" });
        changed += 1;
      });
    }
    return changed;
  }

  function rerender() {
    if (typeof updateAmbientLocalRain === "function") updateAmbientLocalRain();
    if (typeof updateHomeCameraMarker === "function") updateHomeCameraMarker();
    if (typeof renderCameraAlerts === "function") renderCameraAlerts();
    if (typeof mapReady !== "undefined" && mapReady && typeof addCameraMarkers === "function" &&
        ["camerasToggle", "stationsToggle", "tempToggle"].some(id => { const el = document.getElementById(id); return el && el.checked; })) {
      addCameraMarkers();
    }
  }

  async function poll(applyOnly) {
    try {
      if (!applyOnly) {
        const response = await fetch(WORKER + "/tiempo", { cache: "no-store" });
        if (!response.ok) return;
        lastInfo = await response.json();
      }
      if (typeof cameraMonitorData !== "undefined" && merge(cameraMonitorData, lastInfo, Date.now())) rerender();
    } catch (error) { /* la tablet o el Worker no responden: se queda con los datos del bot */ }
  }

  let reapply = null;
  function schedule() {
    clearInterval(timer);
    clearInterval(reapply);
    timer = setInterval(() => { if (!document.hidden) poll(); }, POLL_MS);
    // Si el bot recargó sus datos, se vuelven a aplicar las lecturas de la tablet (sin pedir nada a la red).
    reapply = setInterval(() => { if (!document.hidden && lastInfo) poll(true); }, 20000);
  }

  function init() {
    // Cada vez que llegan los datos del bot, se vuelven a aplicar las lecturas más recientes de la tablet.
    if (typeof loadCameraMonitoringData === "function") {
      const original = loadCameraMonitoringData;
      window.loadCameraMonitoringData = async function () {
        await original.apply(this, arguments);
        await poll(!!lastInfo);
      };
    }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
    poll();
    schedule();
  }

  window.RainTrackLive = { poll, _test: { merge, freshness } };
  document.addEventListener("DOMContentLoaded", init);
})();
