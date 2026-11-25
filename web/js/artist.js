// Artist page (A-T14): what one artist earns from bar plays, on their phone.
// Share = the artist's songs' counted plays / all counted plays (D-015, c-1.3); no money in this version.
// Now-playing card lights up live when a meter confirms a play of one of their songs (SSE "play").
import { MOCK, get, feed, fmtHm, fmtDateTime } from "./api.js";
import { VIEW, project, outlinePath } from "./cameroon.js";
import { loadCovers } from "./covers.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const name = params.get("name");   // no name: show the artist finder (public artist portal)
let period = params.get("period") === "mock_month" ? "mock_month" : "live";
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(x < 0.1 ? 2 : 1) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
// Square artwork: one of the site photos, picked from the name so it stays the same for the same song or bar.
const ART = ["bottles", "dj", "mic", "outdoor-bar", "yaounde", "party"];
const artFor = (s) => `assets/img/${ART[[...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % ART.length]}.webp`;

const venueNames = new Map();     // venue_id -> "Name, City"
let mySongs = new Set();
let lastPlay = null;              // {title, venue_id, started_at, duration_s}

function timeAgo(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function renderNow(live) {
  const card = $("now");
  if (!lastPlay) {
    $("now-title").textContent = "Not heard yet";
    $("now-where").textContent = period === "live" ? "Your songs will show here the moment a bar plays them." : "No plays in this period.";
    $("now-start").textContent = ""; $("now-ago").textContent = "";
    $("now-progress").style.width = "0";
    return;
  }
  card.classList.toggle("live", !!live);
  $("now-label").textContent = live ? "Playing now in a bar" : "Last heard";
  $("now-title").textContent = lastPlay.title;
  $("now-where").textContent = venueNames.get(lastPlay.venue_id) || lastPlay.venue_id || "";
  $("now-start").textContent = fmtHm(lastPlay.started_at);
  $("now-ago").textContent = timeAgo(lastPlay.started_at);
  const dur = lastPlay.duration_s || 0;
  const el = dur ? Math.min(1, (Date.now() - new Date(lastPlay.started_at).getTime()) / 1000 / dur) : 1;
  $("now-progress").style.width = `${(100 * el).toFixed(1)}%`;
}

async function load() {
  const url = MOCK ? "../contract/fixtures/api/artist.json" : `/api/v1/artists/${encodeURIComponent(name)}?period=${period}`;
  let a, shares = null;
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    a = await r.json();
  } catch (e) {
    $("name").textContent = name;
    $("songs-line").textContent = "Could not load this artist.";
    return;
  }
  try { shares = await get("artist_shares", period, "standardised"); } catch (_) { /* rank and song shares stay empty */ }
  const artistName = a.artist_name || name;
  const cv = await loadCovers();
  // Real album cover for this artist's song when there is one, otherwise a site photo.
  const coverFor = (title) => { const c = cv.song(artistName, title) || cv.artist(artistName); return c ? c.src : artFor(title); };
  const ownCover = cv.artist(artistName);
  const row = shares && !shares.frozen ? shares.rows.find((r) => r.artist_name === artistName) : null;

  document.title = `${artistName} · Fair Play`;
  $("name").textContent = artistName;
  $("avatar").textContent = initials(artistName);
  $("watermark").textContent = artistName;
  $("songs-line").textContent = `${(a.songs || []).length} song${(a.songs || []).length === 1 ? "" : "s"} in the catalogue`;
  mySongs = new Set((a.songs || []).map((s) => s.song_id));
  for (const v of a.plays_by_venue || []) venueNames.set(v.venue_id, `${v.name}, ${v.city}`);

  // Tiles: share, rank, counted plays, each with a line saying what the number is made of.
  const counted = (a.plays_by_venue || []).reduce((t, v) => t + (v.plays_counted || 0), 0);
  const heard = (a.plays_by_venue || []).reduce((t, v) => t + (v.plays_raw || 0), 0);
  let share = a.share ?? (row ? row.share : null), total = null;
  try { total = (await get("overview", period)).plays_counted; } catch (_) { /* no total */ }
  if (share == null && total) share = counted / total;   // not in the last stats run yet: computed from the counts shown
  $("share").textContent = shares && shares.frozen ? "Held" : fmtPct(share);
  $("share-sub").textContent = shares && shares.frozen ? "Withheld until the play log is restored."
    : total ? `of ${fmtInt(total)} plays counted in this period` : "";
  $("rank").textContent = row ? `#${row.rank}` : "–";
  $("rank-label").textContent = row && shares ? `of ${shares.rows.length} artists` : "Ranked after the next stats run";
  $("counted").textContent = fmtInt(counted);
  $("counted-sub").textContent = `${fmtInt(heard)} heard, in ${(a.plays_by_venue || []).length} bars`;
  drawMap(a.plays_by_venue || []);

  // Songs, with each song's share when the stats run has it.
  const songShare = new Map((row ? row.songs : []).map((s) => [s.song_id, s]));
  const maxSong = Math.max(0.0001, ...[...songShare.values()].map((s) => s.share));
  // Top songs: rows with square artwork (song plays counted from the recent list when there is no stats row).
  const recentCount = new Map();
  for (const p of a.recent || []) recentCount.set(p.song_id, (recentCount.get(p.song_id) || 0) + 1);
  $("songs").innerHTML = (a.songs || []).map((s, i) => {
    const st = songShare.get(s.song_id);
    const line = st ? `${fmtPct(st.share)} · ${fmtInt(st.counted_plays)} counted`
      : recentCount.get(s.song_id) ? `${recentCount.get(s.song_id)} of the last ${(a.recent || []).length} plays` : "No counted plays yet";
    return `<div class="am-row"><img src="${coverFor(s.title)}" alt=""><span class="am-n">${i + 1}</span><div><b>${esc(s.title)}</b><span>${line}</span></div></div>`;
  }).join("") || `<div class="empty">No songs yet.</div>`;

  // Bars: a shelf of square tiles, most counted first.
  const venues = [...(a.plays_by_venue || [])].sort((x, y) => (y.plays_counted || 0) - (x.plays_counted || 0));
  $("venues").innerHTML = venues.map((v) => `<figure class="am-tile"><div class="am-art" style="background-image:url('${artFor(v.venue_id)}')"><span>${fmtInt(v.plays_counted)}</span></div>
    <figcaption><b>${esc(v.name)}</b><span>${esc(v.city)} · ${fmtInt(v.plays_counted)} counted</span></figcaption></figure>`).join("")
    || `<div class="empty wrap">No bar has played this artist in this period yet.</div>`;
  $("am-hero").style.backgroundImage = `linear-gradient(180deg, rgba(0,0,0,0) 35%, rgba(0,0,0,.72) 100%), url('${ownCover ? ownCover.src : artFor(artistName)}')`;
  $("am-hero").classList.toggle("has-cover", !!ownCover);

  const days = a.plays_by_day || [];
  const maxD = Math.max(1, ...days.map((d) => d.plays_counted || 0));
  $("chart").innerHTML = days.map((d) => `<i title="${esc(d.date)}: ${fmtInt(d.plays_counted)} counted" style="height:${(100 * (d.plays_counted || 0)) / maxD}%"></i>`).join("");
  $("chart-range").textContent = days.length ? `${fmtInt(days.reduce((t, d) => t + (d.plays_counted || 0), 0))} counted` : "";
  $("chart-x").innerHTML = days.map((d) => `<span>${new Date(d.date + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short" })}</span>`).join("");

  const recent = (a.recent || []).slice(0, 12);
  $("recent").innerHTML = recent.map((p) => `<div class="am-row"><img src="${coverFor(p.title || p.song_id)}" alt=""><div><b>${esc(p.title || p.song_id)}</b>
    <span>${esc((venueNames.get(p.venue_id) || p.venue_id || "").split(",")[0])}</span><span>${fmtDateTime(p.started_at)}</span></div></div>`).join("")
    || `<div class="empty">No recent plays.</div>`;
  lastPlay = recent[0] || null;
  renderNow(false);

  $("foot").textContent = `${shares && shares.stats_run_id ? `${shares.rule_version} · run ${shares.stats_run_id} · ` : ""}times in Cameroon time${MOCK ? " · mock data" : ""}`;
}

// Map of the bars that played this artist: dot size follows counted plays.
async function drawMap(byVenue) {
  const svg = $("pmap");
  if (!svg) return;
  let venues = [];
  try { venues = await get("venues", period); } catch (_) { /* outline only */ }
  const coords = new Map(venues.map((v) => [v.venue_id, v]));
  const max = Math.max(1, ...byVenue.map((v) => v.plays_counted || 0));
  const parts = [`<path class="land" d="${outlinePath()}"/>`];
  for (const v of venues) {
    if (byVenue.some((b) => b.venue_id === v.venue_id)) continue;
    const [x, y] = project(v.lat, v.lon);
    parts.push(`<circle class="other" cx="${x}" cy="${y}" r="4"/>`);
  }
  let shown = 0;
  for (const b of byVenue) {
    const v = coords.get(b.venue_id);
    if (!v) continue;
    const [x, y] = project(v.lat, v.lon);
    parts.push(`<circle class="hit" cx="${x}" cy="${y}" r="${(7 + 11 * Math.sqrt((b.plays_counted || 0) / max)).toFixed(1)}"><title>${esc(b.name)}, ${esc(b.city)}: ${fmtInt(b.plays_counted)} counted</title></circle>`);
    shown += 1;
  }
  svg.setAttribute("viewBox", `0 0 ${VIEW.w} ${VIEW.h}`);
  svg.innerHTML = parts.join("");
  const cities = new Set(byVenue.map((b) => b.city));
  $("map-sub").textContent = shown ? `${byVenue.length} bars, ${cities.size} cities` : "";
}

function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 6000);
}

// ---------- artist finder (no ?name=) ----------
async function finder() {
  $("profile").hidden = true;
  $("finder").hidden = false;
  document.title = "Artists · Fair Play";
  $("foot").textContent = `Shares are indicative until the period is closed.${MOCK ? " Mock data." : ""}`;
  let artists = [], shares = null;
  try {
    const r = await fetch(MOCK ? "../contract/fixtures/api/artists.json" : "/api/v1/artists", { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    artists = await r.json();
  } catch (e) { $("artist-list").innerHTML = `<div class="empty">Could not load the artists. Try again in a moment.</div>`; return; }
  try { shares = await get("artist_shares", "live", "standardised"); } catch (_) { /* list without shares */ }
  const byName = new Map(((shares && !shares.frozen && shares.rows) || []).map((r) => [r.artist_name, r]));
  const cv = await loadCovers();
  const av = (n) => { const c = cv.artist(n); return c ? `<span class="l-av img" style="background-image:url('${c.src}')"></span>` : `<span class="l-av">${esc(initials(n))}</span>`; };
  const link = (n) => `artist.html?name=${encodeURIComponent(n)}${MOCK ? "&mock=1" : ""}`;
  // Leaders of the month (computed shares of the closed mock month).
  try {
    const m = await get("artist_shares", "mock_month", "standardised");
    $("leaders").style.setProperty("--n", Math.max(1, Math.min(4, m.rows.length)));
    $("leaders").innerHTML = m.frozen ? `<div class="empty">Results are withheld until the play log is restored.</div>`
      : m.rows.slice(0, 4).map((r) => `<a class="leader" href="${link(r.artist_name)}"><span class="l-rank">${r.rank}</span>
        ${av(r.artist_name)}<b>${esc(r.artist_name)}</b>
        <span class="l-share">${fmtPct(r.share)}</span><span class="l-sub">${fmtInt(r.counted_plays)} plays counted, ${r.n_songs} song${r.n_songs === 1 ? "" : "s"}</span></a>`).join("");
  } catch (_) { $("leaders").closest("section").hidden = true; }
  const render = () => {
    const q = $("q").value.trim().toLowerCase();
    const list = artists.filter((a) => !q || a.artist_name.toLowerCase().includes(q))
      .sort((a, b) => a.artist_name.localeCompare(b.artist_name, "fr"));
    $("artist-list").innerHTML = list.map((a) => {
      const s = byName.get(a.artist_name);
      return `<a class="artist-link" href="${link(a.artist_name)}">${av(a.artist_name)}
        <div><span class="a-name">${esc(a.artist_name)}</span>
        <span class="sub">${a.songs.length} song${a.songs.length === 1 ? "" : "s"}${s ? `, ${fmtPct(s.share)} live, rank #${s.rank}` : ""}</span></div></a>`;
    }).join("") || `<div class="empty">No artist matches "${esc(q)}". Check the spelling, or declare your songs with SONACAM first.</div>`;
  };
  $("q").addEventListener("input", render);
  render();
  $("q").focus();
}
if (!name) { finder(); }
else {

// Period switch (keeps it in the URL so the link can be shared).
document.querySelectorAll("[data-period]").forEach((b) => b.addEventListener("click", () => {
  period = b.dataset.period;
  document.querySelectorAll("[data-period]").forEach((x) => x.classList.toggle("on", x === b));
  params.set("period", period);
  history.replaceState(null, "", `?${params}`);
  load();
}));
document.querySelector(`[data-period="${period}"]`).click();

$("share-link").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(location.href); toast("Link copied"); } catch (_) { toast(location.href); }
});

setInterval(() => { if (lastPlay) renderNow($("now").classList.contains("live")); }, 1000);

feed(({ event, data }) => {
  if (event === "stats") { load(); return; }
  if (event !== "play" || !mySongs.has(data.song_id) || period !== "live") return;
  lastPlay = { title: data.title, venue_id: data.venue_id, started_at: data.started_at, duration_s: data.duration_s };
  renderNow(true);
  toast(`🔊 ${data.title} is playing at ${venueNames.get(data.venue_id) || data.venue_id || "a bar"}`);
  setTimeout(() => { $("now").classList.remove("live"); renderNow(false); }, 120000);
});
}   // end of profile mode
