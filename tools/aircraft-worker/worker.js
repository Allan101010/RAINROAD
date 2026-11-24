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
//   POST /ia  (X-Clave, X-Cam, cuerpo JPEG) → la IA de visión clasifica la foto: LLUVIA, NUBLADO, DESPEJADO o NO_SE_VE.
//   GET  /ia?horas=24                  → resultados de la prueba;  GET /ia/foto?id=N → la foto analizada (7 días).
// Bindings: D1 "DB" y Workers AI "AI".
// Requiere un binding D1 llamado DB.
const ORIGIN = "*";   // datos públicos de solo lectura; la app vive en GitHub Pages y en Cloudflare Pages
const CORS = { "Access-Control-Allow-Origin": ORIGIN, "Access-Control-Allow-Methods": "GET" };
const JSON_HEAD = { ...CORS, "Content-Type": "application/json", "Cache-Control": "no-store" };
const DEMAND_WINDOW_S = 180;
const WX_WINDOW_S = 900;
const AI_MODEL = "@cf/meta/llama-3.2-11b-vision-instruct";
const AI_DAILY_CAP = 1100;     // el plan gratis da 10 000 "neuronas" al día; cada foto pequeña usa ~8
const AI_PROMPT = "You are checking a public outdoor webcam image for a rain-alert app. Answer with exactly one word:\n" +
  "RAIN - rain is visibly falling, or raindrops/streaks are on the lens, or the scene shows active rain (wet shiny ground with grey rainy sky).\n" +
  "FOG - overcast, grey, misty or foggy, but no visible rain.\n" +
  "CLEAR - sunny, blue sky or partly cloudy and dry.\n" +
  "UNKNOWN - too dark, blurry, blocked, frozen or not an outdoor view.\n" +
  "One word only.";
const AI_LABELS = { RAIN: "LLUVIA", FOG: "NUBLADO", CLEAR: "DESPEJADO", UNKNOWN: "NO_SE_VE" };
// Pregunta v2: lluvia sí/no por separado del cielo (los modelos chicos confunden "gris" con "lluvia").
const AI_PROMPT_V2 = "Look at this outdoor webcam photo. Reply in exactly this format: RAIN=yes or RAIN=no; SKY=clear, partly, overcast, fog or unknown.\n" +
  "RAIN=yes only if rain is actually visible: falling rain or rain streaks, raindrops on the lens, splashes, or ground that is shiny and wet with puddles during rain. " +
  "A grey or cloudy sky alone is NOT rain. Sunshine or blue sky means RAIN=no. If it is too dark, blurry or not an outdoor view, reply RAIN=no; SKY=unknown.";
const AI_TEST_MODELS = {
  llama32: "@cf/meta/llama-3.2-11b-vision-instruct",
  gemma3: "@cf/google/gemma-3-12b-it",
  llama4: "@cf/meta/llama-4-scout-17b-16e-instruct",
  mistral: "@cf/mistralai/mistral-small-3.1-24b-instruct"
};
const AI_TEST_DAILY_CAP = 300;
const DATA_NAMES = ["camaras", "catalogo", "temblores", "rayos"];

function parseV2(raw) {
  const text = String(raw || "").toLowerCase();
  const rain = /rain\s*=\s*yes/.test(text) ? true : /rain\s*=\s*no/.test(text) ? false : null;
  const sky = (text.match(/sky\s*=\s*(clear|partly|overcast|fog|unknown)/) || [])[1] || null;
  return { rain, sky };
}

async function runVision(env, model, prompt, buf, maxTokens) {
  let b64 = "";
  for (let i = 0; i < buf.length; i += 0x8000) b64 += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  b64 = btoa(b64);
  const inputs = [
    { messages: [{ role: "user", content: [{ type: "text", text: prompt }, { type: "image_url", image_url: { url: "data:image/jpeg;base64," + b64 } }] }], max_tokens: maxTokens, temperature: 0 },
    { prompt, image: [...buf], max_tokens: maxTokens, temperature: 0 }
  ];
  let lastError = "";
  for (let attempt = 0; attempt < 2; attempt++) {
    for (const input of inputs) {
      try {
        const out = await env.AI.run(model, input);
        const text = out && (out.response ?? out.result ?? (out.choices && out.choices[0] && out.choices[0].message && out.choices[0].message.content));
        return { raw: String(typeof text === "string" ? text : JSON.stringify(text || out)).trim().slice(0, 200), usage: out && out.usage };
      } catch (e) { lastError = String(e); }
    }
    if (/agree/i.test(lastError)) { try { await env.AI.run(model, { prompt: "agree" }); } catch (e) { /* licencia */ } }
    else break;
  }
  throw new Error(lastError.slice(0, 300));
}       // estaciones: la tablet sigue leyendo 15 min después de la última visita   // la tablet sigue enviando hasta 3 min después de la última consulta
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
    db.prepare("CREATE INDEX IF NOT EXISTS winds_t ON winds (t)"),
    db.prepare("CREATE TABLE IF NOT EXISTS ia (id INTEGER PRIMARY KEY AUTOINCREMENT, t INTEGER, cam TEXT, label TEXT, raw TEXT, lat REAL, lon REAL, img BLOB)"),
    db.prepare("CREATE INDEX IF NOT EXISTS ia_t ON ia (t)")
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
    try { return await handle(req, env); }
    catch (e) { return json({ error: "interno", detail: String(e && e.stack || e).slice(0, 400) }, 500); }
  }
};

async function handle(req, env) {
  {
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

    if (url.pathname.startsWith("/datos/")) {
      const name = url.pathname.slice(7);
      if (!DATA_NAMES.includes(name)) return json({ error: "nombre" }, 404);
      if (req.method === "POST") {
        if (!(await checkKey(env.DB, req))) return json({ error: "clave" }, 401);
        const text = await req.text();
        if (text.length > 1500000) return json({ error: "muy grande" }, 413);
        try { JSON.parse(text); } catch (e) { return json({ error: "json" }, 400); }
        await putRow(env.DB, "datos_" + name, text);
        return json({ ok: true, bytes: text.length });
      }
      if (req.method === "GET") {
        const row = await getRow(env.DB, "datos_" + name);
        if (!row) return json({ error: "sin datos" }, 404);
        return new Response(row.v, { headers: { ...JSON_HEAD, "X-Edad": String(nowS() - row.t) } });
      }
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

    if (url.pathname === "/ia" && req.method === "POST") {
      if (!(await checkKey(env.DB, req))) return json({ error: "clave" }, 401);
      if (!env.AI) return json({ error: "falta binding AI" }, 500);
      const day = new Date().toISOString().slice(0, 10);
      const used = await getRow(env.DB, "ia_" + day);
      const count = used ? Number(used.v) : 0;
      if (count >= AI_DAILY_CAP) return json({ error: "cupo", used: count }, 429);
      const buf = new Uint8Array(await req.arrayBuffer());
      if (buf.length < 1000 || buf.length > 400000) return json({ error: "tamaño" }, 413);
      // Pregunta v2 (lluvia sí/no + cielo): en la prueba del 22-nov acertó 15 de 17 fotos sin falsas alarmas.
      let raw;
      try { raw = (await runVision(env, AI_MODEL, AI_PROMPT_V2, buf, 24)).raw; }
      catch (e) { return json({ error: "ia", detail: String(e).slice(0, 300) }, 502); }
      const parsed = parseV2(raw);
      const label = parsed.rain === true ? "LLUVIA"
        : parsed.sky === "clear" || parsed.sky === "partly" ? "DESPEJADO"
        : parsed.sky === "overcast" || parsed.sky === "fog" ? "NUBLADO"
        : "NO_SE_VE";
      const t = nowS();
      const cam = String(req.headers.get("X-Cam") || "").slice(0, 80);
      const lat = Number(req.headers.get("X-Lat")), lon = Number(req.headers.get("X-Lon"));
      await env.DB.batch([
        env.DB.prepare("INSERT INTO ia (t, cam, label, raw, lat, lon, img) VALUES (?, ?, ?, ?, ?, ?, ?)")
          .bind(t, cam, label, raw, Number.isFinite(lat) ? lat : null, Number.isFinite(lon) ? lon : null, buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength)),
        env.DB.prepare("INSERT INTO kv (k, v, t) VALUES (?, ?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v, t = excluded.t").bind("ia_" + day, String(count + 1), t),
        env.DB.prepare("DELETE FROM ia WHERE t < ?").bind(t - 7 * 86400)
      ]);
      return json({ label, raw, used: count + 1 });
    }

    if (url.pathname === "/ia/probar" && req.method === "GET") {
      // Prueba de modelos sobre fotos ya guardadas (cupo diario propio, para no quitarle cupo a la tablet).
      if (!env.AI) return json({ error: "falta binding AI" }, 500);
      const model = AI_TEST_MODELS[url.searchParams.get("modelo") || "llama32"];
      if (!model) return json({ error: "modelo", opciones: Object.keys(AI_TEST_MODELS) }, 400);
      const day = "iap_" + new Date().toISOString().slice(0, 10);
      const used = await getRow(env.DB, day);
      const count = used ? Number(used.v) : 0;
      if (count >= AI_TEST_DAILY_CAP) return json({ error: "cupo de prueba", used: count }, 429);
      const row = await env.DB.prepare("SELECT img FROM ia WHERE id = ?").bind(Number(url.searchParams.get("id")) || 0).first();
      if (!row || !row.img) return json({ error: "no existe" }, 404);
      await putRow(env.DB, day, String(count + 1));
      try {
        const out = await runVision(env, model, AI_PROMPT_V2, new Uint8Array(row.img), 24);
        return new Response(JSON.stringify({ ...parseV2(out.raw), raw: out.raw, usage: out.usage, used: count + 1 }), { headers: { ...JSON_HEAD, "Access-Control-Allow-Origin": "*" } });
      } catch (e) {
        return new Response(JSON.stringify({ error: "ia", detail: String(e).slice(0, 300) }), { status: 502, headers: { ...JSON_HEAD, "Access-Control-Allow-Origin": "*" } });
      }
    }

    if (url.pathname === "/ia" && req.method === "GET") {
      const hours = Math.min(168, Math.max(1, Number(url.searchParams.get("horas")) || 24));
      const res = await env.DB.prepare("SELECT id, t, cam, label, raw, lat, lon FROM ia WHERE t >= ? ORDER BY t").bind(nowS() - hours * 3600).all();
      return new Response(JSON.stringify({ rows: res.results || [] }), { headers: { ...JSON_HEAD, "Access-Control-Allow-Origin": "*" } });
    }

    if (url.pathname === "/ia/foto" && req.method === "GET") {
      const row = await env.DB.prepare("SELECT img FROM ia WHERE id = ?").bind(Number(url.searchParams.get("id")) || 0).first();
      if (!row || !row.img) return json({ error: "no existe" }, 404);
      return new Response(new Uint8Array(row.img), { headers: { "Content-Type": "image/jpeg", "Cache-Control": "public, max-age=86400", "Access-Control-Allow-Origin": "*" } });
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
}
