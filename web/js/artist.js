// Artist page (A-T14): what one artist earns from bar plays, on their phone.
// Share = the artist's songs' counted plays / all counted plays (D-015, c-1.3); no money in this version.
// Now-playing card lights up live when a meter confirms a play of one of their songs (SSE "play").
import { MOCK, get, feed, fmtHm, fmtDateTime } from "./api.js";
import { VIEW, project, outlinePath } from "./cameroon.js";
import { loadCovers } from "./covers.js";
import { osmMap } from "./osm.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const name = params.get("name");   // no name: show the ranking of all artists
let period = params.get("period") === "mock_month" ? "mock_month" : "live";
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(x < 0.1 ? 2 : 1) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
// Square artwork: one of the site photos, picked from the name so it stays the same for the same song or bar.
const ART = ["bottles", "dj", "mic", "outdoor-bar", "yaounde", "party"];
const artFor = (s) => `assets/img/${ART[[...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % ART.length]}.webp`;

const venueNames = new Map();     // venue_id -> "Name, City"
const barLabel = (n) => String(n || "").replace(/^mock bar\s+/i, "Bar ");   // simulated bars: no "Mock" label on the page
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
    $("now-where").textContent = period === "live" ? "Songs show here the moment a bar plays them." : "No plays in this period.";
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
  const ranked = shares && !shares.frozen ? shares.rows.filter((r) => r.artist_name !== "Fair Play test artist" && r.counted_plays > 0) : [];
  const ri = ranked.findIndex((r) => r.artist_name === artistName);
  const row = ri >= 0 ? { ...ranked[ri], rank: ri + 1 } : null;

  document.title = `${artistName} · Fair Play`;
  $("name").textContent = artistName;
  $("avatar").textContent = initials(artistName);
  $("watermark").textContent = artistName;
  $("songs-line").textContent = `${(a.songs || []).length} song${(a.songs || []).length === 1 ? "" : "s"} in the catalogue`;
  mySongs = new Set((a.songs || []).map((s) => s.song_id));
  for (const v of a.plays_by_venue || []) venueNames.set(v.venue_id, `${barLabel(v.name)}, ${v.city}`);

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
  $("rank-label").textContent = row ? `of ${ranked.length} artists` : "No counted play in this period";
  $("counted").textContent = fmtInt(counted);
  $("counted-sub").textContent = `${fmtInt(heard)} heard, in ${(a.plays_by_venue || []).length} bars`;
  drawMap(a.plays_by_venue || []);

  // Songs, with each song's share when the stats run has it.
  const songShare = new Map((row ? row.songs : []).map((s) => [s.song_id, s]));
  const maxSong = Math.max(0.0001, ...[...songShare.values()].map((s) => s.share));
  // Top songs: rows with square artwork (song plays counted from the recent list when there is no stats row).
  const recentCount = new Map();
  for (const p of a.recent || []) recentCount.set(p.song_id, (recentCount.get(p.song_id) || 0) + 1);
  const ordered = [...(a.songs || [])].sort((x, y) => ((songShare.get(y.song_id) || {}).counted_plays || 0) - ((songShare.get(x.song_id) || {}).counted_plays || 0)
    || (recentCount.get(y.song_id) || 0) - (recentCount.get(x.song_id) || 0));
  $("songs").innerHTML = ordered.map((s, i) => {
    const st = songShare.get(s.song_id);
    const line = st ? `${fmtPct(st.share)} · ${fmtInt(st.counted_plays)} counted`
      : recentCount.get(s.song_id) ? `${recentCount.get(s.song_id)} of the last ${(a.recent || []).length} plays` : "No counted plays yet";
    return `<div class="am-row"><img src="${coverFor(s.title)}" alt=""><span class="am-n">${i + 1}</span><div><b>${esc(s.title)}</b><span>${line}</span></div></div>`;
  }).join("") || `<div class="empty">No songs yet.</div>`;

  // Bars: a ranked list (no sideways scrolling), most counted first; the top 10, then "Show all".
  const venues = [...(a.plays_by_venue || [])].sort((x, y) => (y.plays_counted || 0) - (x.plays_counted || 0));
  const vmax = Math.max(1, ...venues.map((v) => v.plays_counted || 0));
  const vtotal = venues.reduce((n, v) => n + (v.plays_counted || 0), 0);
  let showAll = false;
  const drawVenues = () => {
    const list = showAll ? venues : venues.slice(0, 10);
    $("venues").innerHTML = list.map((v, i) => `<li><div class="rk-row bar-row">
        <span class="rk-n">${i + 1}</span>
        <span class="rk-who"><b>${esc(barLabel(v.name))}</b><span>${esc(v.city)}${v.plays_raw != null ? ` · ${fmtInt(v.plays_raw)} heard` : ""}</span></span>
        <span class="rk-bar" aria-hidden="true"><i style="width:${(100 * (v.plays_counted || 0) / vmax).toFixed(1)}%"></i></span>
        <b class="rk-share">${fmtInt(v.plays_counted)}</b><span class="bar-pct">${vtotal ? fmtPct((v.plays_counted || 0) / vtotal) : ""}</span></div></li>`).join("")
      || `<li class="empty">No bar has played this artist in this period yet.</li>`;
    $("venues-more").hidden = venues.length <= 10;
    $("venues-more").textContent = showAll ? "Show the top 10" : `Show all ${venues.length} bars`;
  };
  $("venues-more").onclick = () => { showAll = !showAll; drawVenues(); };
  $("venues-sub").textContent = venues.length ? `${venues.length} bars · plays counted` : "";
  drawVenues();
  $("am-hero").style.backgroundImage = `linear-gradient(180deg, rgba(0,0,0,0) 35%, rgba(0,0,0,.72) 100%), url('${ownCover ? ownCover.src : artFor(artistName)}')`;
  $("am-hero").classList.toggle("has-cover", !!ownCover);

  const days = a.plays_by_day || [];
  // y axis: a round top value and 4 equal steps (e.g. 0, 60, 120, 180, 240), gridlines at each step
  const peak = Math.max(1, ...days.map((d) => d.plays_counted || 0));
  const raw = peak / 4, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
  const top = Math.max(step * 4, 4), ticks = [0, 1, 2, 3, 4].map((k) => Math.round(k * top / 4));
  $("chart-y").innerHTML = ticks.map((v) => `<span style="bottom:${(100 * v) / top}%">${fmtInt(v)}</span>`).join("");
  $("chart-grid").innerHTML = ticks.map((v) => `<i style="bottom:${(100 * v) / top}%"></i>`).join("");
  $("chart").innerHTML = days.map((d) => {
    const label = `${new Date(d.date + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}: ${fmtInt(d.plays_counted)} counted`;
    return `<i data-v="${esc(label)}" aria-label="${esc(label)}" style="height:${(100 * (d.plays_counted || 0)) / top}%"></i>`;
  }).join("");
  const busiest = days.reduce((b, d) => ((d.plays_counted || 0) > (b ? b.plays_counted || 0 : -1) ? d : b), null);
  const dayLabel = (d, o) => new Date(d.date + "T12:00:00Z").toLocaleDateString("en-GB", o);
  $("chart-range").textContent = days.length ? `${fmtInt(days.reduce((t, d) => t + (d.plays_counted || 0), 0))} counted`
    + (busiest && days.length > 1 ? ` · busiest ${dayLabel(busiest, { weekday: "short", day: "numeric", month: "short" })} (${fmtInt(busiest.plays_counted)})` : "") : "";
  // a week or less: weekday names; a month: the date every few days so the labels stay readable
  const every = days.length > 10 ? Math.ceil(days.length / 6) : 1;
  $("chart-x").innerHTML = days.map((d, i) => `<span>${i % every === 0 ? dayLabel(d, days.length > 10 ? { day: "numeric", month: "short" } : { weekday: "short" }) : ""}</span>`).join("");

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
    parts.push(`<circle class="hit" cx="${x}" cy="${y}" r="${(7 + 11 * Math.sqrt((b.plays_counted || 0) / max)).toFixed(1)}"><title>${esc(barLabel(b.name))}, ${esc(b.city)}: ${fmtInt(b.plays_counted)} counted</title></circle>`);
    shown += 1;
  }
  svg.setAttribute("viewBox", `0 0 ${VIEW.w} ${VIEW.h}`);
  svg.innerHTML = parts.join("");
  // OpenStreetMap when the internet is there (D-025): each bar that played this artist, sized by its counted plays
  osmMap(svg, { height: "380px" }).then((m) => m && m.draw(byVenue.map((b) => {
    const v = coords.get(b.venue_id) || {};
    return { id: b.venue_id, lat: v.lat, lon: v.lon, kind: "hit", r: 6 + 10 * Math.sqrt((b.plays_counted || 0) / max),
      title: `${barLabel(b.name)}: ${fmtInt(b.plays_counted)}`,
      html: `<b>${esc(barLabel(b.name))}</b>, ${esc(b.city)}<br>${fmtInt(b.plays_counted)} plays counted${b.plays_raw != null ? ` (${fmtInt(b.plays_raw)} heard)` : ""}` };
  }), { fit: true }));
  const cities = new Set(byVenue.map((b) => b.city));
  $("map-sub").textContent = shown ? `${byVenue.length} bars, ${cities.size} cities` : "";
}

function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 6000);
}

// ---------- ranking of all artists (no ?name=) ----------
const TEST_ARTIST = "Fair Play test artist";      // fictional scenario tracks: never shown on the public pages
async function finder() {
  $("profile").hidden = true;
  $("finder").hidden = false;
  document.title = "Artists · Fair Play";
  let rkPeriod = params.get("period") === "live" ? "live" : "mock_month";
  let artists = [];
  try {
    const r = await fetch(MOCK ? "../contract/fixtures/api/artists.json" : "/api/v1/artists", { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    artists = (await r.json()).filter((a) => a.artist_name !== TEST_ARTIST);
  } catch (e) { $("ranking").innerHTML = `<li class="empty">Could not load the artists. Try again in a moment.</li>`; return; }
  const cv = await loadCovers();
  const av = (n, cls = "l-av") => { const c = cv.artist(n); return c ? `<span class="${cls} img" style="background-image:url('${c.src}')"></span>` : `<span class="${cls}">${esc(initials(n))}</span>`; };
  const link = (n) => `artist.html?name=${encodeURIComponent(n)}&period=${rkPeriod}${MOCK ? "&mock=1" : ""}`;
  const songsIn = new Map(artists.map((a) => [a.artist_name, a.songs.length]));
  let rows = [], frozen = false;

  const draw = () => {
    const q = $("q").value.trim().toLowerCase();
    const max = Math.max(0.0001, ...rows.map((r) => r.share));
    const played = rows.filter((r) => !q || r.artist_name.toLowerCase().includes(q));
    const playedNames = new Set(rows.map((r) => r.artist_name));
    const rest = artists.filter((a) => !playedNames.has(a.artist_name) && (!q || a.artist_name.toLowerCase().includes(q)))
      .sort((a, b) => a.artist_name.localeCompare(b.artist_name, "fr"));
    const row = (r) => `<li><a class="rk-row${r.rank <= 3 ? " top" : ""}" href="${link(r.artist_name)}">
        <span class="rk-n">${r.rank}</span>${av(r.artist_name, "rk-av")}
        <span class="rk-who"><b>${esc(r.artist_name)}</b><span>${fmtInt(r.counted_plays)} plays counted · ${r.n_songs} song${r.n_songs === 1 ? "" : "s"} played</span></span>
        <span class="rk-bar" aria-hidden="true"><i style="width:${(100 * r.share / max).toFixed(1)}%"></i></span>
        <b class="rk-share">${fmtPct(r.share)}</b>
        <svg class="rk-go" viewBox="0 0 12 20" aria-hidden="true"><path d="M2 2l8 8-8 8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></a></li>`;
    const none = (a) => `<li><a class="rk-row none" href="${link(a.artist_name)}"><span class="rk-n">–</span>${av(a.artist_name, "rk-av")}
        <span class="rk-who"><b>${esc(a.artist_name)}</b><span>${a.songs.length} song${a.songs.length === 1 ? "" : "s"} in the catalogue · no counted play in this period</span></span>
        <span class="rk-bar" aria-hidden="true"></span><b class="rk-share">–</b>
        <svg class="rk-go" viewBox="0 0 12 20" aria-hidden="true"><path d="M2 2l8 8-8 8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></a></li>`;
    $("ranking").innerHTML = frozen ? `<li class="empty">Results are withheld until the play log is restored.</li>`
      : (played.map(row).join("") + (rest.length ? `<li class="rk-sep">Not played in this period</li>` + rest.map(none).join("") : ""))
        || `<li class="empty">No artist matches "${esc(q)}".</li>`;
  };

  const loadPeriod = async () => {
    document.querySelectorAll("[data-rk]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.rk === rkPeriod)));
    params.set("period", rkPeriod); history.replaceState(null, "", `?${params}`);
    let s = null;
    try { s = await get("artist_shares", rkPeriod, "standardised"); } catch (_) { /* below */ }
    frozen = !!(s && s.frozen);
    rows = ((s && s.rows) || []).filter((r) => r.artist_name !== TEST_ARTIST && r.counted_plays > 0)
      .map((r, i) => ({ ...r, rank: i + 1 }));
    const month = rkPeriod === "mock_month";
    $("leaders-h").textContent = month ? "Leading this month." : "Leading right now.";
    $("leaders").style.setProperty("--n", Math.max(1, Math.min(4, rows.length)));
    $("leaders").innerHTML = frozen ? `<div class="empty">Results are withheld until the play log is restored.</div>`
      : rows.slice(0, 4).map((r) => `<a class="leader" href="${link(r.artist_name)}"><span class="l-rank">${r.rank}</span>
        ${av(r.artist_name)}<b>${esc(r.artist_name)}</b>
        <span class="l-share">${fmtPct(r.share)}</span><span class="l-sub">${fmtInt(r.counted_plays)} plays counted, ${r.n_songs} song${r.n_songs === 1 ? "" : "s"}</span></a>`).join("")
        || `<div class="empty">No counted play yet in this period.</div>`;
    const total = rows.reduce((n, r) => n + r.counted_plays, 0);
    $("rk-sum").textContent = rows.length
      ? `${rows.length} artists with counted plays, ${fmtInt(total)} plays counted${month ? " in the mock month" : " live"}.` : "";
    $("rk-note").textContent = (month ? "Mock month: 30 simulated days in the bars on the map, built on the real catalogue. The plays are generated, not heard. " : "Live: plays heard by the meter at the CIMFEST stand. ")
      + `${s && s.rule_version ? `Rules ${s.rule_version}` : ""}${s && s.stats_run_id ? `, computed in run ${s.stats_run_id}.` : ""}`;
    draw();
  };
  document.querySelectorAll("[data-rk]").forEach((b) => b.addEventListener("click", () => { rkPeriod = b.dataset.rk; loadPeriod(); }));
  $("q").addEventListener("input", draw);
  $("foot").textContent = `Fair Play is a prototype built at the CIMFEST Hackathon 2026.${MOCK ? " Mock data." : ""}`;
  feed(({ event, data }) => { if (event === "stats" && data && data.period === rkPeriod) loadPeriod(); });
  await loadPeriod();
  void songsIn;
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
