const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function load(fetchImpl) {
  const window = {};
  vm.runInNewContext(fs.readFileSync("assets/datos.js", "utf8"), { window, fetch: fetchImpl, Date, Promise, Error });
  return window.RainTrackDatos;
}
const iso = minutesAgo => new Date(Date.now() - minutesAgo * 60000).toISOString();
const reply = body => Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
const fail = () => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });

(async () => {
  // Worker fresco: no hace falta mirar GitHub.
  let calls = [];
  let d = load(url => { calls.push(url); return url.includes("/datos/") ? reply({ generated_at: iso(5), from: "worker" }) : reply({ generated_at: iso(1), from: "static" }); });
  assert.strictEqual((await d.newest("camaras", "x.json")).from, "worker");
  assert.strictEqual(calls.length, 1);

  // Worker viejo y GitHub más nuevo: gana GitHub.
  d = load(url => url.includes("/datos/") ? reply({ generated_at: iso(90), from: "worker" }) : reply({ generated_at: iso(10), from: "static" }));
  assert.strictEqual((await d.newest("camaras", "x.json")).from, "static");

  // Worker viejo, GitHub más viejo todavía: gana el Worker.
  d = load(url => url.includes("/datos/") ? reply({ generated_at: iso(40), from: "worker" }) : reply({ generated_at: iso(300), from: "static" }));
  assert.strictEqual((await d.newest("camaras", "x.json")).from, "worker");

  // Sin datos en el Worker: se usa GitHub.
  d = load(url => url.includes("/datos/") ? fail() : reply({ generated_at: iso(3), from: "static" }));
  assert.strictEqual((await d.newest("camaras", "x.json")).from, "static");

  // Nada responde: error.
  d = load(() => fail());
  await assert.rejects(() => d.newest("camaras", "x.json"));
  console.log("datos.test.js ok");
})();
