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
console.log("home rain layer OK");
