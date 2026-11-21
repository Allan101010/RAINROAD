// Service worker mínimo: la app siempre intenta la red primero para que cada
// actualización publicada llegue sola; sin conexión usa la última copia guardada.
const CACHE = "raintrackcr-shell-v4";
const SHELL = ["./", "index.html", "assets/app.js", "assets/ambient.js", "assets/landmarks.js", "assets/ratelayer.js", "assets/lightning.js", "assets/quakes.js", "assets/aircraft.js", "assets/live.js", "assets/styles.css", "manifest.webmanifest"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  // Se guarda UNA copia por archivo, sin ?v= ni ?rt=. Con la dirección completa se acumulaba una
  // copia nueva de camera-alerts.json (~270 KB) cada 2 minutos y nunca se borraba.
  const key = url.origin + url.pathname;
  event.respondWith(
    fetch(request, { cache: "no-cache" })
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(key, copy)).catch(() => {});
        }
        return response;
      })
      .catch(() => caches.match(key).then(hit =>
        hit || (request.mode === "navigate" ? caches.match("index.html") : Response.error())))
  );
});
