// SONACAM dashboard v1 (A-T11): KPI row, venue map, live feed, shares table with Raw | Standardised.
import { MOCK, get, feed } from "./api.js";

const state = { period: "live", mode: "standardised" };
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(2) + " %");
const fmtFcfa = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR") + " FCFA");

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
    el.textContent = `Log intact${anchor ? ` · last anchor ${anchor.hour.slice(11, 16)} (${anchor.via})` : ""}`;
  } else {
    el.className = "ledger bad";
    el.textContent = "Log mismatch · payouts frozen";
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
  feedItems.unshift({ event, text, time: (data.window_start || data.started_at || data.last_seen || data.created_at || "").slice(11, 19) });
  feedItems.length = Math.min(feedItems.length, 12);
  const ol = document.getElementById("feed");
  ol.innerHTML = feedItems.map((i) => `<li><span class="tag ${i.event}">${i.event}</span> ${i.text} <span class="note">${i.time}</span></li>`).join("");
  if (event === "play" || event === "match") pulseVenue(data.venue_id);
  if (event === "stats") loadShares();
  if (event === "ledger") loadLedgerBanner();
}

// D-011: every bar is metered and there is no sampling, so ci_low = ci_high = share: no range bar.
// D-009: audience and concentration are review flags only; they never change the money.
// Money is only final when a period's statistics are final. The live period is still open, so it
// shows shares only; a closed period (the mock month here) shows the amounts for that period.
// When B adds a period status to the API, use it instead of this rule.
function periodIsClosed(period) {
  return period !== "live";
}

function renderShares(s) {
  const closed = periodIsClosed(state.period);
  document.getElementById("th-amount").textContent = closed ? "FCFA (final)" : "FCFA";
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
      <td><div class="bar"><i style="left:0;width:${w}%"></i></div></td>
      <td class="n">${closed ? fmtFcfa(r.amount_fcfa) : '<span class="note">at period close</span>'}</td><td>${flags}</td></tr>`;
  }).join("");
  document.getElementById("shares-note").textContent = closed
    ? `${s.rule_version} · run ${s.stats_run_id} · closed period · pot ${fmtFcfa(s.pot_fcfa)} · amounts are final for this period · flags are for SONACAM review`
    : `${s.rule_version} · run ${s.stats_run_id} · period still open · shares can still change · amounts are calculated when the period closes and its statistics are final`;
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
}));

document.getElementById("mode-note").textContent = MOCK ? " · mock data (?mock=1)" : " · live data";
loadAll();
feed(addFeed);
