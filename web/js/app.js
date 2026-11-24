// SONACAM dashboard (A-T11, A-T13): one screen with Overview (map, what each artist earned, live feed),
// Songs (every song's share and review flags) and Trust (play log, hourly anchors, how to check).
// D-009: flags are review only. D-011: every bar is metered, no sampling, no range bars.
// D-015: no money; an artist's share = the sum of their songs' shares. D-016: no rules panels.
import { MOCK, get, feed, fmtTime, fmtHm, fmtDateTime } from "./api.js";
import { VIEW, project, outlinePath } from "./cameroon.js";

const LIVE_VENUE = "V-BUEA-CIMFEST";
const state = { period: "live", mode: "standardised", tab: "overview" };
const venuesById = new Map();
const $ = (id) => document.getElementById(id);
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(2) + " %");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- header, KPIs, ledger ----------
function setKpi(id, text) {
  const el = $(id);
  if (el.textContent !== text && el.textContent !== "–") { el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }
  el.textContent = text;
}

function renderKpis(o) {
  setKpi("k-meters", `${o.meters_online} / ${o.meters_total}`);
  setKpi("k-raw", fmtInt(o.plays_raw));
  setKpi("k-counted", fmtInt(o.plays_counted));
  setKpi("k-songs", fmtInt(o.songs_ready));
  $("rule").textContent = `rule ${o.rule_version}`;
}

let lastLedger = null;
function renderLedger(l) {
  lastLedger = l;
  const el = $("ledger");
  if (l.intact) {
    el.className = "ledger ok";
    el.textContent = `Log intact${l.last_anchor ? ` · anchored ${fmtHm(l.last_anchor.hour)}` : ""}`;
  } else {
    el.className = "ledger bad";
    el.textContent = "Log changed · results withheld";
  }
  renderTrustStatus();
}

function tickClock() {
  $("clock").textContent = new Date().toLocaleString("fr-FR", { timeZone: "Africa/Douala", weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// ---------- map ----------
function renderMap(venues) {
  venuesById.clear();
  for (const v of venues) venuesById.set(v.venue_id, v);
  const svg = $("map");
  const parts = [`<path class="land" d="${outlinePath()}"/>`];
  // City labels: one per city, at the mean position of its venues.
  const cities = new Map();
  for (const v of venues) {
    const c = cities.get(v.city) || { lat: 0, lon: 0, n: 0 };
    c.lat += v.lat; c.lon += v.lon; c.n += 1;
    cities.set(v.city, c);
  }
  // Label the live venue's city first, then the busiest; skip a label that would sit on top of one already placed,
  // and put it on the left when the right side is taken (Douala, Buea and Limbe are close together).
  const live = venues.find((v) => v.venue_id === LIVE_VENUE);
  const order = [...cities.entries()].sort((a, b) => (live && b[0] === live.city) - (live && a[0] === live.city) || b[1].n - a[1].n);
  // Venue dots are obstacles too, so a label never covers a bar.
  const placed = venues.map((v) => { const [x, y] = project(v.lat, v.lon); return { x0: x - 7, x1: x + 7, y: y + 4 }; });
  for (const [name, c] of order) {
    const [x, y] = project(c.lat / c.n, c.lon / c.n);
    const w = 6.2 * name.length;
    const spots = [[x + 10, y + 4, "start"], [x - 10, y + 4, "end"], [x + 8, y + 18, "start"], [x + 8, y - 10, "start"]];
    const spot = spots.find(([sx, sy, anchor]) => {
      const x0 = anchor === "end" ? sx - w : sx;
      return !placed.some((p) => x0 < p.x1 + 4 && x0 + w + 4 > p.x0 && Math.abs(sy - p.y) < 13);
    });
    if (!spot) continue;
    const [sx, sy, anchor] = spot;
    const x0 = anchor === "end" ? sx - w : sx;
    placed.push({ x0, x1: x0 + w, y: sy });
    parts.push(`<text class="city" x="${sx.toFixed(1)}" y="${sy.toFixed(1)}" text-anchor="${anchor}">${esc(name)}</text>`);
  }
  let online = 0;
  // Draw the live venue last so it sits on top of its neighbours.
  venues = [...venues].sort((a, b) => (a.venue_id === LIVE_VENUE) - (b.venue_id === LIVE_VENUE));
  for (const v of venues) {
    const [x, y] = project(v.lat, v.lon);
    const on = (v.meters || []).some((m) => m.online);
    if (on) online += 1;
    const live = v.venue_id === LIVE_VENUE;
    const meters = (v.meters || []).map((m) => `${m.meter_id} ${m.online ? "online" : "offline"}`).join(", ");
    parts.push(`<circle class="ring" data-ring="${esc(v.venue_id)}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6"/>`);
    parts.push(`<circle class="venue${on ? " on" : ""}${live ? " live" : ""}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${live ? 8 : 5.5}">
      <title>${esc(v.name)} · ${esc(v.city)}${meters ? ` · ${esc(meters)}` : ""}</title></circle>`);
  }
  svg.setAttribute("viewBox", `0 0 ${VIEW.w} ${VIEW.h}`);
  svg.innerHTML = parts.join("");
  $("map-note").textContent = `${venues.length} bars · ${online} with a meter online`;
}

let toastTimer = null;
function showPlayOnMap(venueId, text) {
  const ring = document.querySelector(`circle[data-ring="${CSS.escape(venueId || "")}"]`);
  if (ring) { ring.classList.remove("go"); void ring.getBoundingClientRect(); ring.classList.add("go"); }
  const v = venuesById.get(venueId);
  const t = $("map-toast");
  t.textContent = `${text}${v ? ` · ${v.name}, ${v.city}` : ""}`;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 5000);
}

// ---------- what each artist earned ----------
const openArtists = new Set();
let lastEarn = null;
function renderEarnings(e) {
  lastEarn = e;
  $("earn-frozen").classList.toggle("show", !!e.frozen);
  setKpi("k-artists", e.frozen ? "–" : fmtInt(e.rows.filter((r) => r.counted_plays > 0).length));
  const max = Math.max(...e.rows.map((r) => r.share), 0.0001);
  $("earn").innerHTML = e.rows.map((r) => {
    const w = (100 * r.share / max).toFixed(1);
    const link = `artist.html?name=${encodeURIComponent(r.artist_name)}&period=${state.period}`;
    const open = openArtists.has(r.artist_name);
    const songs = open ? r.songs.map((s) => `<tr class="sub"><td></td><td class="name">${esc(s.title)}</td><td></td>
      <td class="n">${fmtInt(s.raw_plays)}</td><td class="n">${fmtInt(s.counted_plays)}</td><td class="n">${fmtPct(s.share)}</td>
      <td><div class="bar"><i style="width:${(100 * s.share / max).toFixed(1)}%"></i></div></td></tr>`).join("") : "";
    return `<tr class="artist${r.rank <= 3 ? " top3" : ""}" data-artist="${esc(r.artist_name)}">
      <td>${r.rank}</td><td class="name"><span class="caret">${open ? "▾" : "▸"}</span>${esc(r.artist_name)}<a href="${link}">page</a></td>
      <td class="n">${r.n_songs}</td><td class="n">${fmtInt(r.raw_plays)}</td><td class="n">${fmtInt(r.counted_plays)}</td>
      <td class="n share">${fmtPct(r.share)}</td><td><div class="bar"><i style="width:${w}%"></i></div></td></tr>${songs}`;
  }).join("") || `<tr><td colspan="7" class="note">${e.frozen ? "Withheld until the log is restored." : "No plays counted in this period yet."}</td></tr>`;
  $("usage-dl").href = `/api/v1/export/usage_report.csv?period=${state.period}&mode=${state.mode}`;
  $("earn-note").textContent = e.stats_run_id
    ? `${e.rule_version} · run ${e.stats_run_id} · an artist earns for all their songs together (their songs' shares added up) · click an artist to see the songs`
    : "An artist earns for all their songs together: their songs' shares are added up.";
}
$("earn").addEventListener("click", (ev) => {
  if (ev.target.closest("a")) return;
  const tr = ev.target.closest("tr.artist");
  if (!tr || !lastEarn) return;
  const n = tr.dataset.artist;
  if (openArtists.has(n)) openArtists.delete(n); else openArtists.add(n);
  renderEarnings(lastEarn);
});

// Flat equal split vs Fair Play against the mock month's known truth (brief §7.4): the share of the pot that
// would go to the wrong artists. Both numbers are computed by the server (no money shown, D-015).
function renderCompare(c) {
  const el = $("compare");
  if (state.period !== "mock_month" || !c || !c.n_artists || !c.pot_fcfa) { el.innerHTML = ""; return; }
  const pf = c.misallocated_flat_fcfa / c.pot_fcfa, pp = c.misallocated_fairplay_fcfa / c.pot_fcfa;
  const scale = Math.max(pf, pp, 0.0001);
  el.innerHTML = `<b>Share of the pot that goes to the wrong artists</b> (mock month, ${c.n_artists} artists, against what really played)
    <div class="vs">
      <span>flat equal split</span><div class="bar"><i class="bad" style="width:${(100 * pf / scale).toFixed(1)}%"></i></div><b>${fmtPct(pf)}</b>
      <span>Fair Play</span><div class="bar"><i style="width:${(100 * pp / scale).toFixed(1)}%"></i></div><b>${fmtPct(pp)}</b>
    </div>`;
}

// ---------- songs ----------
function renderShares(s) {
  const max = Math.max(...s.rows.map((r) => r.share), 0.0001);
  $("shares").innerHTML = s.rows.map((r, i) => {
    const flags = (r.flags || []).map((f) => `<span class="chip">${esc(f)}</span>`).join("");
    return `<tr><td>${i + 1}</td><td>${esc(r.title)}</td><td>${esc(r.artist_name)}</td>
      <td class="n">${fmtInt(r.raw_plays)}</td><td class="n">${fmtInt(r.weighted_plays)}</td><td class="n share">${fmtPct(r.share)}</td>
      <td><div class="bar"><i style="width:${(100 * r.share / max).toFixed(1)}%"></i></div></td><td>${flags}</td></tr>`;
  }).join("") || `<tr><td colspan="8" class="note">No plays counted in this period yet.</td></tr>`;
  $("shares-note").textContent = `${s.rule_version}${s.stats_run_id ? ` · run ${s.stats_run_id}` : ""} · share = the song's counted plays ÷ all counted plays`;
}

// ---------- trust ----------
function renderTrustStatus() {
  const l = lastLedger;
  if (!l) return;
  const st = $("trust-status");
  st.className = "status" + (l.intact ? "" : " bad");
  st.textContent = l.intact ? "Play log intact" : `Play log changed${l.broken_at_play_id ? ` at play ${l.broken_at_play_id}` : ""} · results withheld`;
  if (l.plays_checked != null) $("t-checked").textContent = fmtInt(l.plays_checked);
  if (l.last_root) $("t-root").textContent = l.last_root;
  $("t-anchor").textContent = l.last_anchor ? `${fmtDateTime(l.last_anchor.hour)} · ${l.last_anchor.via}${l.last_anchor.tx_ref ? ` · ${l.last_anchor.tx_ref}` : ""}` : "none yet";
}

function renderAnchors(list) {
  $("anchors").innerHTML = list.map((a) => `<tr><td>${fmtDateTime(a.hour)}</td><td class="n">${a.n_plays == null ? "–" : fmtInt(a.n_plays)}</td>
    <td class="mono" title="${esc(a.root)}">${esc((a.root || "").slice(0, 16))}…</td><td>${esc(a.via)}${a.tx_ref ? ` · ${esc(a.tx_ref)}` : ""}</td></tr>`).join("")
    || `<tr><td colspan="4" class="note">No hour anchored yet.</td></tr>`;
}

// ---------- live feed ----------
// Shows what a person cares about: plays, songs heard, flags, log status, meters going on/offline.
// Every 10 s batch and every "no song" window would drown the list, so they are not listed.
const feedItems = [];
const meterOnline = new Map();
function feedLine(event, data) {
  const v = venuesById.get(data.venue_id);
  const where = v ? `${v.name}, ${v.city}` : (data.venue_id || "");
  switch (event) {
    case "play": return { tag: "play", text: `${esc(data.title)} · ${esc(data.artist_name || "")}`, sub: esc(where) };
    case "match": return data.accepted ? { tag: "heard", text: `${esc(data.title)}`, sub: `${esc(data.meter_id)} · ${Math.round(data.offset_s)} s into the song` } : null;
    case "batch": return data.late ? { tag: "late", text: `${esc(data.meter_id)} sent a delayed sample`, sub: `seq ${data.seq}` } : null;
    case "flag": return { tag: "flag", text: esc(data.type), sub: esc(data.detail) };
    case "ledger": return { tag: data.intact ? "ledger" : "ledger bad", text: data.intact ? "play log intact" : "play log changed · results withheld", sub: data.broken_at_play_id ? `at ${esc(data.broken_at_play_id)}` : "" };
    case "meter": {
      const was = meterOnline.get(data.meter_id);
      meterOnline.set(data.meter_id, data.online);
      if (was === data.online) return null;
      return { tag: "meter", text: `${esc(data.meter_id)} ${data.online ? "online" : "offline"}`, sub: data.queued ? `${data.queued} samples queued` : "" };
    }
    case "stats": return { tag: "stats", text: "shares recalculated", sub: `run ${esc(data.stats_run_id)}` };
    case "epoch": return { tag: "reset", text: "live demo data reset", sub: "" };
    default: return null;
  }
}

function addFeed({ event, data }) {
  $("feed-state").className = "live-dot ok";
  $("feed-state").textContent = MOCK ? "replaying sample" : "live";
  const line = feedLine(event, data);
  if (line) {
    feedItems.unshift({ ...line, time: fmtTime(data.window_start || data.started_at || data.last_seen || data.created_at) || fmtTime(new Date().toISOString()) });
    feedItems.length = Math.min(feedItems.length, 40);
    $("feed").innerHTML = feedItems.map((i, k) => `<li${k === 0 ? ' class="new"' : ""}><span class="tag ${i.tag}">${i.tag.split(" ")[0]}</span>
      <span>${i.text}${i.sub ? `<span class="sub">${i.sub}</span>` : ""}</span><span class="t">${i.time}</span></li>`).join("");
  }
  if (event === "play") showPlayOnMap(data.venue_id, `▶ ${data.title}`);
  if (event === "stats") { loadOverview(); loadShares(); loadEarnings(); }
  if (event === "ledger") { loadLedger(); loadEarnings(); }
  if (event === "meter" && state.period === "live") loadVenuesSoon();
}

// ---------- loading ----------
async function loadOverview() {
  try { renderKpis(await get("overview", state.period)); } catch (e) { $("rule").textContent = String(e); }
}
let venuesTimer = null;
function loadVenuesSoon() { clearTimeout(venuesTimer); venuesTimer = setTimeout(loadVenues, 1500); }
async function loadVenues() {
  try { renderMap(await get("venues", state.period)); } catch (_) { /* keep the old map */ }
}
async function loadEarnings() {
  try {
    const [e, c] = await Promise.all([get("artist_shares", state.period, state.mode),
      state.period === "mock_month" ? get("compare_flat").catch(() => null) : Promise.resolve(null)]);
    renderEarnings(e);
    renderCompare(c);
  } catch (err) { $("earn-note").textContent = String(err); }
}
async function loadShares() {
  try { renderShares(await get("shares", state.period, state.mode)); } catch (e) { $("shares-note").textContent = String(e); }
}
async function loadLedger() {
  try { renderLedger(await get("ledger_status", state.period)); } catch (_) { /* keep the old banner */ }
  try { renderAnchors(await get("anchors")); } catch (_) {
    renderAnchors(lastLedger && lastLedger.last_anchor ? [lastLedger.last_anchor] : []);
  }
}
function loadAll() { loadOverview(); loadVenues(); loadEarnings(); loadShares(); loadLedger(); }

// ---------- controls ----------
function setOn(attr, value) {
  document.querySelectorAll(`[data-${attr}]`).forEach((b) => b.classList.toggle("on", b.dataset[attr] === value));
}
function showTab(tab) {
  state.tab = tab;
  setOn("tab", tab);
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("on", v.id === `view-${tab}`));
  history.replaceState(null, "", `${location.search}#${tab}`);
}
document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
$("ledger").addEventListener("click", () => showTab("trust"));
document.querySelectorAll("[data-period]").forEach((b) => b.addEventListener("click", () => {
  state.period = b.dataset.period;
  setOn("period", state.period);
  openArtists.clear();
  loadAll();
}));
document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
  state.mode = b.dataset.mode;
  setOn("mode", state.mode);
  loadEarnings();
  loadShares();
}));
// Keys for the pitch: 1/2/3 switch tabs, L/M switch period.
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
  const tab = { 1: "overview", 2: "songs", 3: "trust" }[e.key];
  if (tab) showTab(tab);
  if (e.key === "l" || e.key === "m") document.querySelector(`[data-period="${e.key === "l" ? "live" : "mock_month"}"]`).click();
});

const startTab = location.hash.slice(1);
if (["overview", "songs", "trust"].includes(startTab)) showTab(startTab);
$("mode-note").textContent = MOCK ? " · mock data (?mock=1)" : "";
tickClock();
setInterval(tickClock, 1000);
loadAll();
setInterval(() => { if (state.period === "live") { loadOverview(); loadVenues(); } }, 30000);
feed(addFeed);
