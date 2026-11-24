// Artist page (A-T14): what one artist earns from bar plays, on their phone.
// Share = the artist's songs' counted plays / all counted plays (D-015, c-1.3); no money in this version.
// Now-playing card lights up live when a meter confirms a play of one of their songs (SSE "play").
import { MOCK, get, feed, fmtHm, fmtDateTime } from "./api.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const name = params.get("name") || "Mock Artist 01";
let period = params.get("period") === "mock_month" ? "mock_month" : "live";
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(x < 0.1 ? 2 : 1) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

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
  const row = shares && !shares.frozen ? shares.rows.find((r) => r.artist_name === artistName) : null;

  document.title = `${artistName} · Fair Play`;
  $("name").textContent = artistName;
  $("avatar").textContent = initials(artistName);
  $("watermark").textContent = artistName;
  $("songs-line").textContent = `${(a.songs || []).length} song${(a.songs || []).length === 1 ? "" : "s"} in the SONACAM catalogue`;
  mySongs = new Set((a.songs || []).map((s) => s.song_id));
  for (const v of a.plays_by_venue || []) venueNames.set(v.venue_id, `${v.name}, ${v.city}`);

  // The three round controls: share, rank, counted plays.
  const share = a.share ?? (row ? row.share : null);
  $("share").textContent = shares && shares.frozen ? "held" : fmtPct(share);
  $("rank").textContent = row ? `#${row.rank}` : "–";
  $("rank-label").textContent = row && shares ? `Rank (of ${shares.rows.length} artists)` : "Rank";
  const counted = (a.plays_by_venue || []).reduce((t, v) => t + (v.plays_counted || 0), 0);
  $("counted").textContent = fmtInt(counted);

  // Songs, with each song's share when the stats run has it.
  const songShare = new Map((row ? row.songs : []).map((s) => [s.song_id, s]));
  const maxSong = Math.max(0.0001, ...[...songShare.values()].map((s) => s.share));
  $("songs").innerHTML = (a.songs || []).map((s) => {
    const st = songShare.get(s.song_id);
    return `<div class="row"><span>${esc(s.title)}</span><span class="num">${st ? fmtPct(st.share) : "–"}</span>
      <span class="sub">${st ? `${fmtInt(st.counted_plays)} counted · ${fmtInt(st.raw_plays)} heard` : "no counted plays yet"}</span>
      ${st ? `<span class="meter"><i style="width:${(100 * st.share / maxSong).toFixed(1)}%"></i></span>` : ""}</div>`;
  }).join("") || `<div class="empty">No songs yet.</div>`;

  const venues = [...(a.plays_by_venue || [])].sort((x, y) => (y.plays_counted || 0) - (x.plays_counted || 0));
  const maxV = Math.max(1, ...venues.map((v) => v.plays_counted || 0));
  $("venues").innerHTML = venues.map((v) => `<div class="row"><span>${esc(v.name)}</span><span class="num">${fmtInt(v.plays_counted)}</span>
    <span class="sub">${esc(v.city)} · ${fmtInt(v.plays_raw)} heard</span>
    <span class="meter"><i style="width:${(100 * (v.plays_counted || 0) / maxV).toFixed(1)}%"></i></span></div>`).join("")
    || `<div class="empty">No bar has played you in this period yet.</div>`;

  const days = a.plays_by_day || [];
  const maxD = Math.max(1, ...days.map((d) => d.plays_counted || 0));
  $("chart").innerHTML = days.map((d) => `<i title="${esc(d.date)}: ${fmtInt(d.plays_counted)} counted" style="height:${(100 * (d.plays_counted || 0)) / maxD}%"></i>`).join("");
  $("chart-range").textContent = days.length ? `${days[0].date.slice(5)} → ${days[days.length - 1].date.slice(5)}` : "";

  const recent = (a.recent || []).slice(0, 12);
  $("recent").innerHTML = recent.map((p) => `<div class="row"><span>${esc(p.title || p.song_id)}</span><span class="sub" style="grid-column:auto">${fmtDateTime(p.started_at)}</span>
    <span class="sub">${esc(venueNames.get(p.venue_id) || p.venue_id || "")}</span></div>`).join("")
    || `<div class="empty">No recent plays.</div>`;
  lastPlay = recent[0] || null;
  renderNow(false);

  $("foot").textContent = `${shares && shares.stats_run_id ? `${shares.rule_version} · run ${shares.stats_run_id} · ` : ""}times in Cameroon time${MOCK ? " · mock data" : ""}`;
}

function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 6000);
}

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
