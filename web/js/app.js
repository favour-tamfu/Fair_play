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
  const foot = (id, html) => { const el = $(id); if (el) el.innerHTML = html; };
  foot("kf-counted", o.plays_raw ? `<b>${fmtPct(o.plays_counted / o.plays_raw).replace(".00", "")}</b> of plays heard` : "no plays yet");
  foot("kf-raw", `in <b>${fmtInt(o.venues)}</b> metered bars`);
  foot("kf-meters", `<b>${fmtInt(o.meters_total - o.meters_online)}</b> offline or simulated`);
}

// Greeting and breadcrumb (dashboard layout).
function greet() {
  const h = +new Date().toLocaleString("en-GB", { timeZone: "Africa/Douala", hour: "2-digit", hour12: false });
  if ($("greet")) $("greet").textContent = `${h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"}, SONACAM`;
}

// Dot-matrix chart: one group of square columns per artist; light squares = plays heard, dark = plays counted.
// Square size is a fixed number of plays (shown in the y labels). A table view sits under the chart.
function compact(n) { return n >= 1e6 ? (n / 1e6).toFixed(1).replace(".0", "") + "M" : n >= 1e3 ? (n / 1e3).toFixed(1).replace(".0", "") + "k" : String(Math.round(n)); }
function renderDots(e) {
  const box = $("dots");
  if (!box) return;
  $("t-total").textContent = e.frozen ? "–" : fmtInt(e.rows.reduce((t, r) => t + (r.counted_plays || 0), 0));
  const rows = e.frozen ? [] : [...e.rows].filter((r) => r.raw_plays > 0).sort((a, b) => b.raw_plays - a.raw_plays).slice(0, 24);
  $("dots-tbody").innerHTML = rows.map((r) => `<tr><td>${esc(r.artist_name)}</td><td class="n">${fmtInt(r.raw_plays)}</td><td class="n">${fmtInt(r.counted_plays)}</td></tr>`).join("");
  if (!rows.length) { box.innerHTML = `<p class="dots-empty">${e.frozen ? "Withheld until the log is restored." : "No plays in this period yet."}</p>`; $("dots-x").innerHTML = ""; return; }
  // One column per song (up to 64 columns), grouped by artist; each square is a fixed number of plays.
  const H = 22, groupsData = [];
  let ncols = 0;
  for (const r of rows) {
    const songs = (r.songs && r.songs.length ? [...r.songs] : [{ title: r.artist_name, raw_plays: r.raw_plays, counted_plays: r.counted_plays }])
      .sort((a, b) => (b.raw_plays || 0) - (a.raw_plays || 0));
    if (ncols && ncols + songs.length > 64) break;
    groupsData.push({ r, songs }); ncols += songs.length;
  }
  const max = Math.max(...groupsData.flatMap((g) => g.songs.map((s) => s.raw_plays || 0)), 1);
  const unit = max / H;
  const ticks = [0, 1, 2, 3, 4, 5, 6].map((k) => compact((max * (6 - k)) / 6));
  const groups = groupsData.map(({ r, songs }, gi) => {
    const cols = songs.map((s) => {
      const nh = s.raw_plays > 0 ? Math.max(1, Math.round(s.raw_plays / unit)) : 0, nc = Math.min(nh, Math.round((s.counted_plays || 0) / unit));
      return `<div class="dcol" title="${esc(s.title)}: heard ${fmtInt(s.raw_plays)}, counted ${fmtInt(s.counted_plays)}">${Array.from({ length: H }, (_, k) => { const fb = H - k; return `<i class="${fb <= nc ? "c" : fb <= nh ? "h" : ""}"></i>`; }).join("")}</div>`;
    }).join("");
    const label = groupsData.length > 10 && songs.length < 3 ? initialsOf(r.artist_name) : r.artist_name;
    return `<div class="dgroup" data-g="${gi}"><div class="dcols">${cols}</div><span class="dlabel" title="${esc(r.artist_name)}">${esc(label)}</span></div>`;
  });
  // Fill the whole width with a lattice of empty squares, spreading the artist groups evenly across it.
  const avail = Math.max(200, box.clientWidth - 54);
  const sq = Math.max(7, Math.min(14, Math.floor(avail / (ncols + groupsData.length + 1) - 3)));
  const capacity = Math.floor((avail + 3) / (sq + 3));
  const spare = Math.max(0, capacity - ncols), slots = groupsData.length + 1;
  const emptyCol = `<div class="dcol">${"<i></i>".repeat(H)}</div>`;
  const filler = (k) => `<div class="dfill"><div class="dcols">${emptyCol.repeat(k)}</div></div>`;
  const parts = [];
  groups.forEach((g, i) => { const k = Math.floor(spare / slots) + (i < spare % slots ? 1 : 0); if (k) parts.push(filler(k)); parts.push(g); });
  const last = Math.floor(spare / slots);
  if (last) parts.push(filler(last));
  box.innerHTML = `<div class="dots-y">${ticks.map((t) => `<span>${t}</span>`).join("")}</div><div class="dots-grid">${parts.join("")}</div>`;
  box.style.setProperty("--sq", `${sq}px`);
  $("dots-x").innerHTML = "";
  const tip = $("dot-tip"), card = box.closest(".card-i");
  box.querySelectorAll(".dgroup").forEach((g) => {
    const r = groupsData[+g.dataset.g].r;
    const show = () => {
      box.querySelectorAll(".dgroup.hover").forEach((x) => x.classList.remove("hover"));
      g.classList.add("hover");
      tip.innerHTML = `<p>${esc(r.artist_name)}</p><p><i style="background:var(--heard)"></i>Heard<b>${fmtInt(r.raw_plays)}</b></p><p><i style="background:var(--counted)"></i>Counted<b>${fmtInt(r.counted_plays)}</b></p><p>Share<b>${fmtPct(r.share)}</b></p>`;
      const gb = g.getBoundingClientRect(), cb = card.getBoundingClientRect();
      const left = gb.right - cb.left + 12 + 200 > cb.width ? gb.left - cb.left - 212 : gb.right - cb.left + 12;
      tip.style.left = `${Math.max(8, left)}px`;
      tip.style.top = `${Math.max(8, gb.top - cb.top + 20)}px`;
      tip.classList.add("show");
    };
    g.addEventListener("mouseenter", show);
    g.addEventListener("focus", show);
    g.tabIndex = 0;
  });
  box.onmouseleave = () => { tip.classList.remove("show"); box.querySelectorAll(".dgroup.hover").forEach((x) => x.classList.remove("hover")); };
}
const initialsOf = (n) => String(n).split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

// Small bars in the counted and heard cards: the top artists' plays, the leader dark.
function renderSparks(e) {
  const rows = e.frozen ? [] : e.rows.slice(0, 9);
  for (const [id, key] of [["sp-counted", "counted_plays"], ["sp-raw", "raw_plays"]]) {
    const el = $(id);
    if (!el) continue;
    const m = Math.max(...rows.map((r) => r[key] || 0), 1);
    el.innerHTML = rows.map((r, i) => `<i class="${i === 0 ? "hi" : ""}" style="height:${Math.max(8, (100 * (r[key] || 0)) / m)}%"></i>`).join("");
    el.title = "Top artists' plays";
  }
  const k = $("kf-artists");
  if (k) k.innerHTML = rows[0] ? `led by <b>${esc(rows[0].artist_name)}</b>` : "no plays yet";
}

// Filter box: hides artist and song rows that do not match.
function applyFilter() {
  const q = ($("q") ? $("q").value : "").trim().toLowerCase();
  document.querySelectorAll("#earn tr.artist, #shares tr").forEach((tr) => {
    tr.classList.toggle("hide", !!q && !tr.textContent.toLowerCase().includes(q));
  });
}
if ($("q")) $("q").addEventListener("input", applyFilter);

let lastLedger = null;
function renderLedger(l) {
  lastLedger = l;
  const el = $("ledger");
  if (l.intact) {
    el.className = "ledger ok";
    el.textContent = `Log intact${l.last_anchor ? `, anchored ${fmtHm(l.last_anchor.hour)}` : ""}`;
  } else {
    el.className = "ledger bad";
    el.textContent = "Log changed: results withheld";
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
    parts.push(`<circle class="venue${on ? " on" : " off"}${live ? " live" : ""}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${live ? 8 : 5.5}">
      <title>${esc(v.name)}, ${esc(v.city)}${meters ? ` (${esc(meters)})` : ""}</title></circle>`);
  }
  svg.setAttribute("viewBox", `0 0 ${VIEW.w} ${VIEW.h}`);
  svg.innerHTML = parts.join("");
  $("map-note").textContent = `${venues.length} bars, ${online} with a meter online`;
}

let toastTimer = null;
function showPlayOnMap(venueId, text) {
  const ring = document.querySelector(`circle[data-ring="${CSS.escape(venueId || "")}"]`);
  if (ring) { ring.classList.remove("go"); void ring.getBoundingClientRect(); ring.classList.add("go"); }
  const v = venuesById.get(venueId);
  const t = $("map-toast");
  t.textContent = `${text}${v ? ` at ${v.name}, ${v.city}` : ""}`;
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
      <td><div class="bar" title="${esc(s.title)}: ${fmtPct(s.share)} of counted plays"><i style="width:${(100 * s.share / max).toFixed(1)}%"></i></div></td></tr>`).join("") : "";
    return `<tr class="artist${r.rank <= 3 ? " top3" : ""}" data-artist="${esc(r.artist_name)}">
      <td>${r.rank}</td><td class="name"><span class="caret">${open ? "▾" : "▸"}</span>${esc(r.artist_name)}<a href="${link}">page</a></td>
      <td class="n">${r.n_songs}</td><td class="n">${fmtInt(r.raw_plays)}</td><td class="n">${fmtInt(r.counted_plays)}</td>
      <td class="n share">${fmtPct(r.share)}</td><td><div class="bar" title="${esc(r.artist_name)}: ${fmtPct(r.share)} of counted plays"><i style="width:${w}%"></i></div></td></tr>${songs}`;
  }).join("") || `<tr><td colspan="7" class="note">${e.frozen ? "Withheld until the log is restored." : "No plays counted in this period yet. Shares appear after the first counted play."}</td></tr>`;
  $("usage-dl").href = `/api/v1/export/usage_report.csv?period=${state.period}&mode=${state.mode}`;
  // Hero sentence: the answer to "who earned what", computed from the rows shown.
  const top = e.frozen ? null : e.rows[0];
  $("earn-hero").textContent = e.frozen ? "Results are withheld until the play log is restored."
    : top ? `${top.artist_name} leads with ${fmtPct(top.share)} of counted plays. ${fmtInt(e.rows.filter((r) => r.counted_plays > 0).length)} artists have plays in this period.`
    : "No artist has counted plays in this period yet.";
  $("earn-note").textContent = `An artist earns for all their songs together, so their songs' shares are added up. Click an artist to see the songs.${e.stats_run_id ? ` Rule ${e.rule_version}, run ${e.stats_run_id}.` : ""}`;
  renderDots(e);
  renderSparks(e);
  applyFilter();
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
  $("shares-note").textContent = `A song's share is its counted plays divided by all counted plays. Rule ${s.rule_version}${s.stats_run_id ? `, run ${s.stats_run_id}` : ""}.`;
  applyFilter();
}

// ---------- trust ----------
function renderTrustStatus() {
  const l = lastLedger;
  if (!l) return;
  const st = $("trust-status");
  st.className = "status" + (l.intact ? "" : " bad");
  st.textContent = l.intact ? "✓ Play log intact" : `⚠ Play log changed${l.broken_at_play_id ? ` at play ${l.broken_at_play_id}` : ""}. Results are withheld.`;
  if (l.plays_checked != null) $("t-checked").textContent = fmtInt(l.plays_checked);
  if (l.last_root) $("t-root").textContent = l.last_root;
  $("t-anchor").textContent = l.last_anchor ? `${fmtDateTime(l.last_anchor.hour)}, published in the ${l.last_anchor.via}${l.last_anchor.tx_ref ? ` (${l.last_anchor.tx_ref})` : ""}` : "None yet";
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
    case "play": return { tag: "play", text: `${esc(data.title)}${data.artist_name ? `, ${esc(data.artist_name)}` : ""}`, sub: esc(where) };
    case "match": return data.accepted ? { tag: "heard", text: `${esc(data.title)}`, sub: `Meter ${esc(data.meter_id)}, ${Math.round(data.offset_s)} s into the song` } : null;
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
    const label = { play: "Play", heard: "Heard", late: "Late", flag: "Flag", ledger: "Log", meter: "Meter", stats: "Shares", reset: "Reset" };
    $("feed").innerHTML = feedItems.map((i, k) => `<li${k === 0 ? ' class="new"' : ""}><span class="tag ${i.tag}">${label[i.tag.split(" ")[0]] || i.tag}</span>
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
  if ($("crumb")) $("crumb").textContent = tab[0].toUpperCase() + tab.slice(1);
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

// ?period=mock_month opens the dashboard on the closed mock month (used for screenshots and the pitch).
if (new URLSearchParams(location.search).get("period") === "mock_month") { state.period = "mock_month"; setOn("period", "mock_month"); }
const startTab = location.hash.slice(1);
if (["overview", "songs", "trust"].includes(startTab)) showTab(startTab);
$("mode-note").textContent = MOCK ? " · mock data (?mock=1)" : "";
tickClock();
greet();
setInterval(tickClock, 1000);
loadAll();
setInterval(() => { if (state.period === "live") { loadOverview(); loadVenues(); } }, 30000);
feed(addFeed);
