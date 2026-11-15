// Prueba de la lógica de decisión de la ruta (node tests/route_logic.test.js).
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const src = fs.readFileSync(__dirname + "/../assets/app.js", "utf8");
const grab = (start, endMarker) => { const s = src.indexOf(start); return src.slice(s, src.indexOf(endMarker, s)); };
const code = [
  grab("const ROUTE_LEVELS", "];") + "];",
  grab("function routeClock", "\n}\n") + "\n}",
  grab("function assessRoutePoint", "\n}\n") + "\n}",
  grab("function routeVerdict", "\n}\n") + "\n}",
].join("\n");
const ctx = { Math, Date, Number, String };
vm.createContext(ctx); vm.runInContext(code + "\nthis.assess = assessRoutePoint; this.verdict = routeVerdict;", ctx);
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
assert.equal(run({ bolts: 5, minutesAway: 200 }).level, 1, "rayos pero muy lejos en el tiempo");
assert.equal(run({ model: { rain: true, weak: false } }).level, 3, "solo modelo, sin estaciones = lluvia");
assert.equal(run({ model: { rain: true, weak: false }, station: st(null, { name: "Alajuela", mm: 0, km: 6 }) }).level, 1, "estación cercana seca desmiente al modelo");
assert.equal(run({ forecast: fc(60, 0.3) }).level, 2, "pronóstico 60 % = posible");
assert.equal(run({ forecast: fc(85, 2.5) }).level, 3, "pronóstico fuerte = lluvia");
assert.equal(run({ forecast: fc(60, 0.3, 95) }).level, 3, "tormenta pronosticada = lluvia");
const pts = [{ level: 1, distanceAlongKm: 2, eta }, { level: 3, distanceAlongKm: 14, eta }, { level: 2, distanceAlongKm: 20, eta }];
assert.equal(ctx.verdict(pts).level, 3);
assert.equal(ctx.verdict([{ level: 0, distanceAlongKm: 0, eta }]).level, 0);
assert.equal(ctx.verdict([{ level: 1, distanceAlongKm: 0, eta }]).title, "Ruta despejada");
console.log("route logic OK");
