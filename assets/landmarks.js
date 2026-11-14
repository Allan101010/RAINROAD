/* Vida en el mapa: volcanes de Costa Rica e íconos emblemáticos de provincias y cantones. */
(function () {
  "use strict";
  const OVSICORI = "https://www.ovsicori.una.ac.cr/";
  // st: a = activo (desgasificación/actividad registrada), r = en reposo
  const VOLCANOES = [
    { n: "Volcán Poás", slug: "poas", smoke: "strong", top: [25, 14], kind: "Estratovolcán con cráter y laguna ácida", lat: 10.198, lon: -84.231, alt: "2.708 m", st: "a", t: "Cráter activo con laguna ácida y fumarolas. Parque Nacional Volcán Poás." },
    { n: "Volcán Irazú", slug: "irazu", smoke: "none", top: [24, 14], kind: "Estratovolcán con laguna en el cráter", lat: 9.979, lon: -83.852, alt: "3.432 m", st: "a", t: "El más alto del país. Cráter con laguna verde; desde su cima se ven ambos océanos en días claros." },
    { n: "Volcán Turrialba", slug: "turrialba", smoke: "ash", top: [23.4, 13], kind: "Estratovolcán", lat: 10.019, lon: -83.756, alt: "3.340 m", st: "a", t: "Volcán activo con desgasificación y episodios de ceniza en los últimos años." },
    { n: "Volcán Arenal", slug: "arenal", smoke: "soft", top: [24, 5], kind: "Cono casi perfecto (estratovolcán)", lat: 10.463, lon: -84.703, alt: "1.670 m", st: "r", t: "Cono casi perfecto junto a La Fortuna. En reposo desde 2010, tras décadas de actividad continua." },
    { n: "Volcán Rincón de la Vieja", slug: "rincon", smoke: "soft", top: [26, 12], kind: "Complejo volcánico", lat: 10.83, lon: -85.324, alt: "1.916 m", st: "a", t: "Volcán activo con fumarolas, pailas de barro y aguas termales. Guanacaste." },
    { n: "Volcán Tenorio", slug: "tenorio", smoke: "none", top: [26, 16], kind: "Estratovolcán cubierto de bosque", low: true, lat: 10.673, lon: -85.015, alt: "1.916 m", st: "r", t: "Famoso por el Río Celeste. Parque Nacional Volcán Tenorio." },
    { n: "Volcán Barva", slug: "barva", smoke: "none", top: [24, 19], kind: "Volcán amplio con lagunas en la cima", low: true, lat: 10.135, lon: -84.11, alt: "2.906 m", st: "r", t: "El mayor del Parque Nacional Braulio Carrillo, con bosque nuboso y lagunas." },
    { n: "Volcán Miravalles", slug: "miravalles", smoke: "none", top: [27, 17], kind: "Complejo volcánico con caldera", low: true, lat: 10.717, lon: -85.15, alt: "2.028 m", st: "r", t: "Aprovechado para energía geotérmica. Guanacaste." },
    { n: "Volcán Orosí", slug: "orosi", smoke: "none", top: [27, 14], kind: "Estratovolcán boscoso", low: true, lat: 10.98, lon: -85.47, alt: "1.659 m", st: "r", t: "Parte del Área de Conservación Guanacaste, al norte del país." }
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
  // Un ícono por volcán, dibujado a partir de fotos de referencia de cada uno.
  const tree = (x, y, c = "#2f6b3f") => `<path d="M${x} ${y} l-2 3.6 h4 z" fill="${c}"/>`;
  const grad = (id, a, b) => `<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient>`;
  const ICONS = {
    // Irazú: masa ancha de cumbre achatada, caldera con laguna turquesa, laderas muy verdes.
    irazu: () => `<defs>${grad("gIr", "#58a566", "#2c6a3d")}</defs>
      <path d="M1 41 L10 23 Q14 17.5 19 15.5 Q24 13.5 29 15.5 Q34 17.5 38 23 L47 41 Z" fill="url(#gIr)" stroke="rgba(0,0,0,.3)" stroke-width=".7" stroke-linejoin="round"/>
      <ellipse cx="24" cy="15.4" rx="8" ry="2.9" fill="#3a3f4a"/>
      <ellipse cx="22.2" cy="15.9" rx="3.7" ry="1.5" fill="#4fd1c5"/>
      <ellipse cx="28.2" cy="14.8" rx="2.4" ry=".9" fill="#e8c9a0"/>
      <path d="M41 24 V19 M39.6 20 h2.8" stroke="#cbd5e1" stroke-width=".9" stroke-linecap="round"/>
      ${tree(9, 38)}${tree(15, 36.5)}${tree(34, 36.5)}${tree(39.5, 38)}${tree(24, 38.5)}`,
    // Arenal: cono empinado y simétrico, dorado y ocre con vetas rojizas de lava.
    arenal: () => `<defs>${grad("gAr", "#d9b45a", "#7a5a2e")}</defs>
      <path d="M3 41 L20.6 7 Q24 2.5 27.4 7 L45 41 Z" fill="url(#gAr)" stroke="rgba(0,0,0,.3)" stroke-width=".7" stroke-linejoin="round"/>
      <path d="M22.8 9 L16 38 M25.4 10 L33.5 39 M24 11 L24.5 37 M21 14 L10.5 35" stroke="#8b3a2a" stroke-width="1.5" stroke-linecap="round" opacity=".75"/>
      <path d="M3 41 L9 31 Q24 36 39 31 L45 41 Z" fill="#6f7d3b" opacity=".95"/>
      <path d="M21.2 7.5 Q24 9.6 26.8 7.5" fill="none" stroke="rgba(40,22,14,.6)" stroke-width="1.1" stroke-linecap="round"/>
      ${tree(10, 38.5, "#4d5c2b")}${tree(38, 38.5, "#4d5c2b")}`,
    // Rincón de la Vieja: laderas peladas gris-arena, laguna celeste lechosa, bosque alrededor, varios picos.
    rincon: () => `<defs>${grad("gRi", "#c4b29c", "#6d6459")}${grad("gRiB", "#4d9a5b", "#2c6a3d")}</defs>
      <path d="M1 41 L8 28 L15 22.5 L22 19 L33 16.5 L41 25 L47 41 Z" fill="url(#gRiB)"/>
      <path d="M7 41 L21 14.5 Q24.2 11 28 13 L40 41 Z" fill="url(#gRi)" stroke="rgba(0,0,0,.3)" stroke-width=".7" stroke-linejoin="round"/>
      <path d="M22 18 L16 38 M25.5 18 L28 38 M28 17 L36 38 M20 21 L12 38" stroke="#4a4239" stroke-width="1" stroke-linecap="round" opacity=".55"/>
      <ellipse cx="23.6" cy="14" rx="3.4" ry="1.7" fill="#bfe6f2"/>
      <ellipse cx="29.3" cy="14.8" rx="2.4" ry="1.1" fill="#8a7f73"/>
      <ellipse cx="37" cy="23" rx="2.8" ry=".9" fill="#d9eef6"/>
      ${tree(5, 38.5)}${tree(11, 38)}${tree(37, 38)}${tree(43, 38.5)}`,
    // Poás: cono oscuro y árido, laguna turquesa al borde del cráter, pared en terrazas, laderas en espina de pescado.
    poas: () => `<defs>${grad("gPo", "#6a6e7a", "#23262d")}</defs>
      <path d="M1 41 L12 19.5 Q14 14.3 19 14.3 L30 14.3 Q35 14.3 37 19.5 L47 41 Z" fill="url(#gPo)" stroke="rgba(0,0,0,.4)" stroke-width=".7" stroke-linejoin="round"/>
      <path d="M12.4 19.5 L17 17 L17.6 20.2 L13.6 22.4 Z" fill="#8b909b"/>
      <ellipse cx="25" cy="15.8" rx="6.2" ry="2.4" fill="#5eead4"/>
      <path d="M25 18 L20 38 M25 18 L30 38 M23 21 l-3.5 2.6 M27 21 l3.5 2.6 M22 27 l-4.5 2.8 M28 27 l4.5 2.8 M21 33 l-4 2.5 M29 33 l4 2.5" stroke="#aeb3bf" stroke-width=".9" stroke-linecap="round" opacity=".6"/>
      <path d="M1 41 L4 36.5 Q24 39 44 36.5 L47 41 Z" fill="#3a5a40"/>`,
    // Turrialba: cresta con varios cráteres y lagunas, laderas rojizas por la ceniza, cráter activo oscuro.
    turrialba: () => `<defs>${grad("gTu", "#c4753f", "#5a3a2a")}</defs>
      <path d="M1 41 L8 26.5 L14 21.5 L19 16.5 L23.5 13.2 L28.5 13.8 L33.5 17.5 Q40.5 21.5 47 41 Z" fill="url(#gTu)" stroke="rgba(0,0,0,.35)" stroke-width=".7" stroke-linejoin="round"/>
      <ellipse cx="23.4" cy="14.8" rx="6.6" ry="2.5" fill="#1f2229"/>
      <ellipse cx="20.8" cy="16.6" rx="2.4" ry="1" fill="#5fd6e0"/>
      <ellipse cx="26.8" cy="16" rx="1.6" ry=".7" fill="#5fd6e0"/>
      <ellipse cx="19" cy="22.6" rx="3.2" ry="1.4" fill="#4fc3d9"/>
      <path d="M1 41 L6 34 Q24 38 42 34 L47 41 Z" fill="#6a4a2c" opacity=".9"/>
      ${tree(8, 38.5, "#5b4a2a")}${tree(14, 37, "#6a5030")}${tree(35, 37, "#6a5030")}${tree(41, 38.5, "#5b4a2a")}`,
    // Tenorio: lomas verdes y suaves cubiertas de bosque, lagunita clara entre las cimas, un camino.
    tenorio: () => `<defs>${grad("gTe", "#86c874", "#2f6b3f")}</defs>
      <path d="M1 41 Q6 28 14 24 Q18 20.5 22 21.5 Q26 15 31 17 Q36 19 40 25 Q45 32 47 41 Z" fill="url(#gTe)" stroke="rgba(0,0,0,.28)" stroke-width=".7" stroke-linejoin="round"/>
      <ellipse cx="21.8" cy="24.6" rx="2.3" ry=".9" fill="#d3eef7"/>
      <path d="M8 38 Q12 31 17 27.5" fill="none" stroke="#e0c595" stroke-width=".9" stroke-linecap="round" stroke-dasharray="2 1.4"/>
      <path d="M27 21 Q30 24 35 26 M14 32 Q20 30 25 33" stroke="#a8dd8c" stroke-width="1" fill="none" opacity=".6" stroke-linecap="round"/>`,
    // Barva: domo de selva oscura con cumbres bajas y una laguna casi negra.
    barva: () => `<defs>${grad("gBa", "#3b7a4a", "#14391f")}</defs>
      <path d="M1 41 Q5 26 14 21.5 Q19 18.5 24 19.5 Q31 16.5 37 22 Q44 28 47 41 Z" fill="url(#gBa)" stroke="rgba(0,0,0,.35)" stroke-width=".7" stroke-linejoin="round"/>
      <ellipse cx="21" cy="28.6" rx="4.8" ry="2.1" fill="#0d1424"/>
      <ellipse cx="19.8" cy="28" rx="2" ry=".6" fill="#33456b" opacity=".8"/>
      ${[[12, 30], [30, 27], [35, 33], [9, 36], [26, 36], [40, 37], [16, 24], [31, 21]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="2.1" fill="#4f9a5c" opacity=".7"/>`).join("")}`,
    // Miravalles: loma ancha de cimas suaves; un lado seco y dorado, el otro de bosque oscuro.
    miravalles: () => `<defs>${grad("gMi", "#4b8a55", "#1f4d2c")}</defs>
      <path d="M1 41 L7 31 Q14 25 20 20.5 Q23 15.8 27 17.2 Q30 15.8 33.5 20 Q40 27 47 41 Z" fill="url(#gMi)" stroke="rgba(0,0,0,.3)" stroke-width=".7" stroke-linejoin="round"/>
      <path d="M1 41 L7 31 Q14 25 20 20.5 L25.5 25 L22 41 Z" fill="#cfa84e" opacity=".96"/>
      <ellipse cx="15" cy="29.5" rx="2.6" ry="1.3" fill="#c97a3a"/>
      ${tree(30, 36, "#1b4226")}${tree(37, 37.5, "#1b4226")}${tree(6, 39, "#5d7a35")}${tree(43, 39, "#1b4226")}`,
    // Orosí: cono ancho verde azulado, lado derecho largo y tendido, quebradas en las laderas, potreros al pie.
    orosi: () => `<defs>${grad("gOr", "#52967f", "#24574a")}</defs>
      <path d="M1 41 Q10 36 18 24 Q22 15.5 27 14.2 Q31 14.8 34 19 Q42 29 47 41 Z" fill="url(#gOr)" stroke="rgba(0,0,0,.3)" stroke-width=".7" stroke-linejoin="round"/>
      <path d="M27 16 L24 38 M29 17 L31.5 38 M25.5 20 L19 36 M31 21 L38 37" stroke="#1d4639" stroke-width="1" stroke-linecap="round" opacity=".6"/>
      <path d="M1 41 L5 38 Q24 40.5 43 38 L47 41 Z" fill="#8cc152"/>
      ${tree(12, 38.6, "#2d6a3c")}${tree(36, 38.6, "#2d6a3c")}`
  };
  function volcanoSvg(slug) {
    const draw = ICONS[slug] || ICONS.irazu;
    return `<svg viewBox="0 0 48 44" aria-hidden="true"><ellipse cx="24" cy="42" rx="22" ry="2.4" fill="rgba(0,0,0,.28)"/>${draw()}</svg>`;
  }

  const key = "raintrack-landmarks";
  let markers = [];
  const read = (k, d) => { try { const v = localStorage.getItem(key + "-" + k); return v === null ? d : v === "1"; } catch (e) { return d; } };
  const write = (k, v) => { try { localStorage.setItem(key + "-" + k, v ? "1" : "0"); } catch (e) {} };

  function clear() { markers.forEach(m => m.remove()); markers = []; }
  // Fotos de lugares icónicos: Wikimedia Commons (licencia libre; cada foto enlaza a su página con autor y licencia).
  const PHOTOS = {
    "Teatro Nacional": {
      "f": "Costa Rica-Teatro Nacional.JPG",
      "a": "Andres Alvarez"
    },
    "Alajuela, Ciudad de los Mangos": {
      "f": "Juan Santamaria 1.JPG",
      "a": "Erick Chavarría"
    },
    "Basílica de Nuestra Señora de los Ángeles": {
      "f": "Basilica of Our Lady of the Angels, Cartago 01.jpg",
      "a": "Bernard Gagnon"
    },
    "El Fortín y el café de Heredia": {
      "f": "El Fortín de Heredia.JPG",
      "a": "Lex.mercurio"
    },
    "Liberia, la Ciudad Blanca": {
      "f": "Liberia (Costa Rica).jpg",
      "a": "Tizianok"
    },
    "Puerto de Puntarenas": {
      "f": "Muelle de Puntarenas.jpg",
      "a": "Steven Depolo"
    },
    "Parque Vargas, Limón": {
      "f": "Parque Vargas. Limón. Costa Rica.jpg",
      "a": "Roger"
    },
    "Sarchí y la carreta pintada": {
      "f": "Carreta tipica Sarchi (1).JPG",
      "a": "Axxis10"
    },
    "Jardín de arbustos de Zarcero": {
      "f": "ZARCERO TOPIARY GARDEN, COSTA RICA.jpg",
      "a": "Jerrye y Roy Klotz"
    },
    "Monteverde": {
      "f": "Monteverde Cloud Forest 01.jpg",
      "a": "Cephas"
    },
    "Tortuguero": {
      "f": "Tortuguero Nationalpark.jpg",
      "a": "Leyo"
    },
    "Manuel Antonio": {
      "f": "Parque Nacional Manuel Antonio 02.jpg",
      "a": "Bernard Gagnon"
    },
    "Jacó": {
      "f": "Beach, Jaco.JPG",
      "a": "Milei.vencel"
    },
    "Tamarindo": {
      "f": "Tamarindo beach-Guanacaste-Costa Rica.jpg",
      "a": "Jarle Naustvik"
    },
    "Cahuita": {
      "f": "Cahuita national park, Costa Rica.jpg",
      "a": "Haakon S. Krohn"
    },
    "Península de Osa y Corcovado": {
      "f": "Corcovado National Park, Costa RIca 02.jpg",
      "a": "Bernard Gagnon"
    },
    "Cerro Chirripó": {
      "f": "Chirripo.jpg",
      "a": "Peter Andersen"
    },
    "Valle de Orosi": {
      "f": "Vista del Valle de Orosi.jpg",
      "a": "André Oliva"
    },
    "Isla del Coco": {
      "f": "CocosIslandCostaRica.jpg",
      "a": "Shannon Rankin, NOAA"
    },
    "Nicoya y su iglesia de San Blas": {
      "f": "Fachada Iglesia Colonial Nicoya Museo Nacional CRI 01 2020 4152.jpg",
      "a": "Mariordo"
    }
  };
  function photoHtml(name) {
    const ph = PHOTOS[name];
    if (!ph) return "";
    const file = encodeURIComponent(ph.f.replace(/ /g, "_"));
    return `<figure class="lm-photo"><img class="vol-photo" src="https://commons.wikimedia.org/wiki/Special:FilePath/${file}?width=720" alt="${esc(name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('figure').remove()"><figcaption>Foto: ${esc(ph.a)} · <a href="https://commons.wikimedia.org/wiki/File:${file}" target="_blank" rel="noopener">Wikimedia Commons ↗</a></figcaption></figure>`;
  }
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
        el.className = "landmark volcano " + (v.st === "a" ? "active" : "rest") + " smoke-" + v.smoke + (v.low ? " low-hide" : "");
        const puffs = { none: 0, soft: 2, strong: 3, ash: 3 }[v.smoke] || 0;
        el.innerHTML = `<span class="vol-icon">${volcanoSvg(v.slug)}</span>` +
          Array.from({ length: puffs }, (_, i) => `<i class="vol-smoke s${i + 1} ${v.smoke}"></i>`).join("");
        el.style.setProperty("--top-x", v.top[0] / 48 * 100 + "%");
        el.style.setProperty("--top-y", v.top[1] / 44 * 100 + "%");
        el.setAttribute("aria-label", v.n);
        add(el, v.lon, v.lat, {
          eyebrow: "VOLCÁN",
          title: v.n,
          subtitle: v.kind + " · " + v.alt + " · " + (v.st === "a" ? "Volcán activo" : "Sin actividad eruptiva reciente"),
          content: `<div class="camera-popup"><img class="vol-photo" src="assets/volcanes/${v.slug}.jpg" alt="${esc(v.n)}" loading="lazy"><div class="camera-popup-status">${esc(v.t)}</div>
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
          content: `<div class="camera-popup">${photoHtml(l.n)}<div class="camera-popup-status">${esc(l.t)}</div></div>`
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
