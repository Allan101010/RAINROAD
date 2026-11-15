// Prueba de la lógica de decisión de la ruta (node tests/route_logic.test.js).
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const src = fs.readFileSync(__dirname + "/../assets/app.js", "utf8");
const grab = (start, endMarker) => { const s = src.indexOf(start); return src.slice(s, src.indexOf(endMarker, s)); };
const code = [
  grab("const ROUTE_LEVELS", "];") + "];",
  grab("function routeClock", "\n}\n") + "\n}",
  grab("function assessRoutePoint", "\n}\n") + "\n}",
  grab("function routeVerdict", "\n}\n") + "\n}",
  grab("function nearestHourlyForecast", "\n}\n") + "\n}",
].join("\n");
const ctx = { Math, Date, Number, String };
vm.createContext(ctx); vm.runInContext(code + "\nthis.assess = assessRoutePoint; this.verdict = routeVerdict; this.hourly = nearestHourlyForecast;", ctx);
const eta = new Date("2026-11-15T17:30:00-06:00");
const st = (rainy, dry) => ({ covered: !!(rainy || dry), rainy, dry });
const base = { minutesAway: 10, bolts: 0, station: st(null, null), model: null, forecast: null, eta };
const run = o => ctx.assess({ ...base, ...o });
const fc = (p, mm, code = 3) => ({ probability: p, precipitation: mm, weatherCode: code });

assert.equal(run({}).level, 0, "sin nada = sin datos");
assert.equal(run({ forecast: fc(5, 0) }).level, 1, "pronóstico seco = despejado");
assert.equal(run({ station: st({ name: "Poás", mm: 2.1, km: 4 }) }).level, 3, "estación con lluvia y llegas pronto = lluvia");
assert.equal(run({ station: st({ name: "Poás", mm: 12, km: 4 }) }).level, 4, "lluvia intensa medida = tormenta");
assert.equal(run({ station: st({ name: "Poás", mm: 2, km: 4 }), minutesAway: 50 }).level, 2, "lluvia medida pero llegas en 50 min = posible");
assert.equal(run({ station: st({ name: "Poás", mm: 2, km: 4 }), minutesAway: 120, forecast: fc(5, 0) }).level, 1, "llegas en 2 h: manda el pronóstico");
assert.equal(run({ bolts: 5 }).level, 4, "rayos cerca y llegas pronto = tormenta");
assert.equal(run({ bolts: 5, minutesAway: 200 }).level, 0, "llegada lejana y sin pronóstico: no se afirma nada");
assert.equal(run({ bolts: 5, minutesAway: 200, forecast: fc(5, 0) }).level, 1, "rayos ahora pero llegas en 3 h con pronóstico seco");
assert.equal(run({ station: st(null, { name: "Alajuela", mm: 0, km: 6 }), minutesAway: 120 }).level, 0, "estación seca ahora no garantiza nada en 2 h");
assert.equal(run({ homeCam: true }).level, 3, "la cámara de casa ve lluvia y llegas pronto = lluvia");
assert.equal(run({ homeCam: true, minutesAway: 50 }).level, 2, "cámara con lluvia pero llegas en 50 min = posible");
assert.equal(run({ homeCam: true, minutesAway: 120, forecast: fc(5, 0) }).level, 1, "cámara con lluvia ahora, llegas en 2 h: manda el pronóstico");
assert.equal(run({ model: { rain: true, weak: false } }).level, 3, "solo modelo, sin estaciones = lluvia");
assert.equal(run({ model: { rain: true, weak: false }, station: st(null, { name: "Alajuela", mm: 0, km: 6 }) }).level, 1, "estación cercana seca desmiente al modelo");
assert.equal(run({ forecast: fc(60, 0.3) }).level, 2, "pronóstico 60 % = posible");
assert.equal(run({ forecast: fc(85, 2.5) }).level, 3, "pronóstico fuerte = lluvia");
assert.equal(run({ forecast: fc(60, 0.3, 95) }).level, 3, "tormenta pronosticada = lluvia");
const pts = [{ level: 1, distanceAlongKm: 2, eta }, { level: 3, distanceAlongKm: 14, eta }, { level: 2, distanceAlongKm: 20, eta }];
assert.equal(ctx.verdict(pts).level, 3);
assert.equal(ctx.verdict([{ level: 0, distanceAlongKm: 0, eta }]).level, 0);
assert.equal(ctx.verdict([{ level: 1, distanceAlongKm: 0, eta }]).title, "Ruta despejada");
// La lluvia de cada marca horaria cubre la hora anterior: para llegar a las 5:25 vale la marca de las 6:00.
const hourlyData = { hourly: {
  time: ["2026-11-15T16:00", "2026-11-15T17:00", "2026-11-15T18:00"],
  precipitation_probability: [10, 20, 90], precipitation: [0, 0, 3.5], rain: [0, 0, 3.5], showers: [0, 0, 0],
  weather_code: [1, 2, 63] } };
const at = hhmm => new Date("2026-11-15T" + hhmm + ":00-06:00");
assert.equal(ctx.hourly(hourlyData, at("17:25")).probability, 90, "llegar 5:25 usa el intervalo 5:00-6:00");
assert.equal(ctx.hourly(hourlyData, at("16:40")).probability, 20, "llegar 4:40 usa el intervalo 4:00-5:00");
assert.equal(ctx.hourly(hourlyData, at("17:00")).probability, 20, "llegar a la hora en punto usa la hora que termina ahí");
assert.equal(ctx.hourly(hourlyData, at("23:00")).probability, 90, "fuera del pronóstico usa la última hora");
assert.equal(ctx.hourly({ hourly: { time: ["2026-11-15T17:00", "2026-11-15T18:00"], weather_code: [95, 1] } }, at("17:10")).weatherCode, 95, "tormenta en la marca más cercana");
console.log("route logic OK");
