// OpenStreetMap maps (D-025). Leaflet 1.9.4 (web/vendor/leaflet, BSD-2-Clause) + OpenStreetMap tiles from the internet.
// Use: const m = await osmMap(svgElement); if (m) m.draw(points) — points = [{lat, lon, r, kind, title, html, id}].
// No internet (the tile test fails within 4 s) → osmMap returns null and the page keeps its drawn outline map.
const TILE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';
const CAMEROON = [[1.6, 8.4], [13.1, 16.2]];
let ready = null;

function loadLeaflet() {
  if (window.L) return Promise.resolve(true);
  return new Promise((resolve) => {
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = "vendor/leaflet/leaflet.css";
    document.head.appendChild(css);
    const s = document.createElement("script");
    s.src = "vendor/leaflet/leaflet.js";
    s.onload = () => resolve(!!window.L);
    s.onerror = () => resolve(false);
    document.head.appendChild(s);
  });
}

function tilesReachable() {
  return new Promise((resolve) => {
    const img = new Image();
    const done = (ok) => { clearTimeout(t); img.onload = img.onerror = null; resolve(ok); };
    const t = setTimeout(() => done(false), 4000);
    img.onload = () => done(true);
    img.onerror = () => done(false);
    img.src = TILE.replace("{z}", "5").replace("{x}", "17").replace("{y}", "15") + `?probe=${Date.now() % 100000}`;
  });
}

export function osmAvailable() {
  if (new URLSearchParams(location.search).get("map") === "outline") return Promise.resolve(false);  // force the fallback
  if (!ready) ready = Promise.all([tilesReachable(), loadLeaflet()]).then(([a, b]) => a && b);
  return ready;
}

const COLOURS = { live: "#0071e3", on: "#1a9f4b", off: "#8e8e93", hit: "#0071e3", other: "#c7c7cc" };

// Replace `svg` (kept in the page, hidden) by a Leaflet map of the same size; returns {map, draw, pulse} or null.
export async function osmMap(svg, { height } = {}) {
  if (!svg || !(await osmAvailable())) return null;
  if (svg._osm) return svg._osm;
  const box = document.createElement("div");
  box.className = "osm-map";
  box.style.height = height || `${Math.max(260, svg.getBoundingClientRect().height || 340)}px`;
  svg.after(box);
  svg.style.display = "none";
  const L = window.L;
  const map = L.map(box, { scrollWheelZoom: false, zoomSnap: 0.5, attributionControl: true, minZoom: 5, maxZoom: 17 });
  L.tileLayer(TILE, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(map);
  map.fitBounds(CAMEROON);
  const layer = L.layerGroup().addTo(map);
  const byId = new Map();
  let fitted = false;
  const handle = {
    map,
    draw(points, { fit = !fitted } = {}) {
      layer.clearLayers(); byId.clear();
      for (const p of points) {
        if (p.lat == null || p.lon == null) continue;
        const colour = p.colour || COLOURS[p.kind] || COLOURS.on;
        const m = L.circleMarker([p.lat, p.lon], { radius: p.r || 7, color: "#fff", weight: 1.5, fillColor: colour,
          fillOpacity: p.kind === "off" || p.kind === "other" ? 0.55 : 0.85 });
        if (p.html) m.bindPopup(p.html); else if (p.title) m.bindTooltip(p.title);
        if (p.title && p.html) m.bindTooltip(p.title);
        m.addTo(layer);
        if (p.id) byId.set(p.id, m);
      }
      const pts = points.filter((p) => p.lat != null && p.lon != null).map((p) => [p.lat, p.lon]);
      if (fit && pts.length) { map.fitBounds(pts.length > 1 ? pts : [pts[0], pts[0]], { padding: [28, 28], maxZoom: 13 }); fitted = true; }
    },
    pulse(id) {   // a play just happened at this bar: a ring grows and fades around its dot
      const m = byId.get(id);
      if (!m) return;
      const ring = L.circleMarker(m.getLatLng(), { radius: m.options.radius, color: COLOURS.live, weight: 3, fill: false, opacity: 0.9 }).addTo(map);
      let r = m.options.radius, o = 0.9;
      const t = setInterval(() => { r += 1.5; o -= 0.05; ring.setStyle({ opacity: Math.max(o, 0) }); ring.setRadius(r);
        if (o <= 0) { clearInterval(t); map.removeLayer(ring); } }, 50);
    },
  };
  svg._osm = handle;
  return handle;
}
