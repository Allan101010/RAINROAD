// Intermediario de aviones para RainTrack CR (Cloudflare Worker, plan gratis).
// Solo reenvía consultas de aviones cerca de un punto. Ejemplo: /?lat=9.93&lon=-84.08&r=80
const ORIGIN = "https://allan101010.github.io";
const CORS = { "Access-Control-Allow-Origin": ORIGIN, "Access-Control-Allow-Methods": "GET", "Access-Control-Expose-Headers": "X-Source", "Vary": "Origin" };

export default {
  async fetch(req) {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const q = new URL(req.url).searchParams;
    const lat = Number(q.get("lat")), lon = Number(q.get("lon")), r = Math.round(Number(q.get("r")));
    if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 && r >= 1 && r <= 250)) {
      return new Response('{"error":"parametros"}', { status: 400, headers: { ...CORS, "Content-Type": "application/json" } });
    }
    const sources = [
      `https://api.airplanes.live/v2/point/${lat}/${lon}/${r}`,
      `https://api.adsb.lol/v2/point/${lat}/${lon}/${r}`
    ];
    for (const url of sources) {
      try {
        const res = await fetch(url, { cf: { cacheTtl: 5, cacheEverything: true }, headers: { "User-Agent": "RainTrackCR (uso personal)" } });
        if (res.ok) {
          return new Response(res.body, { headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "public, max-age=5", "X-Source": new URL(url).hostname } });
        }
      } catch (e) { /* se prueba la siguiente fuente */ }
    }
    return new Response('{"error":"sin respuesta"}', { status: 502, headers: { ...CORS, "Content-Type": "application/json" } });
  }
};
