/* Vida en el mapa: volcanes de Costa Rica e íconos emblemáticos de provincias y cantones. */
(function () {
  "use strict";
  const OVSICORI = "https://www.ovsicori.una.ac.cr/";
  // st: a = activo (desgasificación/actividad registrada), r = en reposo
  const VOLCANOES = [
    { n: "Volcán Poás", lat: 10.198, lon: -84.231, alt: "2.708 m", st: "a", t: "Cráter activo con laguna ácida y fumarolas. Parque Nacional Volcán Poás." },
    { n: "Volcán Irazú", lat: 9.979, lon: -83.852, alt: "3.432 m", st: "a", t: "El más alto del país. Cráter con laguna verde; desde su cima se ven ambos océanos en días claros." },
    { n: "Volcán Turrialba", lat: 10.019, lon: -83.756, alt: "3.340 m", st: "a", t: "Volcán activo con desgasificación y episodios de ceniza en los últimos años." },
    { n: "Volcán Arenal", lat: 10.463, lon: -84.703, alt: "1.670 m", st: "r", t: "Cono casi perfecto junto a La Fortuna. En reposo desde 2010, tras décadas de actividad continua." },
    { n: "Volcán Rincón de la Vieja", lat: 10.83, lon: -85.324, alt: "1.916 m", st: "a", t: "Volcán activo con fumarolas, pailas de barro y aguas termales. Guanacaste." },
    { n: "Volcán Tenorio", low: true, lat: 10.673, lon: -85.015, alt: "1.916 m", st: "r", t: "Famoso por el Río Celeste. Parque Nacional Volcán Tenorio." },
    { n: "Volcán Barva", low: true, lat: 10.135, lon: -84.11, alt: "2.906 m", st: "r", t: "El mayor del Parque Nacional Braulio Carrillo, con bosque nuboso y lagunas." },
    { n: "Volcán Miravalles", low: true, lat: 10.717, lon: -85.15, alt: "2.028 m", st: "r", t: "Aprovechado para energía geotérmica. Guanacaste." },
    { n: "Volcán Orosí", low: true, lat: 10.98, lon: -85.47, alt: "1.659 m", st: "r", t: "Parte del Área de Conservación Guanacaste, al norte del país." }
  ];
  // major: provincia (siempre visible); lo demás aparece al acercar el mapa
  const LANDMARKS = [
    { e: "🎭", n: "Teatro Nacional", p: "San José", lat: 9.9337, lon: -84.0772, major: true, t: "Joya neoclásica de 1897 en el centro de San José." },
    { e: "🥭", n: "Alajuela, Ciudad de los Mangos", low: true, p: "Alajuela", lat: 10.0162, lon: -84.214, major: true, t: "Cuna de Juan Santamaría, héroe nacional, y famosa por sus mangos." },
    { e: "⛪", n: "Basílica de Nuestra Señora de los Ángeles", low: true, p: "Cartago", lat: 9.8644, lon: -83.9192, major: true, t: "Santuario de la patrona de Costa Rica; cada 2 de agosto llega la romería." },
    { e: "☕", n: "El Fortín y el café de Heredia", low: true, p: "Heredia", lat: 9.9985, lon: -84.1166, major: true, t: "La ciudad de las flores, con su Fortín y una larga tradición cafetalera." },
    { e: "🌳", n: "Liberia, la Ciudad Blanca", p: "Guanacaste", lat: 10.6347, lon: -85.4377, major: true, t: "Capital de Guanacaste, tierra de sabana, sabaneros y del árbol nacional." },
    { e: "⚓", n: "Puerto de Puntarenas", p: "Puntarenas", lat: 9.9763, lon: -84.8384, major: true, t: "El puerto histórico del Pacífico, con su paseo de los turistas." },
    { e: "🌴", n: "Parque Vargas, Limón", p: "Limón", lat: 9.9915, lon: -83.0258, major: true, t: "Corazón del Caribe costarricense y de su Carnaval." },
    { e: "🛺", n: "Sarchí y la carreta pintada", p: "Alajuela · Sarchí", lat: 10.0867, lon: -84.3447, t: "Cuna de la carreta típica, Patrimonio Cultural Inmaterial de la Humanidad." },
    { e: "🌿", n: "Jardín de arbustos de Zarcero", p: "Alajuela · Zarcero", lat: 10.186, lon: -84.39, t: "Famoso parque con arbustos esculpidos frente a su iglesia." },
    { e: "🦋", n: "Monteverde", p: "Puntarenas · Monteverde", lat: 10.3009, lon: -84.825, t: "Bosque nuboso con una de las mayores diversidades de aves y mariposas." },
    { e: "🐢", n: "Tortuguero", p: "Limón · Pococí", lat: 10.542, lon: -83.502, t: "Playa de anidación de tortugas verdes y red de canales." },
    { e: "🐒", n: "Manuel Antonio", p: "Puntarenas · Quepos", lat: 9.392, lon: -84.14, t: "Parque nacional de playas y monos entre bosque y mar." },
    { e: "🏄", n: "Jacó", p: "Puntarenas · Garabito", lat: 9.614, lon: -84.629, t: "Destino de surf del Pacífico central." },
    { e: "🏖️", n: "Tamarindo", p: "Guanacaste · Santa Cruz", lat: 10.3, lon: -85.841, t: "Playa y surf en la costa de Guanacaste." },
    { e: "🦥", n: "Cahuita", p: "Limón · Talamanca", lat: 9.735, lon: -82.84, t: "Parque nacional con arrecife de coral y perezosos." },
    { e: "🦜", n: "Península de Osa y Corcovado", p: "Puntarenas · Osa", lat: 8.54, lon: -83.59, t: "Selva tropical considerada de las más biodiversas del planeta." },
    { e: "⛰️", n: "Cerro Chirripó", p: "San José · Pérez Zeledón", lat: 9.4844, lon: -83.489, t: "La cima más alta del país, a 3.820 m." },
    { e: "💧", n: "Valle de Orosi", p: "Cartago · Paraíso", lat: 9.793, lon: -83.857, t: "Valle de cafetales con el templo colonial más antiguo del país." },
    { e: "🪸", n: "Isla del Coco", p: "Puntarenas", lat: 5.53, lon: -87.06, t: "Parque nacional marino y Patrimonio de la Humanidad, a 550 km de la costa." },
    { e: "🥁", n: "Nicoya y su iglesia de San Blas", p: "Guanacaste · Nicoya", lat: 10.1504, lon: -85.4509, t: "Una de las ciudades más antiguas del país, con iglesia colonial y herencia de marimba y tradición guanacasteca." }
  ];
  const key = "raintrack-landmarks";
  let markers = [];
  const read = (k, d) => { try { const v = localStorage.getItem(key + "-" + k); return v === null ? d : v === "1"; } catch (e) { return d; } };
  const write = (k, v) => { try { localStorage.setItem(key + "-" + k, v ? "1" : "0"); } catch (e) {} };

  function clear() { markers.forEach(m => m.remove()); markers = []; }
  function esc(s) { return typeof escapeHtml === "function" ? escapeHtml(s) : String(s); }

  function add(el, lon, lat, detail) {
    const marker = new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat([lon, lat]).addTo(map);
    el.addEventListener("click", () => showMapDetail(Object.assign({ markerElement: el }, detail)));
    markers.push(marker);
  }

  function render() {
    if (typeof map === "undefined" || !map || !mapReady) return;
    clear();
    if (document.getElementById("volcanoToggle").checked) {
      VOLCANOES.forEach(v => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "landmark volcano " + (v.st === "a" ? "active" : "rest") + (v.low ? " low-hide" : "");
        el.innerHTML = `<span class="vol-icon">🌋</span>${v.st === "a" ? '<i class="vol-smoke"></i>' : ""}`;
        el.setAttribute("aria-label", v.n);
        add(el, v.lon, v.lat, {
          eyebrow: "VOLCÁN",
          title: v.n,
          subtitle: v.alt + " · " + (v.st === "a" ? "Volcán activo" : "Sin actividad eruptiva reciente"),
          content: `<div class="camera-popup"><div class="camera-popup-status">${esc(v.t)}</div>
            <div class="camera-popup-links"><a class="camera-popup-link" href="${OVSICORI}" target="_blank" rel="noopener">Estado en vivo en OVSICORI ↗</a></div>
            <p class="layer-hint">Clasificación general; no es un reporte en tiempo real. Consulte siempre a OVSICORI y a la CNE.</p></div>`
        });
      });
    }
    if (document.getElementById("landmarkToggle").checked) {
      LANDMARKS.forEach(l => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "landmark emblem" + (l.major ? " major" : " minor") + (l.low ? " low-hide" : "");
        el.textContent = l.e;
        el.setAttribute("aria-label", l.n);
        add(el, l.lon, l.lat, {
          eyebrow: l.major ? "ÍCONO DE LA PROVINCIA" : "ÍCONO DE COSTA RICA",
          title: l.n,
          subtitle: l.p,
          content: `<div class="camera-popup"><div class="camera-popup-status">${esc(l.t)}</div></div>`
        });
      });
    }
    syncZoom();
  }

  function syncZoom() {
    if (typeof map === "undefined" || !map) return;
    document.getElementById("map").classList.toggle("zoom-low", map.getZoom() < 8.2);
  }

  function init() {
    const v = document.getElementById("volcanoToggle"), l = document.getElementById("landmarkToggle");
    if (!v || !l) return;
    v.checked = read("volcano", true);
    l.checked = read("emblem", true);
    v.addEventListener("change", () => { write("volcano", v.checked); render(); });
    l.addEventListener("change", () => { write("emblem", l.checked); render(); });
    const wait = setInterval(() => {
      if (typeof map !== "undefined" && map && mapReady) {
        clearInterval(wait);
        map.on("zoom", syncZoom);
        render();
      }
    }, 400);
  }
  window.renderLandmarks = render;
  document.addEventListener("DOMContentLoaded", init);
})();
