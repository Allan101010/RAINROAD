// Mezcla de datos en vivo de la tablet con los del bot (node tests/live.test.js).
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const ctx = { document: { addEventListener() {}, getElementById() { return null; } }, window: {}, Date, Math, Number, Map, Array, Object, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname + "/../assets/live.js", "utf8"), ctx);
const { merge, freshness } = ctx.window.RainTrackLive._test;
const now = Date.parse("2026-11-20T19:00:00Z");

const data = {
  stations: [
    { id: "a", image_timestamp: "2026-11-20T18:40:00Z", rain_last_hour_mm: 0, availability_status: "online", image_timestamp_source: "imn_html_table" },
    { id: "b", image_timestamp: "2026-11-20T18:58:00Z", rain_last_hour_mm: 0 }
  ],
  home_cameras: [{ id: "home-casa-patio", t: "2026-11-20T18:50:00Z", estimate: "no_rain", basis: "own_baseline", lat: 10.1, lon: -84.2 }]
};
const live = {
  estaciones: { stations: [
    { id: "a", image_timestamp: "2026-11-20T18:57:00Z", image_timestamp_source: "imn_html_table", rain_last_hour_mm: 2.4, rain_step_mm: 0.8 },
    { id: "b", image_timestamp: "2026-11-20T18:50:00Z", rain_last_hour_mm: 5 },     // más vieja: no se usa
    { id: "zz", image_timestamp: "2026-11-20T18:59:00Z" }                          // desconocida: no se usa
  ] },
  casa: { cams: [{ id: "home-casa-patio", t: "2026-11-20T18:58:00Z", estimate: "unknown", reason: "lamp_on", mode: "lamp" }] }
};
assert.equal(merge(data, live, now), 2);
assert.equal(data.stations[0].rain_last_hour_mm, 2.4);
assert.equal(data.stations[0].rain_observed, true);
assert.equal(data.stations[0].availability_status, "online");
assert.equal(data.stations[0].rain_step_mm, 0.8);
assert.equal(data.stations[1].rain_last_hour_mm, 0, "no se reemplaza con una lectura más vieja");
const cam = data.home_cameras[0];
assert.equal(cam.estimate, "unknown");
assert.equal(cam.reason, "lamp_on");
assert.equal(cam.basis, undefined, "se borran campos de la estimación anterior");
assert.equal(cam.lat, 10.1, "se conserva la ubicación del bot");
assert.equal(merge(data, live, now), 0, "aplicar dos veces no cambia nada");

// Lectura de la tablet demasiado vieja: no se usa
const d2 = { home_cameras: [{ id: "home-casa-patio", t: "2026-11-20T18:00:00Z", estimate: "no_rain" }] };
assert.equal(merge(d2, { casa: { cams: [{ id: "home-casa-patio", t: "2026-11-20T18:30:00Z", estimate: "possible_rain" }] } }, now), 0);
assert.equal(freshness("2026-11-20T18:20:00Z", now).availability_status, "delayed");
assert.equal(freshness(null, now).availability_status, "unknown");
assert.equal(merge(null, live, now), 0);
console.log("live tests ok");
