// Si la cámara de casa ve lluvia, la capa de lluvia dibuja una zona de varios km (node tests/home_rain_layer.test.js).
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const load = (summary, stations = []) => {
  const ctx = {
    document: { addEventListener() {} }, performance: { now: () => 0 }, Date, Math, Number, window: {},
    cameraMonitorData: { generated_at: new Date().toISOString(), stations },
    homeCameraSummary: () => summary,
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(__dirname + "/../assets/ratelayer.js", "utf8"), ctx);
  ctx.window.RainTrackOwnRain.rebuild();
  return ctx.window.RainTrackOwnRain;
};
const row = (estimate, extra = {}) => ({ id: "home-casa", lat: 10.1, lon: -84.26, estimate, ...extra });
let api = load({ estimate: "possible_rain", rows: [row("possible_rain")] });
assert.ok(api.homeRain(), "cámara con lluvia = zona de lluvia en casa");
assert.equal(api.cellCount(), 0, "no cuenta como estación");
api = load({ estimate: "no_rain", rows: [row("no_rain")] });
assert.ok(!api.homeRain(), "sin lluvia = nada");
api = load({ estimate: "possible_rain", rows: [row("possible_rain", { stale: true })] });
assert.ok(!api.homeRain(), "cámara sin conexión no dibuja lluvia");
// rainAt: ¿un punto cae dentro de una zona de lluvia medida? (lo usa el resumen de arriba)
const station = (mm, age, extra = {}) => ({ id: "imn-x", lat: 10.0, lon: -84.0, rain_last_hour_mm: mm, image_age_minutes: age, availability_status: "online", ...extra });
api = load({ estimate: "unknown", rows: [] }, [station(2, 5)]);
assert.ok(api.rainAt(10.0, -84.0), "encima de la estación con lluvia");
assert.ok(api.rainAt(10.04, -84.0), "a ~4,4 km de 2 mm/h (radio 5,9 km) = dentro");
assert.equal(api.rainAt(10.2, -84.0), null, "a ~22 km = fuera");
api = load({ estimate: "unknown", rows: [] }, [station(0.2, 5)]);
assert.equal(api.rainAt(10.04, -84.0), null, "la llovizna solo cuenta a 3,5 km");
api = load({ estimate: "unknown", rows: [] }, [station(2, 50)]);
assert.equal(api.rainAt(10.0, -84.0), null, "lluvia de hace 50 min ya no cuenta como 'ahora'");
api = load({ estimate: "unknown", rows: [] }, [station(2, 5, { availability_status: "offline" })]);
assert.equal(api.rainAt(10.0, -84.0), null, "estación caída no cuenta");
console.log("home rain layer OK");

// Lluvia clara ("rain") también pinta lluvia, más intensa que "posible lluvia"
api = load({ estimate: "rain", rows: [row("rain")] });
assert.ok(api.homeRain(), "lluvia clara cuenta como lluvia");
console.log("home rain clear-rain ok");
