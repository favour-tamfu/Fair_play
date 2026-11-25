// Landing page. Every number shown is computed by the system (API, or the fixtures with ?mock=1).
// No scroll animation and no counters: values are written once when the data arrives.
import { MOCK, get, feed, fmtHm } from "./api.js";
import { VIEW, project, outlinePath } from "./cameroon.js";
import { loadCovers, initials } from "./covers.js";

const $ = (id) => document.getElementById(id);
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x, d = 2) => (x == null ? "–" : (100 * x).toFixed(d) + " %");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LIVE_VENUE = "V-BUEA-CIMFEST";
const TEST_ARTIST = "Fair Play test artist";        // fictional scenario tracks are never shown on the public page
const TZ = "Africa/Douala";
// "21:35" today, "24/11 21:35" on another day (Cameroon time)
const fmtDayTime = (iso) => {
  if (!iso) return "";
  const day = (d) => new Date(d).toLocaleDateString("fr-FR", { timeZone: TZ });
  return day(iso) === day(Date.now()) ? fmtHm(iso)
    : new Date(iso).toLocaleString("fr-FR", { timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};
// A bar's public name: the live bar by its name; simulated bars by their city only (their names are test labels).
const barName = (v) => (!v ? "" : v.source === "mock" || /^mock bar/i.test(v.name || "") ? `a bar in ${v.city}` : `${v.name}, ${v.city}`);

// ---------- data for both periods (reloaded on play / stats / ledger events) ----------
const data = { live: {}, mock_month: {} };
let period = new URLSearchParams(location.search).get("period") === "mock_month" ? "mock_month" : "live";
document.querySelectorAll(".period-switch button").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.period === period)));
async function load(p) {
  const [overview, venues, shares, flags, plays, ledger] = await Promise.all([
    get("overview", p).catch(() => null), get("venues", p).catch(() => []),
    get("artist_shares", p, "standardised").catch(() => null), get("flags", p).catch(() => []),
    get("plays", p).catch(() => []), get("ledger_status", p).catch(() => null)]);
  data[p] = { overview, venues, shares, flags, plays, ledger };
  return data[p];
}
const setStat = (k, label, value, note) => { $(`${k}-k`).textContent = label; $(k).textContent = value; $(`${k}-n`).textContent = note; };

function renderNumbers() {
  const d = data[period], o = d.overview, vs = d.venues || [];
  if (period === "live") {
    const real = vs.filter((v) => v.source === "live").flatMap((v) => v.meters || []);
    const test = vs.filter((v) => v.source === "virtual").flatMap((v) => v.meters || []);
    const last = (d.plays || []).find((p) => p.artist_name !== TEST_ARTIST);
    const when = last ? fmtDayTime(last.started_at) : "";
    setStat("s1", "Plays counted", fmtInt(o && o.plays_counted), "since the live meters started");
    setStat("s2", "Meters online", fmtInt(real.concat(test).filter((m) => m.online).length),
      `of ${fmtInt(real.length)} real and ${fmtInt(test.length)} test meters`);
    setStat("s3", "Last play", last ? when.slice(-5) : "–",
      last ? `${when.length > 5 ? when.slice(0, 5) + " · " : ""}${last.title} · ${last.artist_name}` : "no play yet");
    setStat("s4", "Play log", d.ledger ? (d.ledger.intact ? "Intact" : "Broken") : "–",
      d.ledger ? `${fmtInt(d.ledger.plays_checked)} plays checked` : "");
    $("period-note").textContent = "Live: what the meter at the CIMFEST stand in Buea is hearing now. Times are Cameroon time.";
  } else {
    const bars = vs.filter((v) => v.plays && v.plays.mock_month > 0);
    const rows = ((d.shares && d.shares.rows) || []).filter((r) => r.artist_name !== TEST_ARTIST && r.counted_plays > 0);
    const songs = rows.reduce((n, r) => n + r.songs.filter((s) => s.counted_plays > 0).length, 0);
    const review = (d.flags || []).filter((f) => !["duplicate_suspected", "cooldown"].includes(f.type));
    setStat("s1", "Plays recorded", fmtInt(o && o.plays_raw), `${fmtInt(o && o.plays_counted)} counted after the repeat rule`);
    setStat("s2", "Bars", fmtInt(bars.length), `in ${new Set(bars.map((v) => v.city)).size} cities`);
    setStat("s3", "Artists", fmtInt(rows.length), `${fmtInt(songs)} songs played`);
    setStat("s4", "Flags to review", fmtInt(review.length), "songs on repeat, empty rooms, odd meters; they do not change shares");
    $("period-note").textContent = d.shares && d.shares.frozen
      ? "Results withheld: the play log failed its integrity check."
      : "Mock month: 30 simulated days in the bars on the map, built on the real catalogue to show a full month. These plays are generated, not heard.";
  }
  mapTile();
}

function mapTile() {
  const vs = data[period].venues || [];
  if (!vs.length) return;
  const key = period === "live" ? "live" : "mock_month";
  const max = Math.max(1, ...vs.map((v) => (v.plays ? v.plays[key] : 0)));
  const parts = [`<path class="land" d="${outlinePath()}"/>`];
  for (const v of [...vs].sort((a, b) => (a.venue_id === LIVE_VENUE) - (b.venue_id === LIVE_VENUE))) {
    const [x, y] = project(v.lat, v.lon);
    const n = v.plays ? v.plays[key] : 0, live = v.venue_id === LIVE_VENUE;
    const on = (v.meters || []).some((m) => m.online);
    let cls = "v", r;
    if (period === "live") { cls += live ? " live" : on ? "" : " off"; r = live ? 9 : 5; }
    else { cls += n ? "" : " off"; r = n ? 4 + 9 * Math.sqrt(n / max) : 4; }
    if (live && period === "live") parts.push(`<circle class="ring" cx="${x}" cy="${y}" r="17"/>`);
    parts.push(`<circle class="${cls}" cx="${x}" cy="${y}" r="${r.toFixed(1)}"><title>${esc(barName(v))}: ${fmtInt(n)} plays</title></circle>`);
  }
  $("mini-map").setAttribute("viewBox", `0 0 ${VIEW.w} ${VIEW.h}`);
  $("mini-map").innerHTML = parts.join("");
  if (period === "live") {
    const on = vs.filter((v) => (v.meters || []).some((m) => m.online)).length;
    $("map-title").textContent = `${on} bar${on === 1 ? "" : "s"} sending right now.`;
    $("map-note").textContent = "Blue: the live meter at the CIMFEST stand. Hollow: bars whose meter is not sending now (the other bars are in the mock month).";
  } else {
    const bars = vs.filter((v) => v.plays && v.plays.mock_month);
    $("map-title").textContent = `${bars.length} bars in ${new Set(bars.map((v) => v.city)).size} cities.`;
    $("map-note").textContent = "Dot size: plays in the mock month.";
  }
}

document.querySelectorAll(".period-switch button").forEach((b) => b.addEventListener("click", () => {
  period = b.dataset.period;
  document.querySelectorAll(".period-switch button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  renderNumbers();
}));

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
    $("cmp-note").textContent = "Share of the pot that would go to the wrong artists in the mock month, measured against what was really played there.";
  } catch (_) { $("cmp-note").textContent = "The comparison appears once the mock month has been computed."; }
}

function sharesTiles() {
  const s = data.mock_month.shares;
  if (!s) return;
  if (s.frozen) { $("mix-intro").textContent = "Results withheld: the play log failed its integrity check."; return; }
  const rows = s.rows.filter((r) => r.artist_name !== TEST_ARTIST);
  if (rows[0]) musicTiles({ ...s, rows });
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
    $("frame-who").textContent = `Most played this month: ${song.title} by ${top.artist_name}.`;
  }
  $("mix-sub").textContent = `${s.rows.filter((r) => r.counted_plays > 0).length} artists, mock month`;
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


// Wall of covers: one per album, laid out on fixed spots around the headline (no randomness between loads).
const SPOTS = [[3, 6, 15], [21, -4, 12], [40, 3, 10], [60, -6, 13], [79, 4, 15], [93, 30, 12], [-3, 36, 14], [8, 70, 13], [27, 82, 11],
  [47, 78, 12], [66, 84, 14], [84, 66, 13], [16, 40, 9], [76, 38, 10]];
async function wallTile() {
  const cv = await loadCovers();
  const pick = cv.albums.slice(0, SPOTS.length);
  $("wall").innerHTML = pick.map((c, i) => { const [x, y, w] = SPOTS[i];
    return `<div class="cv" style="left:${x}%;top:${y}%;width:${w}%;aspect-ratio:1;background-image:url('${c.src}')" title="${esc(c.album)} · ${esc(c.artist)}"></div>`; }).join("");
  try {   // what the meters can recognise right now: songs fingerprinted and ready (the fictional test tracks have no audio)
    const ready = (await get("songs")).filter((s) => s.status === "ready" && s.n_hashes > 0);
    const artists = new Set(ready.map((s) => s.artist_name));
    $("cat-h").innerHTML = `${fmtInt(ready.length)} songs.<br>${fmtInt(artists.size)} artists.`;
    $("wall-note").textContent = `Every one is fingerprinted, so a meter recognises it from ten seconds of sound in a bar.`;
  } catch (_) { /* keep the static headline */ }
}

function trustTiles() {
  const l = data.live.ledger;
  const root = (l && l.last_root) || "";
  // Only the latest block shows a real value (the current chain hash); the others show the structure.
  const blocks = [["Play n−3", "sealed to the next"], ["Play n−2", "sealed to the next"], ["Play n−1", "sealed to the next"],
    ["Latest play", root ? `${root.slice(0, 16)}…` : "no plays yet"]];
  if (l) $("trust-note").textContent = `${l.intact ? "Intact" : "Broken"}: ${fmtInt(l.plays_checked)} plays checked just now.`
    + (l.last_anchor ? ` Last hourly anchor: ${fmtHm(l.last_anchor.hour)} (Cameroon time).` : "");
  $("chain").innerHTML = blocks.map(([t, h], i) => `${i ? '<span class="link"></span>' : ""}<div class="blk${i === 3 ? " last" : ""}"><b>${t}</b>${i === 3 ? "chain hash" : "&nbsp;"}<code>${esc(h)}</code></div>`).join("");
}

// Live from the bars: plays and recognised songs from the event stream (the fixture replay with ?mock=1).
const liveItems = [];
const venueName = new Map();
const songArtist = new Map();
get("songs", "live").then((ss) => ss.forEach((s) => songArtist.set(s.song_id, s.artist_name))).catch(() => {});
// Start with the latest confirmed live plays (oldest first, so the newest ends on top), then follow the live feed.
function startLive() {
  (data.live.venues || []).forEach((v) => venueName.set(v.venue_id, barName(v)));
  const ps = (data.live.plays || []).filter((p) => p.artist_name !== TEST_ARTIST);
  ps.forEach((p) => songArtist.set(p.song_id, p.artist_name));
  if (!ps.length) $("live-list").innerHTML = `<li class="live-empty">No live play yet. Play a catalogue song near the meter.</li>`;
  ps.slice(0, 5).reverse().forEach((p) => onFeed({ event: "play", data: p }));
  feed((e) => {
    onFeed(e);
    if (e.event === "play" || e.event === "stats" || e.event === "ledger") refresh(e.data && e.data.period);
  });
}
let refreshTimer = null;
function refresh(p) {                               // a new play or stats run: reload that period (debounced)
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    await load(p === "mock_month" ? "mock_month" : "live");
    renderNumbers(); trustTiles();
  }, 1500);
}
function onFeed({ event, data }) {
  if (event !== "play" && !(event === "match" && data.accepted)) return;
  const item = { kind: event === "play" ? "Played" : "Heard", title: data.title || data.song_id, artist: data.artist_name || songArtist.get(data.song_id) || "",
    where: venueName.get(data.venue_id) || data.venue_id || "", time: fmtDayTime(data.started_at || data.window_start) };
  if (item.artist === TEST_ARTIST) return;
  // One line per song: a song heard and then confirmed as a play stays on one line.
  if (liveItems[0] && liveItems[0].title === item.title && liveItems[0].where === item.where) liveItems[0] = item;
  else liveItems.unshift(item);
  liveItems.length = Math.min(liveItems.length, 5);
  $("live-list").innerHTML = liveItems.map((i) => `<li>${esc(i.title)}<span>${esc(i.artist)} · ${i.kind.toLowerCase()} at ${esc(i.where.split(",")[0])} · ${i.time}</span></li>`).join("");
  $("lyric-title").textContent = item.title;
  $("lyric-artist").textContent = item.artist;
  loadCovers().then((cv) => setCover($("lyric-art"), cv.song(item.artist, item.title) || cv.artist(item.artist), item.artist || item.title));
}

Promise.all([load("live"), load("mock_month")]).then(() => { renderNumbers(); sharesTiles(); trustTiles(); startLive(); });
compareTile(); wallTile();

if (MOCK) {
  document.title += " (mock data)";
  document.querySelectorAll('a[href$=".html"]').forEach((a) => { a.href += (a.href.includes("?") ? "&" : "?") + "mock=1"; });
}

// Starter cards: previous/next arrows scroll one card; each arrow is disabled at its end.
{
  const row = document.querySelector(".am-cards");
  const paddles = document.querySelectorAll(".paddlenav .paddle");
  const step = () => { const c = row && row.querySelector("article"); return c ? c.getBoundingClientRect().width + 20 : 300; };
  const update = () => {
    if (!row) return;
    const max = row.scrollWidth - row.clientWidth - 2;
    paddles.forEach((p) => { p.disabled = p.dataset.dir === "-1" ? row.scrollLeft <= 2 : row.scrollLeft >= max; });
    document.querySelector(".paddlenav").hidden = max <= 0;
  };
  paddles.forEach((p) => p.addEventListener("click", () => row.scrollBy({ left: Number(p.dataset.dir) * step(), behavior: "smooth" })));
  if (row) { row.addEventListener("scroll", update, { passive: true }); addEventListener("resize", update); update(); }
}
