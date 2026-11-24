/* Datos del bot (cámaras, temblores, rayos): primero se mira el Worker de Cloudflare, donde publica la tablet,
   y si lo de allí es viejo o no existe se usa la copia de GitHub. Gana la más reciente. */
(function () {
  "use strict";
  const WORKER = "https://raintrack-aviones.raintrackcr.workers.dev";
  const FRESH_MS = 30 * 60000;

  async function get(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }

  const time = payload => (payload && Date.parse(payload.generated_at)) || 0;

  async function newest(name, staticUrl) {
    let fromWorker = null;
    let firstError = null;
    try { fromWorker = await get(WORKER + "/datos/" + name); } catch (error) { firstError = error; }
    if (fromWorker && Date.now() - time(fromWorker) < FRESH_MS) return fromWorker;
    let fromStatic = null;
    try { fromStatic = await get(staticUrl); } catch (error) { if (!fromWorker) throw error; }
    if (!fromStatic) return fromWorker;
    if (!fromWorker) return fromStatic;
    return time(fromWorker) >= time(fromStatic) ? fromWorker : fromStatic;
  }

  window.RainTrackDatos = { newest, _test: { time } };
})();
