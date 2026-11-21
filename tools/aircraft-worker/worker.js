// Intermediario de aviones para RainTrack CR (Cloudflare Worker + D1, plan gratis).
// La tablet de la casa (conexión residencial) consulta adsb.fi y publica aquí; la app lee desde aquí.
//   GET  /?lat=9.93&lon=-84.08&r=80   → aviones dentro del radio (millas náuticas). También marca que alguien está mirando.
//   GET  /demanda                      → {"wanted":true} si alguien miró en los últimos minutos (la tablet solo trabaja entonces).
//   POST /publicar  (cabecera X-Clave) → la tablet sube la foto actual. La primera clave que llega queda registrada.
//   POST /vientos   (cabecera X-Clave) → la tablet guarda viento y temperatura que reportan los aviones (cada 10 min).
//   GET  /vientos?horas=24             → esas mediciones, para analizarlas (se guardan 30 días).
//   POST /casa, /estaciones (X-Clave)  → la tablet publica la estimación de la cámara de casa (cada 2 min) y
//                                        lecturas frescas de estaciones del IMN (cada 3 min con la app abierta).
//   GET  /tiempo                       → lo último de ambas, y marca que la app está abierta.
// Requiere un binding D1 llamado DB.
const ORIGIN = "https://allan101010.github.io";
const CORS = { "Access-Control-Allow-Origin": ORIGIN, "Access-Control-Allow-Methods": "GET", "Vary": "Origin" };
const JSON_HEAD = { ...CORS, "Content-Type": "application/json", "Cache-Control": "no-store" };
const DEMAND_WINDOW_S = 180;
const WX_WINDOW_S = 900;       // estaciones: la tablet sigue leyendo 15 min después de la última visita   // la tablet sigue enviando hasta 3 min después de la última consulta
const STALE_S = 90;            // una foto más vieja que esto no se entrega como "en vivo"
const KEEP = ["hex", "flight", "r", "t", "desc", "lat", "lon", "alt_baro", "alt_geom", "gs", "track", "baro_rate", "squawk", "seen_pos", "seen"];

const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: JSON_HEAD });
const nowS = () => Math.floor(Date.now() / 1000);

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}

function nmBetween(lat1, lon1, lat2, lon2) {
  const rad = Math.PI / 180, dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 3440.065 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

async function ready(db) {
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, t INTEGER)"),
    db.prepare("CREATE TABLE IF NOT EXISTS winds (t INTEGER, hex TEXT, lat REAL, lon REAL, alt INTEGER, wd INTEGER, ws INTEGER, oat INTEGER, track INTEGER, gs INTEGER)"),
    db.prepare("CREATE INDEX IF NOT EXISTS winds_t ON winds (t)")
  ]);
}

async function checkKey(db, req) {
  const clave = req.headers.get("X-Clave") || "";
  if (clave.length < 20) return false;
  const hash = await sha256(clave);
  const saved = await getRow(db, "clave");
  if (!saved) { await putRow(db, "clave", hash); return true; }   // primer registro
  return saved.v === hash;
}
const getRow = (db, k) => db.prepare("SELECT v, t FROM kv WHERE k = ?").bind(k).first();
const putRow = (db, k, v) => db.prepare("INSERT INTO kv (k, v, t) VALUES (?, ?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v, t = excluded.t").bind(k, v, nowS()).run();

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (!env.DB) return json({ error: "falta binding DB" }, 500);
    const url = new URL(req.url);
    await ready(env.DB);

    if (url.pathname === "/publicar" && req.method === "POST") {
      if (!(await checkKey(env.DB, req))) return json({ error: "clave" }, 401);
      const text = await req.text();
      if (text.length > 500000) return json({ error: "muy grande" }, 413);
      let data;
      try { data = JSON.parse(text); } catch (e) { return json({ error: "json" }, 400); }
      const list = Array.isArray(data.ac) ? data.ac : Array.isArray(data.aircraft) ? data.aircraft : [];
      const slim = list.slice(0, 800).map(a => Object.fromEntries(KEEP.filter(k => a[k] !== undefined).map(k => [k, a[k]])));
      await putRow(env.DB, "snap", JSON.stringify({ ac: slim, src: String(data.src || "adsb.fi").slice(0, 30) }));
      return json({ ok: true, n: slim.length });
    }

    if (url.pathname === "/vientos" && req.method === "POST") {
      if (!(await checkKey(env.DB, req))) return json({ error: "clave" }, 401);
      let data;
      try { data = JSON.parse(await req.text()); } catch (e) { return json({ error: "json" }, 400); }
      const t = nowS();
      const num = v => (Number.isFinite(Number(v)) && v !== null && v !== "" ? Math.round(Number(v)) : null);
      const rows = (Array.isArray(data.obs) ? data.obs : []).slice(0, 300)
        .filter(o => Number.isFinite(o.lat) && Number.isFinite(o.lon) && Number.isFinite(Number(o.wd)) && Number.isFinite(Number(o.ws)))
        .map(o => env.DB.prepare("INSERT INTO winds (t, hex, lat, lon, alt, wd, ws, oat, track, gs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(t - Math.min(60, Math.max(0, num(o.seen) || 0)), String(o.hex || "").slice(0, 8), Math.round(o.lat * 1000) / 1000, Math.round(o.lon * 1000) / 1000,
                num(o.alt), num(o.wd), num(o.ws), num(o.oat), num(o.track), num(o.gs)));
      rows.push(env.DB.prepare("DELETE FROM winds WHERE t < ?").bind(t - 30 * 86400));
      await env.DB.batch(rows);
      return json({ ok: true, n: rows.length - 1 });
    }

    if (url.pathname === "/vientos" && req.method === "GET") {
      const hours = Math.min(720, Math.max(1, Number(url.searchParams.get("horas")) || 24));
      const res = await env.DB.prepare("SELECT t, hex, lat, lon, alt, wd, ws, oat, track, gs FROM winds WHERE t >= ? ORDER BY t").bind(nowS() - hours * 3600).all();
      return new Response(JSON.stringify({ rows: res.results || [] }), { headers: { ...JSON_HEAD, "Access-Control-Allow-Origin": "*" } });
    }

    if ((url.pathname === "/casa" || url.pathname === "/estaciones") && req.method === "POST") {
      if (!(await checkKey(env.DB, req))) return json({ error: "clave" }, 401);
      const text = await req.text();
      if (text.length > 200000) return json({ error: "muy grande" }, 413);
      try { JSON.parse(text); } catch (e) { return json({ error: "json" }, 400); }
      await putRow(env.DB, url.pathname.slice(1), text);
      return json({ ok: true });
    }

    if (url.pathname === "/tiempo" && req.method === "GET") {
      const d = await getRow(env.DB, "demand_wx");
      if (!d || nowS() - d.t >= 30) await putRow(env.DB, "demand_wx", "1");
      const out = {};
      for (const k of ["casa", "estaciones"]) {
        const row = await getRow(env.DB, k);
        if (row) out[k] = { ...JSON.parse(row.v), age_s: nowS() - row.t };
      }
      return json(out);
    }

    if (url.pathname === "/demanda") {
      const d = await getRow(env.DB, "demand");
      const w = await getRow(env.DB, "demand_wx");
      return json({ wanted: !!d && nowS() - d.t < DEMAND_WINDOW_S, wx_wanted: !!w && nowS() - w.t < WX_WINDOW_S });
    }

    if (url.pathname === "/" && req.method === "GET") {
      const lat = Number(url.searchParams.get("lat")), lon = Number(url.searchParams.get("lon")), r = Number(url.searchParams.get("r"));
      if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 && r >= 1 && r <= 250)) return json({ error: "parametros" }, 400);
      const d = await getRow(env.DB, "demand");
      if (!d || nowS() - d.t >= 5) await putRow(env.DB, "demand", "1");   // a lo sumo una escritura cada 5 s
      const snap = await getRow(env.DB, "snap");
      if (!snap) return json({ ac: [], age_s: null, stale: true });
      const age = nowS() - snap.t;
      const data = JSON.parse(snap.v);
      const ac = age > STALE_S ? [] : data.ac.filter(a => Number.isFinite(a.lat) && Number.isFinite(a.lon) && nmBetween(lat, lon, a.lat, a.lon) <= r);
      return json({ ac, age_s: age, stale: age > STALE_S, src: data.src });
    }
    return json({ error: "ruta" }, 404);
  }
};
