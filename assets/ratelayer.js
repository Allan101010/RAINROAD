/* Capa propia de lluvia medida: dibuja lluvia animada alrededor de cada estación del IMN
   que reporta precipitación reciente. No interpola ni inventa datos entre estaciones. */
(function () {
  "use strict";
  const KEY = "raintrack-ownrain";
  const STORM_MM = 8; // lluvia intensa: se trata como tormenta (el IMN no publica rayos con coordenadas)
  let canvas, ctx, raf = null, W = 0, H = 0, dpr = 1, cells = [], lastCellsAt = 0;

  const pref = () => { try { return localStorage.getItem(KEY) !== "0"; } catch (e) { return true; } };

  // Edad real del dato (minutos): la que tenía al guardarse + el tiempo desde que se guardó.
  function stationAge(s, gen) {
    const base = Number(s.image_age_minutes);
    return (Number.isFinite(base) ? base : 0) + Math.max(0, (Date.now() - gen) / 60000);
  }
  // Cuánto tiempo se considera vigente una lluvia según su intensidad: la llovizna pasa rápido.
  function maxAgeFor(mm) { return mm < 0.5 ? 45 : mm < 2 ? 60 : 80; }
  // 1 = dato reciente (hasta 15 min); baja hasta 0 al vencer su vigencia.
  function freshness(mm, age) {
    if (age <= 15) return 1;
    const max = maxAgeFor(mm);
    return Math.max(0, 1 - (age - 15) / (max - 15));
  }

  function rainyStations() {
    if (typeof cameraMonitorData === "undefined" || !cameraMonitorData) return [];
    const gen = cameraMonitorData.generated_at ? new Date(cameraMonitorData.generated_at).getTime() : 0;
    if (!gen || Date.now() - gen > 80 * 60 * 1000) return [];
    const rows = Array.isArray(cameraMonitorData.stations) ? cameraMonitorData.stations : [];
    return rows.filter(s => s.availability_status === "online" && Number(s.rain_last_hour_mm) > 0
      && Number.isFinite(Number(s.lat)) && Number.isFinite(Number(s.lon)))
      .map(s => Object.assign({}, s, { _fresh: freshness(Number(s.rain_last_hour_mm), stationAge(s, gen)) }))
      .filter(s => s._fresh > 0.03);
  }

  function buildCells() {
    lastCellsAt = performance.now();
    const old = new Map(cells.map(c => [c.id, c]));
    cells = rainyStations().map(s => {
      const mm = Number(s.rain_last_hour_mm);
      const prev = old.get(s.id);
      const n = mm < 0.5 ? 8 : Math.min(70, 14 + Math.round(mm * 7));
      const drops = prev && prev.drops.length === n ? prev.drops : Array.from({ length: n }, () => ({
        a: Math.random() * 6.283, r: Math.sqrt(Math.random()), p: Math.random(), v: 0.012 + Math.random() * 0.012
      }));
      return { id: s.id, lat: Number(s.lat), lon: Number(s.lon), mm, fresh: s._fresh, drizzle: mm < 0.5, drops, storm: mm >= STORM_MM && s._fresh > 0.5,
               nextBolt: prev ? prev.nextBolt : performance.now() + 800 + Math.random() * 3000, bolt: prev ? prev.bolt : null };
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
      ctx.globalAlpha = c.drizzle ? c.fresh * 0.7 : c.fresh;
      const pt = map.project([c.lon, c.lat]);
      const radiusM = c.drizzle ? 3500 : Math.min(11000, 4500 + c.mm * 700);
      const R = Math.max(16, radiusM / metersPerPx(c.lat));
      if (pt.x < -R || pt.x > W + R || pt.y < -R || pt.y > H + R) continue;
      const g = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, R);
      const strong = Math.min(0.32, 0.12 + c.mm * 0.03);
      const rgb = c.storm ? "88,80,236" : "56,130,246";
      g.addColorStop(0, "rgba(" + rgb + "," + (c.storm ? Math.min(0.4, strong + 0.06) : strong) + ")");
      g.addColorStop(0.7, "rgba(" + rgb + "," + (strong * 0.5) + ")");
      g.addColorStop(1, "rgba(" + rgb + ",0)");
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
      if (c.storm) drawStorm(c, pt, R, now);
    }
    ctx.globalAlpha = 1;
  }

  function makeBolt(pt, R) {
    const pts = [[pt.x + (Math.random() - 0.5) * R * 0.6, pt.y - R * 0.85]];
    const step = Math.max(5, R / 7), endY = pt.y + R * 0.15;
    while (pts[pts.length - 1][1] < endY) {
      const [x, y] = pts[pts.length - 1];
      pts.push([x + (Math.random() - 0.5) * step * 1.6, y + step * (0.8 + Math.random() * 0.6)]);
    }
    return { pts, life: 30 };
  }
  function drawStorm(c, pt, R, now) {
    if (!c.bolt && now > c.nextBolt) {
      c.bolt = makeBolt(pt, R);
      c.nextBolt = now + 3000 + Math.random() * 7000;
    }
    if (!c.bolt) return;
    const l = c.bolt.life;
    const a = l > 24 ? 1 : l > 20 ? 0.25 : l > 15 ? 0.9 : l / 15;
    const fg = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, R);
    fg.addColorStop(0, "rgba(220,230,255," + (0.38 * a) + ")");
    fg.addColorStop(1, "rgba(160,180,255,0)");
    ctx.fillStyle = fg; ctx.beginPath(); ctx.arc(pt.x, pt.y, R, 0, 6.283); ctx.fill();
    if (R >= 22) {
      ctx.save();
      ctx.shadowColor = "rgba(170,190,255," + a + ")"; ctx.shadowBlur = 12;
      ctx.strokeStyle = "rgba(250,252,255," + a + ")"; ctx.lineWidth = Math.max(1.2, Math.min(2.6, R / 28)); ctx.lineJoin = "round";
      ctx.beginPath(); c.bolt.pts.forEach((q, i) => i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1])); ctx.stroke();
      ctx.restore();
    }
    if (--c.bolt.life <= 0) c.bolt = null;
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
  window.RainTrackOwnRain = { sync, rebuild: buildCells, stormCount: () => cells.filter(c => c.storm).length, cellCount: () => cells.length };
})();
