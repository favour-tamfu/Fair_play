// Landing page. Every number shown is computed by the system (API, or the fixtures with ?mock=1).
// Motion: tiles reveal once when scrolled into view; stat numbers count up once; both off with reduced motion.
import { MOCK, get } from "./api.js";
import { VIEW, project, outlinePath } from "./cameroon.js";

document.documentElement.classList.add("js");
const $ = (id) => document.getElementById(id);
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x, d = 2) => (x == null ? "–" : (100 * x).toFixed(d) + " %");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const LIVE_VENUE = "V-BUEA-CIMFEST";

// ---------- reveal + count-up ----------
const counters = new Map();   // element -> target value
function countUp(el) {
  const target = counters.get(el);
  if (target == null || el.dataset.done) return;
  el.dataset.done = "1";
  if (reduced) { el.textContent = fmtInt(target); return; }
  const t0 = performance.now(), dur = 1400;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmtInt(target * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
const io = new IntersectionObserver((entries) => {
  for (const en of entries) {
    if (!en.isIntersecting) continue;
    en.target.classList.add("in");
    en.target.querySelectorAll(".count").forEach((c) => { c.dataset.visible = "1"; countUp(c); });
    io.unobserve(en.target);
  }
}, { threshold: 0.18 });
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
function setCount(id, value) {
  const el = $(id);
  counters.set(el, value);
  if (el.dataset.visible || reduced) countUp(el);
}

// ---------- highlights gallery ----------
const track = $("hl-track"), cards = [...track.querySelectorAll(".hl-card")];
$("hl-dots").innerHTML = cards.map(() => "<i></i>").join("");
const dots = [...$("hl-dots").children];
const current = () => {
  const mid = track.scrollLeft + track.clientWidth / 2;
  let best = 0, d = Infinity;
  cards.forEach((c, i) => { const dd = Math.abs(c.offsetLeft + c.offsetWidth / 2 - mid); if (dd < d) { d = dd; best = i; } });
  return best;
};
const paint = () => { const i = current(); dots.forEach((x, k) => x.classList.toggle("on", k === i)); };
const go = (i) => { const c = cards[Math.max(0, Math.min(cards.length - 1, i))]; track.scrollTo({ left: c.offsetLeft - (track.clientWidth - c.offsetWidth) / 2, behavior: reduced ? "auto" : "smooth" }); };
$("hl-prev").addEventListener("click", () => go(current() - 1));
$("hl-next").addEventListener("click", () => go(current() + 1));
track.addEventListener("scroll", () => requestAnimationFrame(paint), { passive: true });
track.addEventListener("keydown", (e) => { if (e.key === "ArrowRight") go(current() + 1); if (e.key === "ArrowLeft") go(current() - 1); });
paint();

// ---------- local nav: highlight the section in view ----------
const navLinks = [...document.querySelectorAll('.ln-links a[href^="#"]')];
const spy = new IntersectionObserver((entries) => {
  for (const en of entries) if (en.isIntersecting) navLinks.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === `#${en.target.id}`));
}, { rootMargin: "-45% 0px -50% 0px" });
navLinks.forEach((a) => { const s = document.querySelector(a.getAttribute("href")); if (s) spy.observe(s); });

// ---------- data ----------
async function numbers() {
  try {
    const o = await get("overview", "live");
    setCount("n-counted", o.plays_counted);
    setCount("n-meters", o.meters_online);
  } catch (_) { /* leave dashes */ }
}

async function mapTile() {
  try {
    const venues = await get("venues", "live");
    setCount("n-bars", venues.length);
    const cities = new Set(venues.map((v) => v.city));
    $("map-title").textContent = `${venues.length} bars in ${cities.size} cities.`;
    const parts = [`<path class="land" d="${outlinePath()}"/>`];
    for (const v of [...venues].sort((a, b) => (a.venue_id === LIVE_VENUE) - (b.venue_id === LIVE_VENUE))) {
      const [x, y] = project(v.lat, v.lon);
      const on = (v.meters || []).some((m) => m.online), live = v.venue_id === LIVE_VENUE;
      if (live) parts.push(`<circle class="halo" cx="${x}" cy="${y}" r="10"/>`);
      parts.push(`<circle class="v${live ? " live" : on ? "" : " off"}" cx="${x}" cy="${y}" r="${live ? 10 : 7}"><title>${esc(v.name)}, ${esc(v.city)}</title></circle>`);
    }
    $("mini-map").setAttribute("viewBox", `0 0 ${VIEW.w} ${VIEW.h}`);
    $("mini-map").innerHTML = parts.join("");
  } catch (_) { $("map-title").textContent = "Every metered bar."; }
}

async function compareTile() {
  try {
    const c = await get("compare_flat");
    if (!c || !c.n_artists || !c.pot_fcfa) throw new Error("not computed");
    const pf = c.misallocated_flat_fcfa / c.pot_fcfa, pp = c.misallocated_fairplay_fcfa / c.pot_fcfa;
    $("cmp-flat-v").textContent = fmtPct(pf, 1);
    $("cmp-fp-v").textContent = fmtPct(pp, 1);
    $("cmp-ratio").textContent = pp > 0 ? `${(pf / pp).toFixed(1).replace(".", ",")}×` : "–";
    const scale = Math.max(pf, pp);
    const fill = () => { $("cmp-flat").style.width = `${(100 * pf / scale).toFixed(1)}%`; $("cmp-fp").style.width = `${(100 * pp / scale).toFixed(1)}%`; };
    const t = document.querySelector(".b-compare");
    if (reduced) fill(); else new IntersectionObserver((e, o) => { if (e[0].isIntersecting) { fill(); o.disconnect(); } }, { threshold: .4 }).observe(t);
    $("cmp-note").textContent = `Share of the pot that would go to the wrong artists in the mock month (${c.n_artists} artists), measured against what really played.`;
  } catch (_) { $("cmp-note").textContent = "The comparison appears once the mock month has been computed."; }
}

async function sharesTiles() {
  try {
    const s = await get("artist_shares", "mock_month", "standardised");
    if (s.frozen) throw new Error("frozen");
    setCount("n-artists", s.rows.filter((r) => r.counted_plays > 0).length);
    const max = Math.max(...s.rows.map((r) => r.share), 0.0001);
    $("toplist").innerHTML = s.rows.slice(0, 4).map((r) => `<li><span>${esc(r.artist_name)}</span><b>${fmtPct(r.share)}</b><i style="width:${(100 * r.share / max).toFixed(0)}%"></i></li>`).join("");
    // phone
    const a = s.rows[0];
    if (a) {
      $("ps-name").textContent = a.artist_name;
      $("ps-avatar").textContent = a.artist_name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
      $("ps-share").textContent = fmtPct(a.share);
      $("ps-rank").textContent = `#${a.rank} of ${s.rows.length}`;
      const m = Math.max(...a.songs.map((x) => x.share), 0.0001);
      $("ps-songs").innerHTML = a.songs.slice(0, 3).map((x) => `<div class="ps-row"><div><span>${esc(x.title)}</span><b>${fmtPct(x.share)}</b></div><i style="width:${(100 * x.share / m).toFixed(0)}%"></i></div>`).join("");
      $("ps-foot").textContent = `Example from the mock month, rule ${s.rule_version}.`;
    }
  } catch (_) { $("ps-foot").textContent = "Shares appear once a period has been computed."; }
  $("ps-time").textContent = new Date().toLocaleTimeString("fr-FR", { timeZone: "Africa/Douala", hour: "2-digit", minute: "2-digit" });
}

async function trustTiles() {
  let l = null;
  try { l = await get("ledger_status", "live"); } catch (_) { /* below */ }
  const root = (l && l.last_root) || "";
  $("hash-status").textContent = !l ? "Not reachable." : l.intact ? "Intact." : "Changed. Results withheld.";
  $("hash-status").classList.toggle("bad", !!l && !l.intact);
  $("hash-root").textContent = root ? root.slice(0, 32) + "…" : "no plays yet";
  $("hash-note").textContent = l && l.plays_checked != null ? `${fmtInt(l.plays_checked)} plays checked against the chain.` : "";
  // Chain picture: only the latest block shows a real value (the current chain hash); earlier blocks show the structure.
  const blocks = [["Play n−3", "sealed to the next"], ["Play n−2", "sealed to the next"], ["Play n−1", "sealed to the next"],
    ["Latest play", root ? `${root.slice(0, 16)}…` : "no plays yet"]];
  $("chain").innerHTML = blocks.map(([t, h], i) => `${i ? '<span class="link"></span>' : ""}<div class="blk${i === 3 ? " last" : ""}"><b>${t}</b>${i === 3 ? "chain hash" : "&nbsp;"}<code>${esc(h)}</code></div>`).join("");
}

numbers(); mapTile(); compareTile(); sharesTiles(); trustTiles();

if (MOCK) {
  document.title += " (mock data)";
  document.querySelectorAll('a[href$=".html"]').forEach((a) => { a.href += (a.href.includes("?") ? "&" : "?") + "mock=1"; });
}
