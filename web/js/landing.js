// Landing page: the live numbers on the page come from the API (or the fixtures with ?mock=1),
// so every figure shown is computed by the system. The phone screen shows the top artist of the mock month.
import { MOCK, get } from "./api.js";

const $ = (id) => document.getElementById(id);
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(2) + " %");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function liveTile() {
  try {
    const o = await get("overview", "live");
    $("live-counted").textContent = fmtInt(o.plays_counted);
    $("live-label").textContent = `so far by ${o.meters_online} meters online`;
  } catch (_) { $("live-label").textContent = "when the meters are online"; }
}

async function phone() {
  $("ps-time").textContent = new Date().toLocaleTimeString("fr-FR", { timeZone: "Africa/Douala", hour: "2-digit", minute: "2-digit" });
  try {
    const s = await get("artist_shares", "mock_month", "standardised");
    const a = !s.frozen && s.rows[0];
    if (!a) { $("ps-foot").textContent = "No shares yet for this period."; return; }
    $("ps-name").textContent = a.artist_name;
    $("ps-avatar").textContent = a.artist_name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    $("ps-share").textContent = fmtPct(a.share);
    $("ps-rank").textContent = `#${a.rank} of ${s.rows.length}`;
    const max = Math.max(...a.songs.map((x) => x.share), 0.0001);
    $("ps-songs").innerHTML = a.songs.slice(0, 4).map((x) => `<div class="ps-row"><div><span>${esc(x.title)}</span><b>${fmtPct(x.share)}</b></div>
      <i style="width:${(100 * x.share / max).toFixed(0)}%"></i></div>`).join("");
    $("ps-foot").textContent = `Example from the mock month, rule ${s.rule_version}.`;
  } catch (_) { $("ps-foot").textContent = "Could not load the example."; }
}

liveTile();
phone();
if (MOCK) {
  document.title += " (mock data)";
  // keep mock mode when moving between our own pages
  document.querySelectorAll('a[href$=".html"]').forEach((a) => { a.href += (a.href.includes("?") ? "&" : "?") + "mock=1"; });
}
