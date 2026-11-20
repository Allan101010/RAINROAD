// Intermediario de aviones para RainTrack CR (Cloudflare Worker + D1, plan gratis).
// La tablet de la casa (conexión residencial) consulta adsb.fi y publica aquí; la app lee desde aquí.
//   GET  /?lat=9.93&lon=-84.08&r=80   → aviones dentro del radio (millas náuticas). También marca que alguien está mirando.
//   GET  /demanda                      → {"wanted":true} si alguien miró en los últimos minutos (la tablet solo trabaja entonces).
//   POST /publicar  (cabecera X-Clave) → la tablet sube la foto actual. La primera clave que llega queda registrada.
// Requiere un binding D1 llamado DB.
const ORIGIN = "https://allan101010.github.io";
const CORS = { "Access-Control-Allow-Origin": ORIGIN, "Access-Control-Allow-Methods": "GET", "Vary": "Origin" };
const JSON_HEAD = { ...CORS, "Content-Type": "application/json", "Cache-Control": "no-store" };
const DEMAND_WINDOW_S = 180;   // la tablet sigue enviando hasta 3 min después de la última consulta
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
  await db.prepare("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, t INTEGER)").run();
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
      const clave = req.headers.get("X-Clave") || "";
      if (clave.length < 20) return json({ error: "clave" }, 401);
      const hash = await sha256(clave);
      const saved = await getRow(env.DB, "clave");
      if (!saved) await putRow(env.DB, "clave", hash);          // primer registro
      else if (saved.v !== hash) return json({ error: "clave" }, 401);
      const text = await req.text();
      if (text.length > 500000) return json({ error: "muy grande" }, 413);
      let data;
      try { data = JSON.parse(text); } catch (e) { return json({ error: "json" }, 400); }
      const list = Array.isArray(data.ac) ? data.ac : Array.isArray(data.aircraft) ? data.aircraft : [];
      const slim = list.slice(0, 800).map(a => Object.fromEntries(KEEP.filter(k => a[k] !== undefined).map(k => [k, a[k]])));
      await putRow(env.DB, "snap", JSON.stringify({ ac: slim, src: String(data.src || "adsb.fi").slice(0, 30) }));
      return json({ ok: true, n: slim.length });
    }

    if (url.pathname === "/demanda") {
      const d = await getRow(env.DB, "demand");
      return json({ wanted: !!d && nowS() - d.t < DEMAND_WINDOW_S });
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
