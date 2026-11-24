// Landing page. Every number shown is computed by the system (API, or the fixtures with ?mock=1).
// No scroll animation and no counters: values are written once when the data arrives.
import { MOCK, get, feed, fmtTime } from "./api.js";
import { VIEW, project, outlinePath } from "./cameroon.js";
import { loadCovers, initials } from "./covers.js";

const $ = (id) => document.getElementById(id);
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x, d = 2) => (x == null ? "–" : (100 * x).toFixed(d) + " %");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LIVE_VENUE = "V-BUEA-CIMFEST";

async function numbers() {
  try {
    const o = await get("overview", "live");
    $("n-counted").textContent = fmtInt(o.plays_counted);
    $("n-meters").textContent = fmtInt(o.meters_online);
  } catch (_) { /* leave dashes */ }
}

async function mapTile() {
  try {
    const venues = await get("venues", "live");
    $("n-bars").textContent = fmtInt(venues.length);
    const cities = new Set(venues.map((v) => v.city));
    $("map-title").textContent = `${venues.length} bars in ${cities.size} cities.`;
    const parts = [`<path class="land" d="${outlinePath()}"/>`];
    for (const v of [...venues].sort((a, b) => (a.venue_id === LIVE_VENUE) - (b.venue_id === LIVE_VENUE))) {
      const [x, y] = project(v.lat, v.lon);
      const on = (v.meters || []).some((m) => m.online), live = v.venue_id === LIVE_VENUE;
      if (live) parts.push(`<circle class="ring" cx="${x}" cy="${y}" r="17"/>`);
      parts.push(`<circle class="v${live ? " live" : on ? "" : " off"}" cx="${x}" cy="${y}" r="${live ? 9 : 6.5}"><title>${esc(v.name)}, ${esc(v.city)}</title></circle>`);
    }
    $("mini-map").setAttribute("viewBox", `0 0 ${VIEW.w} ${VIEW.h}`);
    $("mini-map").innerHTML = parts.join("");
  } catch (_) { /* keep the title */ }
}

async function compareTile() {
  try {
    const c = await get("compare_flat");
    if (!c || !c.n_artists || !c.pot_fcfa) throw new Error("not computed");
    const pf = c.misallocated_flat_fcfa / c.pot_fcfa, pp = c.misallocated_fairplay_fcfa / c.pot_fcfa;
    const scale = Math.max(pf, pp);
    $("cmp-flat-v").textContent = fmtPct(pf, 1);
    $("cmp-fp-v").textContent = fmtPct(pp, 1);
    $("cmp-flat").style.width = `${(100 * pf / scale).toFixed(1)}%`;
    $("cmp-fp").style.width = `${(100 * pp / scale).toFixed(1)}%`;
    $("cmp-ratio").textContent = pp > 0 ? `${(pf / pp).toFixed(1).replace(".", ",")}×` : "–";
    $("cmp-note").textContent = `Share of the pot that would go to the wrong artists in the mock month (${c.n_artists} artists), measured against what really played.`;
  } catch (_) { $("cmp-note").textContent = "The comparison appears once the mock month has been computed."; }
}

async function sharesTiles() {
  $("ps-time").textContent = new Date().toLocaleTimeString("fr-FR", { timeZone: "Africa/Douala", hour: "2-digit", minute: "2-digit" });
  try {
    const s = await get("artist_shares", "mock_month", "standardised");
    if (s.frozen) throw new Error("frozen");
    $("n-artists").textContent = fmtInt(s.rows.filter((r) => r.counted_plays > 0).length);
    const max = Math.max(...s.rows.map((r) => r.share), 0.0001);
    $("toplist").innerHTML = s.rows.slice(0, 4).map((r) => `<li><span>${esc(r.artist_name)}</span><b>${fmtPct(r.share)}</b><i style="width:${(100 * r.share / max).toFixed(0)}%"></i></li>`).join("");
    const a = s.rows[0];
    if (!a) return;
    $("ps-name").textContent = a.artist_name;
    $("ps-avatar").textContent = a.artist_name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    $("ps-share").textContent = fmtPct(a.share);
    $("ps-rank").textContent = `#${a.rank} of ${s.rows.length}`;
    $("ps-counted").textContent = fmtInt(a.counted_plays);
    $("ps-heard").textContent = fmtInt(a.raw_plays);
    const m = Math.max(...a.songs.map((x) => x.share), 0.0001);
    $("ps-songs").innerHTML = a.songs.slice(0, 4).map((x) => `<div class="ps-row"><div><span>${esc(x.title)}</span><b>${fmtPct(x.share)}</b></div><i style="width:${(100 * x.share / m).toFixed(0)}%"></i></div>`).join("");
    $("ps-foot").textContent = `Example from the mock month, rule ${s.rule_version}.`;
    musicTiles(s);
  } catch (_) { $("ps-foot").textContent = "Shares appear once a period has been computed."; }
}

// Music block: real album covers, matched only to the artist (or song) they belong to.
const setCover = (el, c, name) => {
  if (!el) return;
  el.style.backgroundImage = c ? `url("${c.src}")` : "";
  el.textContent = c ? "" : initials(name);
};

async function musicTiles(s) {
  const cv = await loadCovers();
  const top = s.rows[0], song = top && [...top.songs].sort((a, b) => b.share - a.share)[0];
  if (song) {
    const c = cv.song(top.artist_name, song.title) || cv.artist(top.artist_name);
    setCover($("frame-cover"), c, top.artist_name);
    if (c) averageColour(c.src).then((rgb) => rgb && $("tile-frames").style.setProperty("--tint", rgb));
    $("frame-who").textContent = `${song.title} · ${top.artist_name}`;
  }
  $("mix-sub").textContent = `${s.rows.length} artists, mock month`;
  s.rows.slice(0, 3).forEach((r, i) => {
    const el = $(`mix-${i + 1}`), c = cv.artist(r.artist_name);
    if (c) el.style.backgroundImage = `url("${c.src}")`; else el.textContent = initials(r.artist_name);
    el.title = r.artist_name;
  });
  $("mix-list").innerHTML = s.rows.slice(0, 5).map((r) => {
    const c = cv.artist(r.artist_name);
    return `<li><i${c ? ` style="background-image:url('${c.src}')"` : ""}></i><span>${esc(r.artist_name)}</span><b>${fmtPct(r.share)}</b></li>`;
  }).join("");
}

// Stepped frames: panels behind the cover, each wider and taller, tinted from the cover; they sway together,
// inner ones further and a little later, so the stack reads as depth.
const LAYERS = 12;
function buildFrames() {
  const tile = $("tile-frames"), box = $("frames");
  if (!tile || !box) return;
  const W = tile.clientWidth, H = tile.clientHeight;
  const cover = Math.round(Math.min(W * 0.27, H * 0.36)), top = Math.round(H * 0.08);
  const stepX = Math.round(Math.max(14, W * 0.024)), stepY = Math.round(stepX * 1.05);
  const panels = [];
  for (let k = LAYERS; k >= 1; k--) {
    const w = cover + 2 * stepX * k, h = cover + stepY * k * 1.5 + top;
    panels.push(`<i class="fl" style="--w:${w}px;--h:${h}px;--top:${-top - stepY * k * 0.1}px;--lift:${(LAYERS - k) * 1.6}%;--amp:${(LAYERS - k + 2) * 0.55}px;--delay:${(-k * 0.09).toFixed(2)}s"></i>`);
  }
  box.querySelectorAll(".fl").forEach((n) => n.remove());
  box.insertAdjacentHTML("afterbegin", panels.join(""));
  const fc = $("frame-cover");
  fc.style.cssText += `;--w:${cover}px;--top:${top}px;--amp:${(LAYERS + 3) * 0.55}px;--delay:0s`;
}
// Average colour of a cover (same-origin image), darkened slightly so white text stays readable on it.
function averageColour(src) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement("canvas"); c.width = c.height = 24;
        const g = c.getContext("2d"); g.drawImage(img, 0, 0, 24, 24);
        const d = g.getImageData(0, 0, 24, 24).data; let r = 0, gg = 0, b = 0;
        for (let i = 0; i < d.length; i += 4) { r += d[i]; gg += d[i + 1]; b += d[i + 2]; }
        const n = d.length / 4, k = 0.72;
        resolve(`rgb(${Math.round((r / n) * k)}, ${Math.round((gg / n) * k)}, ${Math.round((b / n) * k)})`);
      } catch (_) { resolve(null); }
    };
    img.onerror = () => resolve(null);
    img.src = src;
  });
}
buildFrames();
let framesTimer = null;
addEventListener("resize", () => { clearTimeout(framesTimer); framesTimer = setTimeout(buildFrames, 150); });
if ($("sway-btn")) $("sway-btn").addEventListener("click", () => {
  const p = $("tile-frames").classList.toggle("paused");
  $("sway-btn").setAttribute("aria-label", p ? "Play the animation" : "Pause the animation");
});
if (matchMedia("(prefers-reduced-motion: reduce)").matches && $("tile-frames")) $("tile-frames").classList.add("paused");

// Wall of covers: one per album, laid out on fixed spots around the headline (no randomness between loads).
const SPOTS = [[3, 6, 15], [21, -4, 12], [40, 3, 10], [60, -6, 13], [79, 4, 15], [93, 30, 12], [-3, 36, 14], [8, 70, 13], [27, 82, 11],
  [47, 78, 12], [66, 84, 14], [84, 66, 13], [16, 40, 9], [76, 38, 10]];
async function wallTile() {
  const cv = await loadCovers();
  const pick = cv.albums.slice(0, SPOTS.length);
  $("wall").innerHTML = pick.map((c, i) => { const [x, y, w] = SPOTS[i];
    return `<div class="cv" style="left:${x}%;top:${y}%;width:${w}%;aspect-ratio:1;background-image:url('${c.src}')" title="${esc(c.album)} · ${esc(c.artist)}"></div>`; }).join("");
  const artists = new Set(cv.list.map((c) => c.artist));
  $("wall-note").textContent = cv.list.length ? `Covers from ${artists.size} artists in the Fair Play catalogue.` : "";
}

async function trustTiles() {
  let l = null;
  try { l = await get("ledger_status", "live"); } catch (_) { /* below */ }
  const root = (l && l.last_root) || "";
  $("hash-status").textContent = !l ? "Not reachable." : l.intact ? "Intact." : "Changed. Results withheld.";
  $("hash-status").classList.toggle("bad", !!l && !l.intact);
  $("hash-root").textContent = root ? root.slice(0, 32) + "…" : "No plays yet.";
  $("hash-note").textContent = l && l.plays_checked != null ? `${fmtInt(l.plays_checked)} plays checked against the chain.` : "";
  // Only the latest block shows a real value (the current chain hash); the others show the structure.
  const blocks = [["Play n−3", "sealed to the next"], ["Play n−2", "sealed to the next"], ["Play n−1", "sealed to the next"],
    ["Latest play", root ? `${root.slice(0, 16)}…` : "no plays yet"]];
  $("chain").innerHTML = blocks.map(([t, h], i) => `${i ? '<span class="link"></span>' : ""}<div class="blk${i === 3 ? " last" : ""}"><b>${t}</b>${i === 3 ? "chain hash" : "&nbsp;"}<code>${esc(h)}</code></div>`).join("");
}

// Live from the bars: plays and recognised songs from the event stream (the fixture replay with ?mock=1).
const liveItems = [];
const venueName = new Map();
get("venues", "live").then((vs) => vs.forEach((v) => venueName.set(v.venue_id, `${v.name}, ${v.city}`))).catch(() => {});
const songArtist = new Map();
get("songs", "live").then((ss) => ss.forEach((s) => songArtist.set(s.song_id, s.artist_name))).catch(() => {});
feed(({ event, data }) => {
  $("live-state").textContent = MOCK ? "Replaying sample events" : "Connected";
  $("live-state").classList.add("on");
  if (event !== "play" && !(event === "match" && data.accepted)) return;
  const item = { kind: event === "play" ? "Play" : "Heard", title: data.title || data.song_id, artist: data.artist_name || songArtist.get(data.song_id) || "",
    where: venueName.get(data.venue_id) || data.venue_id || "", time: fmtTime(data.started_at || data.window_start) };
  liveItems.unshift(item);
  liveItems.length = Math.min(liveItems.length, 5);
  $("live-list").innerHTML = liveItems.map((i) => `<li>${esc(i.title)}<span>${i.kind} · ${esc(i.where)} · ${i.time}</span></li>`).join("");
  loadCovers().then((cv) => setCover($("lyric-art"), cv.song(item.artist, item.title) || cv.artist(item.artist), item.artist || item.title));
});

numbers(); mapTile(); compareTile(); sharesTiles(); trustTiles(); wallTile();

if (MOCK) {
  document.title += " (mock data)";
  document.querySelectorAll('a[href$=".html"]').forEach((a) => { a.href += (a.href.includes("?") ? "&" : "?") + "mock=1"; });
}
