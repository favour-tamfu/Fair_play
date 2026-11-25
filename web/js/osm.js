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
const DARK_COLOURS = { live: "#2997ff", on: "#30d158", off: "#98989d", hit: "#2997ff", other: "#636366" };

// The map takes the look of the page it sits on: a quiet grey map (no OSM colours) that is light on light pages
// and dark on dark ones, with the site's own controls. The tiles stay OpenStreetMap's; only a filter is applied.
const STYLE = `
.osm-map { isolation: isolate; }
.osm-map[data-theme="light"] { background: #f5f5f7; }
.osm-map[data-theme="dark"]  { background: #1c1c1e; }
.osm-map[data-theme="light"] .leaflet-tile-pane { filter: grayscale(1) brightness(1.07) contrast(.86); }
.osm-map[data-theme="dark"]  .leaflet-tile-pane { filter: grayscale(1) invert(1) brightness(.82) contrast(.88); }
.osm-map .leaflet-bar { border: 0; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0, 0, 0, .16); }
.osm-map .leaflet-bar a { width: 30px; height: 30px; line-height: 29px; border: 0; border-radius: 0;
  font: 400 18px/29px "SF Pro Text", "SF Pro", -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", Arial, sans-serif;
  background: rgba(255, 255, 255, .92); color: #1d1d1f; backdrop-filter: saturate(180%) blur(12px); }
.osm-map .leaflet-bar a + a { border-top: 1px solid rgba(0, 0, 0, .1); }
.osm-map .leaflet-bar a:hover { background: #fff; }
.osm-map .leaflet-bar a.leaflet-disabled { color: #c7c7cc; background: rgba(255, 255, 255, .92); }
.osm-map[data-theme="dark"] .leaflet-bar a { background: rgba(44, 44, 46, .92); color: #f5f5f7; }
.osm-map[data-theme="dark"] .leaflet-bar a + a { border-top-color: rgba(255, 255, 255, .1); }
.osm-map[data-theme="dark"] .leaflet-bar a:hover { background: #3a3a3c; }
.osm-map[data-theme="dark"] .leaflet-bar a.leaflet-disabled { color: #636366; background: rgba(44, 44, 46, .92); }
.osm-map .leaflet-control-attribution { background: none; padding: 2px 8px; font-size: 10px; line-height: 1.4; color: #86868b; }
.osm-map .leaflet-control-attribution a { color: inherit; text-decoration: none; }
.osm-map .leaflet-control-attribution a:hover { text-decoration: underline; }
.osm-map[data-theme="dark"] .leaflet-control-attribution { color: #8e8e93; }
.osm-map .leaflet-popup-content-wrapper, .osm-map .leaflet-tooltip { border-radius: 12px; box-shadow: 0 4px 16px rgba(0, 0, 0, .14);
  font: 400 13px/1.38 "SF Pro Text", "SF Pro", -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", Arial, sans-serif;
  letter-spacing: -.01em; background: #fff; color: #1d1d1f; border: 0; }
.osm-map .leaflet-popup-content { margin: 12px 14px; color: inherit; }
.osm-map .leaflet-tooltip { padding: 6px 10px; }
.osm-map .leaflet-tooltip::before { display: none; }
.osm-map .leaflet-popup-tip { background: #fff; box-shadow: none; }
.osm-map[data-theme="dark"] :is(.leaflet-popup-content-wrapper, .leaflet-popup-tip, .leaflet-tooltip) { background: #2c2c2e; color: #f5f5f7; }
.osm-map a.leaflet-popup-close-button { color: #86868b; }
`;

function injectStyle() {
  if (document.getElementById("osm-theme")) return;
  const st = document.createElement("style");
  st.id = "osm-theme";
  st.textContent = STYLE;
  document.head.appendChild(st);
}

// Dark when the first non-transparent background around the map is dark.
function themeOf(el) {
  for (let x = el.parentElement; x; x = x.parentElement) {
    const m = getComputedStyle(x).backgroundColor.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    if (!m || (m[4] !== undefined && +m[4] < 0.5)) continue;
    const lum = (0.2126 * m[1] + 0.7152 * m[2] + 0.0722 * m[3]) / 255;
    return lum < 0.45 ? "dark" : "light";
  }
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

// Replace `svg` (kept in the page, hidden) by a Leaflet map of the same size; returns {map, draw, pulse} or null.
export async function osmMap(svg, { height } = {}) {
  if (!svg || !(await osmAvailable())) return null;
  if (svg._osm) return svg._osm;
  injectStyle();
  const box = document.createElement("div");
  box.className = "osm-map";
  box.style.height = height || `${Math.max(260, svg.getBoundingClientRect().height || 340)}px`;
  svg.after(box);
  svg.style.display = "none";
  box.dataset.theme = themeOf(box);
  const L = window.L;
  const map = L.map(box, { scrollWheelZoom: false, zoomSnap: 0.5, attributionControl: true, minZoom: 5, maxZoom: 17 });
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
  L.tileLayer(TILE, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(map);
  map.fitBounds(CAMEROON);
  const layer = L.layerGroup().addTo(map);
  const byId = new Map();
  let fitted = false;
  let last = [];
  const palette = () => (box.dataset.theme === "dark" ? DARK_COLOURS : COLOURS);
  const ring = () => (box.dataset.theme === "dark" ? "#1c1c1e" : "#fff");
  // follow the system's light/dark switch (and any page that changes its background)
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const t = themeOf(box);
    if (t !== box.dataset.theme) { box.dataset.theme = t; handle.draw(last, { fit: false }); }
  });
  const handle = {
    map,
    draw(points, { fit = !fitted } = {}) {
      last = points;
      layer.clearLayers(); byId.clear();
      for (const p of points) {
        if (p.lat == null || p.lon == null) continue;
        const colour = p.colour || palette()[p.kind] || palette().on;
        const m = L.circleMarker([p.lat, p.lon], { radius: p.r || 7, color: ring(), weight: 1.5, fillColor: colour,
          fillOpacity: p.kind === "off" || p.kind === "other" ? 0.55 : 0.9 });
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
      const ring = L.circleMarker(m.getLatLng(), { radius: m.options.radius, color: palette().live, weight: 3, fill: false, opacity: 0.9 }).addTo(map);
      let r = m.options.radius, o = 0.9;
      const t = setInterval(() => { r += 1.5; o -= 0.05; ring.setStyle({ opacity: Math.max(o, 0) }); ring.setRadius(r);
        if (o <= 0) { clearInterval(t); map.removeLayer(ring); } }, 50);
    },
  };
  svg._osm = handle;
  return handle;
}
