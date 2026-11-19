// Capa de aviones: lectura de datos ADS-B, radio del área y colores (node tests/aircraft.test.js).
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const ctx = { document: { addEventListener() {}, getElementById() { return null; } }, window: {}, Date, Math, Number, String, Array, Set, Map, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname + "/../assets/aircraft.js", "utf8"), ctx);
const t = ctx.window.RainTrackAircraft._test;

// Datos de ejemplo con la forma de airplanes.live / adsb.lol
const planes = t.parsePlanes({ ac: [
  { hex: "A1B2C3", flight: "AVA123  ", r: "N123AV", t: "A320", lat: 10.0, lon: -84.2, alt_baro: 12000, gs: 250, track: 90, baro_rate: -800, squawk: "1234", seen_pos: 2 },
  { hex: "~abcdef", lat: 10.1, lon: -84.1, alt_baro: "ground", gs: 5, seen_pos: 1 },
  { hex: "zzz", lat: null, lon: -84.1, alt_baro: 3000 },              // sin posición: se ignora
  { hex: "old", lat: 10, lon: -84, alt_baro: 3000, seen_pos: 300 },   // posición vieja: se ignora
  { lat: 10, lon: -84 }                                                // sin código: se ignora
] });
assert.equal(planes.length, 2, "solo los aviones con posición reciente");
assert.equal(planes[0].hex, "a1b2c3");
assert.equal(planes[0].call, "AVA123", "se limpia el indicativo");
assert.equal(planes[0].altFt, 12000);
assert.equal(planes[0].track, 90);
assert.ok(planes[1].onGround && planes[1].altFt === 0, "en tierra");
assert.equal(planes[1].hex, "abcdef", "se quita el ~ de códigos sin dueño");
assert.deepEqual(t.parsePlanes(null), []);
assert.deepEqual(t.parsePlanes({ ac: "x" }), []);

// Conversiones
assert.equal(t.ftToM(10000), 3048);
assert.equal(t.ktToKmh(100), 185);

// Radio del área visible: acotado entre 15 y 250 millas náuticas
assert.equal(t.radiusNm(9.99, -84.01, 10.01, -83.99), 15, "área pequeña = mínimo");
assert.equal(t.radiusNm(-20, -120, 40, -40), 250, "área enorme = máximo de las APIs");
const mid = t.radiusNm(9.0, -85.0, 11.0, -83.0);
assert.ok(mid > 70 && mid < 100, "área de 2° x 2° (~157 km de centro a esquina) = " + mid + " nm");

// Colores y avisos
assert.equal(t.altitudeColor({ onGround: true }), "#94a3b8");
assert.equal(t.altitudeColor({ onGround: false, altFt: 5000 }), "#fbbf24");
assert.equal(t.altitudeColor({ onGround: false, altFt: 35000 }), "#a78bfa");
assert.equal(t.squawkNote("7700"), "Emergencia general");
assert.equal(t.squawkNote("1200"), "");

// Aeropuertos dentro de Costa Rica
assert.ok(t.AIRPORTS.length >= 2);
t.AIRPORTS.forEach(a => assert.ok(a.lat > 8 && a.lat < 11.5 && a.lon > -86 && a.lon < -82.5, a.icao + " en Costa Rica"));
assert.ok(t.PROVIDERS.every(p => /^https:\/\//.test(p.url(10, -84, 50))), "todas las fuentes usan https");
console.log("aircraft tests ok");
