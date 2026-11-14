/* Capa propia de lluvia medida: dibuja lluvia animada alrededor de cada estación del IMN
   que reporta precipitación reciente. No interpola ni inventa datos entre estaciones. */
(function () {
  "use strict";
  const KEY = "raintrack-ownrain";
  let canvas, ctx, raf = null, W = 0, H = 0, dpr = 1, cells = [], lastCellsAt = 0;

  const pref = () => { try { return localStorage.getItem(KEY) !== "0"; } catch (e) { return true; } };

  function rainyStations() {
    if (typeof cameraMonitorData === "undefined" || !cameraMonitorData) return [];
    const gen = cameraMonitorData.generated_at ? new Date(cameraMonitorData.generated_at).getTime() : 0;
    if (!gen || Date.now() - gen > 80 * 60 * 1000) return [];
    const rows = Array.isArray(cameraMonitorData.stations) ? cameraMonitorData.stations : [];
    return rows.filter(s => s.availability_status === "online" && Number(s.rain_last_hour_mm) > 0
      && Number.isFinite(Number(s.lat)) && Number.isFinite(Number(s.lon)));
  }

  function buildCells() {
    lastCellsAt = performance.now();
    const old = new Map(cells.map(c => [c.id, c]));
    cells = rainyStations().map(s => {
      const mm = Number(s.rain_last_hour_mm);
      const prev = old.get(s.id);
      const n = Math.min(70, 14 + Math.round(mm * 7));
      const drops = prev && prev.drops.length === n ? prev.drops : Array.from({ length: n }, () => ({
        a: Math.random() * 6.283, r: Math.sqrt(Math.random()), p: Math.random(), v: 0.012 + Math.random() * 0.012
      }));
      return { id: s.id, lat: Number(s.lat), lon: Number(s.lon), mm, drops };
    });
  }

  function metersPerPx(lat) {
    return 78271.517 * Math.cos(lat * Math.PI / 180) / Math.pow(2, map.getZoom());
  }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    ctx.clearRect(0, 0, W, H);
    if (!map || !mapReady || document.hidden) return;
    if (now - lastCellsAt > 20000) buildCells();
    for (const c of cells) {
      const pt = map.project([c.lon, c.lat]);
      const radiusM = Math.min(11000, 4500 + c.mm * 700);
      const R = Math.max(16, radiusM / metersPerPx(c.lat));
      if (pt.x < -R || pt.x > W + R || pt.y < -R || pt.y > H + R) continue;
      const g = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, R);
      const strong = Math.min(0.32, 0.12 + c.mm * 0.03);
      g.addColorStop(0, "rgba(56,130,246," + strong + ")");
      g.addColorStop(0.7, "rgba(56,130,246," + (strong * 0.5) + ")");
      g.addColorStop(1, "rgba(56,130,246,0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(pt.x, pt.y, R, 0, 6.283); ctx.fill();
      ctx.lineCap = "round"; ctx.lineWidth = R < 30 ? 1.1 : 1.5;
      for (const d of c.drops) {
        d.p += d.v; if (d.p > 1) { d.p = 0; d.a = Math.random() * 6.283; d.r = Math.sqrt(Math.random()); }
        const x = pt.x + Math.cos(d.a) * d.r * R * 0.95;
        const top = pt.y - R * 0.9 + (R * 1.7) * d.p;
        const y = top + Math.sin(d.a) * d.r * R * 0.1;
        const len = Math.max(5, R * 0.16);
        ctx.strokeStyle = "rgba(205,230,255," + (0.35 + 0.4 * (1 - d.p)) + ")";
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - len * 0.15, y - len); ctx.stroke();
      }
    }
  }

  function resize() {
    const shell = document.getElementById("mapShell");
    if (!shell || !canvas) return;
    const r = shell.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = Math.max(1, Math.round(r.width)); H = Math.max(1, Math.round(r.height));
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function start() {
    if (raf) return;
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.className = "own-rain-canvas";
      canvas.setAttribute("aria-hidden", "true");
      document.getElementById("mapShell").appendChild(canvas);
      ctx = canvas.getContext("2d");
      if (window.ResizeObserver) new ResizeObserver(resize).observe(document.getElementById("mapShell"));
      window.addEventListener("resize", resize);
    }
    resize(); buildCells();
    raf = requestAnimationFrame(frame);
  }
  function stop() {
    if (raf) cancelAnimationFrame(raf);
    raf = null;
    if (ctx) ctx.clearRect(0, 0, W, H);
  }
  function sync() {
    const sel = document.getElementById("radarSource");
    const on = sel && sel.value === "raintrack";
    if (on && typeof map !== "undefined" && map && mapReady) start(); else stop();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const wait = setInterval(() => {
      if (typeof map !== "undefined" && map && mapReady) { clearInterval(wait); sync(); }
    }, 500);
  });
  window.RainTrackOwnRain = { sync, rebuild: buildCells };
})();
