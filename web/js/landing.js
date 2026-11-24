// Landing page. Every number shown is computed by the system (API, or the fixtures with ?mock=1).
// No scroll animation and no counters: values are written once when the data arrives.
import { MOCK, get } from "./api.js";
import { VIEW, project, outlinePath } from "./cameroon.js";

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
  } catch (_) { $("ps-foot").textContent = "Shares appear once a period has been computed."; }
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

numbers(); mapTile(); compareTile(); sharesTiles(); trustTiles();

if (MOCK) {
  document.title += " (mock data)";
  document.querySelectorAll('a[href$=".html"]').forEach((a) => { a.href += (a.href.includes("?") ? "&" : "?") + "mock=1"; });
}
