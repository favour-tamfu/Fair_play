// SONACAM dashboard v1 (A-T11): KPI row, venue map, live feed, shares table with Raw | Standardised.
import { MOCK, get, feed, fmtTime, fmtHm } from "./api.js";

const state = { period: "live", mode: "standardised" };
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(2) + " %");

// Cameroon bounding box for the map (lon 8.3-16.3, lat 1.5-13.2), drawn to the 400x420 viewBox.
function project(lat, lon) {
  const x = ((lon - 8.3) / (16.3 - 8.3)) * 380 + 10;
  const y = ((13.2 - lat) / (13.2 - 1.5)) * 400 + 10;
  return [x, y];
}

function renderKpis(o) {
  document.getElementById("k-meters").textContent = `${o.meters_online} / ${o.meters_total}`;
  document.getElementById("k-raw").textContent = fmtInt(o.plays_raw);
  document.getElementById("k-counted").textContent = fmtInt(o.plays_counted);
  document.getElementById("k-songs").textContent = fmtInt(o.songs_ready);
  document.getElementById("rule").textContent = `rule ${o.rule_version}`;
}

function renderLedger(intact, anchor) {
  const el = document.getElementById("ledger");
  if (intact) {
    el.className = "ledger ok";
    el.textContent = `Log intact${anchor ? ` · last anchor ${fmtHm(anchor.hour)} (${anchor.via})` : ""}`;
  } else {
    el.className = "ledger bad";
    el.textContent = "Log mismatch · results withheld";
  }
}

function renderMap(venues) {
  const svg = document.getElementById("map");
  svg.innerHTML = "";
  for (const v of venues) {
    const [x, y] = project(v.lat, v.lon);
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", x.toFixed(1));
    c.setAttribute("cy", y.toFixed(1));
    c.setAttribute("r", v.venue_id === "V-BUEA-CIMFEST" ? 7 : 4.5);
    c.setAttribute("class", "venue" + (v.venue_id === "V-BUEA-CIMFEST" ? " live" : ""));
    c.dataset.venue = v.venue_id;
    const t = document.createElementNS("http://www.w3.org/2000/svg", "title");
    t.textContent = `${v.name} · ${v.city}`;
    c.appendChild(t);
    svg.appendChild(c);
  }
}

function pulseVenue(venueId) {
  const c = document.querySelector(`circle[data-venue="${venueId}"]`);
  if (!c) return;
  c.classList.remove("pulse");
  void c.getBoundingClientRect();
  c.classList.add("pulse");
  setTimeout(() => c.classList.remove("pulse"), 4000);
}

const feedItems = [];
function addFeed(evt) {
  const { event, data } = evt;
  let text = "";
  if (event === "batch") text = `${data.meter_id} seq ${data.seq}${data.late ? " (late)" : ""}`;
  else if (event === "match") text = data.accepted ? `${data.title} at ${data.offset_s} s` : "no match";
  else if (event === "play") text = `${data.title} · ${data.artist_name || ""}`;
  else if (event === "flag") text = `${data.type}: ${data.detail}`;
  else if (event === "ledger") text = data.intact ? "log intact" : `log broken at ${data.broken_at_play_id}`;
  else if (event === "meter") text = `${data.meter_id} ${data.online ? "online" : "offline"} · queued ${data.queued}`;
  else if (event === "stats") text = `stats run ${data.stats_run_id}`;
  if (!text) return;
  feedItems.unshift({ event, text, time: fmtTime(data.window_start || data.started_at || data.last_seen || data.created_at) });
  feedItems.length = Math.min(feedItems.length, 12);
  const ol = document.getElementById("feed");
  ol.innerHTML = feedItems.map((i) => `<li><span class="tag ${i.event}">${i.event}</span> ${i.text} <span class="note">${i.time}</span></li>`).join("");
  if (event === "play" || event === "match") pulseVenue(data.venue_id);
  if (event === "stats") { loadShares(); loadEarnings(); }
  if (event === "ledger") { loadLedgerBanner(); loadEarnings(); }
}

// D-011: every bar is metered and there is no sampling, so ci_low = ci_high = share: no range bar.
// D-009: audience and concentration are review flags only; they never change the counts.
// D-015: no money in this version. A song's share of all counted plays is shown; artists earn the sum of
// their songs' shares (see renderEarnings).
function renderShares(s) {
  const rows = s.rows.slice(0, 15);
  const max = Math.max(...rows.map((r) => r.share), 0.01);
  const tb = document.getElementById("shares");
  tb.innerHTML = rows.map((r, i) => {
    const w = (100 * r.share / max).toFixed(1);
    const flags = (r.flags || []).map((f) => `<span class="chip">${f}</span>`).join("");
    return `<tr>
      <td>${i + 1}</td><td>${r.title}</td><td>${r.artist_name}</td>
      <td class="n">${fmtInt(r.raw_plays)}</td><td class="n">${fmtInt(r.weighted_plays)}</td>
      <td>${fmtPct(r.share)}</td>
      <td><div class="bar"><i style="left:0;width:${w}%"></i></div></td><td>${flags}</td></tr>`;
  }).join("");
  document.getElementById("shares-note").textContent =
    `${s.rule_version} · run ${s.stats_run_id} · share = the song's counted plays ÷ all counted plays · flags are for SONACAM review`;
}

// What each artist earned (c-1.3): artists ranked by the sum of their songs' shares; click to show the songs.
const openArtists = new Set();
function renderEarnings(e) {
  document.getElementById("earn-frozen").classList.toggle("show", !!e.frozen);
  document.getElementById("rules").innerHTML = (e.rules || []).map((r) => `<li>${r}</li>`).join("");
  const max = Math.max(...e.rows.map((r) => r.share), 0.01);
  document.getElementById("earn").innerHTML = e.rows.map((r) => {
    const w = (100 * r.share / max).toFixed(1);
    const link = `artist.html?name=${encodeURIComponent(r.artist_name)}&period=${state.period}`;
    const open = openArtists.has(r.artist_name);
    const songs = open ? r.songs.map((s) => `<tr class="sub"><td></td><td colspan="3">${s.title}</td>
      <td class="n">${fmtInt(s.counted_plays)}</td><td>${fmtPct(s.share)}</td><td></td></tr>`).join("") : "";
    return `<tr class="artist" data-artist="${r.artist_name.replace(/"/g, "&quot;")}">
      <td>${r.rank}</td><td>${open ? "▾" : "▸"} ${r.artist_name} <a class="note" href="${link}">page</a></td>
      <td class="n">${r.n_songs}</td><td class="n">${fmtInt(r.raw_plays)}</td><td class="n">${fmtInt(r.counted_plays)}</td>
      <td><b>${fmtPct(r.share)}</b></td><td><div class="bar"><i style="left:0;width:${w}%"></i></div></td></tr>${songs}`;
  }).join("") || `<tr><td colspan="7" class="note">${e.frozen ? "" : "No stats run for this period yet."}</td></tr>`;
  document.querySelectorAll("#earn tr.artist").forEach((tr) => tr.addEventListener("click", (ev) => {
    if (ev.target.tagName === "A") return;
    const n = tr.dataset.artist;
    if (openArtists.has(n)) openArtists.delete(n); else openArtists.add(n);
    renderEarnings(e);
  }));
  document.getElementById("usage-dl").href = `/api/v1/export/usage_report.csv?period=${state.period}&mode=${state.mode}`;
}

// Flat advance vs Fair Play on the mock month's known truth (brief §7.4), shown as % of the pot that
// would go to the wrong artists (no money, D-015). The server computes both numbers.
function renderCompare(c) {
  const el = document.getElementById("compare");
  if (state.period !== "mock_month" || !c || !c.n_artists) { el.innerHTML = ""; return; }
  const pf = c.misallocated_flat_fcfa / c.pot_fcfa, pp = c.misallocated_fairplay_fcfa / c.pot_fcfa;
  el.innerHTML = `<b>Flat split vs Fair Play</b> (mock month, ${c.n_artists} artists, against what really played):
    a flat equal split gives <b>${fmtPct(pf)}</b> of the pot to the wrong artists; Fair Play <b>${fmtPct(pp)}</b>.`;
}

async function loadEarnings() {
  try {
    const [e, c] = await Promise.all([get("artist_shares", state.period, state.mode),
      state.period === "mock_month" ? get("compare_flat") : Promise.resolve(null)]);
    renderEarnings(e);
    renderCompare(c);
  } catch (err) { document.getElementById("earn-note").textContent = String(err); }
}

async function loadShares() {
  try { renderShares(await get("shares", state.period, state.mode)); } catch (e) { document.getElementById("shares-note").textContent = String(e); }
}

async function loadLedgerBanner() {
  try {
    const l = await get("ledger_status", state.period);
    renderLedger(l.intact, l.last_anchor);
  } catch (_) { /* keep the old banner */ }
}

async function loadAll() {
  try {
    const [o, v] = await Promise.all([get("overview", state.period), get("venues", state.period)]);
    renderKpis(o);
    renderLedger(o.ledger_intact, o.last_anchor);
    renderMap(v);
  } catch (e) {
    document.getElementById("rule").textContent = String(e);
  }
  loadShares();
  loadEarnings();
}

function setButtons(group, attr, value) {
  document.querySelectorAll(`[data-${group}]`).forEach((b) => b.classList.toggle("on", b.dataset[group] === value));
}

document.querySelectorAll("[data-period]").forEach((b) => b.addEventListener("click", () => {
  state.period = b.dataset.period;
  setButtons("period", "period", state.period);
  loadAll();
}));
document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
  state.mode = b.dataset.mode;
  setButtons("mode", "mode", state.mode);
  loadShares();
  loadEarnings();
}));

document.getElementById("mode-note").textContent = MOCK ? " · mock data (?mock=1)" : " · live data";
loadAll();
feed(addFeed);
