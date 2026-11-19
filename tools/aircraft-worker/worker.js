// Intermediario de aviones para RainTrack CR (Cloudflare Worker, plan gratis).
// Consulta tres redes abiertas y devuelve la que vea más aviones. Ejemplo: /?lat=9.93&lon=-84.08&r=80  (&debug=1 muestra cada fuente)
const ORIGIN = "https://allan101010.github.io";
const CORS = { "Access-Control-Allow-Origin": ORIGIN, "Access-Control-Allow-Methods": "GET", "Access-Control-Expose-Headers": "X-Source", "Vary": "Origin" };
const JSON_HEAD = { ...CORS, "Content-Type": "application/json" };

export default {
  async fetch(req) {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const q = new URL(req.url).searchParams;
    const lat = Number(q.get("lat")), lon = Number(q.get("lon")), r = Math.round(Number(q.get("r")));
    if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 && r >= 1 && r <= 250)) {
      return new Response('{"error":"parametros"}', { status: 400, headers: JSON_HEAD });
    }
    const sources = {
      "airplanes.live": `https://api.airplanes.live/v2/point/${lat}/${lon}/${r}`,
      "adsb.fi": `https://opendata.adsb.fi/api/v2/lat/${lat}/lon/${lon}/dist/${r}`,
      "adsb.lol": `https://api.adsb.lol/v2/point/${lat}/${lon}/${r}`
    };
    const results = await Promise.all(Object.entries(sources).map(async ([name, url]) => {
      try {
        const res = await fetch(url, { cf: { cacheTtl: 5, cacheEverything: true }, headers: { "User-Agent": "RainTrackCR/1.0 (uso personal)", "Accept": "application/json" } });
        if (!res.ok) return { name, status: res.status, n: -1 };
        const data = await res.json();
        const list = data.ac || data.aircraft || [];
        return { name, status: res.status, n: list.length, data: { ac: list, now: data.now } };
      } catch (e) { return { name, status: 0, n: -1, error: String(e) }; }
    }));
    if (q.get("debug")) {
      return new Response(JSON.stringify(results.map(({ name, status, n, error }) => ({ name, status, n, error }))), { headers: JSON_HEAD });
    }
    const best = results.filter(x => x.n >= 0).sort((a, b) => b.n - a.n)[0];
    if (!best) return new Response('{"error":"sin respuesta"}', { status: 502, headers: JSON_HEAD });
    return new Response(JSON.stringify(best.data), { headers: { ...JSON_HEAD, "Cache-Control": "public, max-age=5", "X-Source": best.name } });
  }
};
