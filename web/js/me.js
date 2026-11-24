// Artist portal: the artist's own space (profile, activity feed, songs, declare a song).
// Sign-in is a prototype: the artist picks their name, no password, until real accounts exist (REQUESTS R-018).
// The declare form itself is handled by portal.js; this file sets the artist name on it.
import { MOCK, get, feed, fmtTime, fmtDateTime } from "./api.js";

const $ = (id) => document.getElementById(id);
const KEY = "fp-artist";
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(x < 0.1 ? 2 : 1) + " %");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initials = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
const ART = ["bottles", "dj", "mic", "outdoor-bar", "yaounde", "party"];
const artFor = (s) => `assets/img/${ART[[...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % ART.length]}.webp`;
const store = { get: () => { try { return localStorage.getItem(KEY); } catch (_) { return null; } },
  set: (v) => { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch (_) { /* private mode */ } } };

function timeAgo(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

// ---------- sign in ----------
async function showSignin() {
  $("signin").hidden = false; $("me").hidden = true;
  let artists = [];
  try { artists = await (await fetch(MOCK ? "../contract/fixtures/api/artists.json" : "/api/v1/artists", { cache: "no-store" })).json(); } catch (_) { /* free text */ }
  $("artist-names").innerHTML = artists.map((a) => `<option value="${esc(a.artist_name)}">`).join("");
  $("signin-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const n = $("signin-name").value.trim();
    if (artists.length && !artists.some((a) => a.artist_name === n)) {
      $("signin-err").textContent = "That name is not in the catalogue yet. Check the spelling, or ask the rights society to register you.";
      return;
    }
    store.set(n);
    location.hash = "";
    start(n);
  });
  $("signin-name").focus();
}

// ---------- tabs ----------
function showTab(tab) {
  document.querySelectorAll(".tabs [data-tab], .side-nav [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.dataset.panel !== tab; });
  if (tab === "declare") $("title").focus();
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-tab]"); if (b) { e.preventDefault(); showTab(b.dataset.tab); } });

// ---------- portal ----------
async function start(name) {
  $("signin").hidden = true; $("me").hidden = false;
  document.title = `${name} · Artist portal`;
  $("me-name").textContent = name;
  $("me-avatar").textContent = initials(name);
  $("me-mini").textContent = initials(name);
  $("me-public").href = `artist.html?name=${encodeURIComponent(name)}${MOCK ? "&mock=1" : ""}`;
  $("artist").value = name;                    // the declare form always declares for the signed-in artist
  $("signout").onclick = () => { store.set(null); location.reload(); };

  let a = null, shares = null, total = null;
  try {
    const r = await fetch(MOCK ? "../contract/fixtures/api/artist.json" : `/api/v1/artists/${encodeURIComponent(name)}?period=live`, { cache: "no-store" });
    if (r.ok) a = await r.json();
  } catch (_) { /* new artist: nothing yet */ }
  try { shares = await get("artist_shares", "live", "standardised"); } catch (_) { /* no shares */ }
  try { total = (await get("overview", "live")).plays_counted; } catch (_) { /* no total */ }

  const byVenue = (a && a.plays_by_venue) || [];
  const counted = byVenue.reduce((t, v) => t + (v.plays_counted || 0), 0);
  const row = shares && !shares.frozen ? shares.rows.find((r) => r.artist_name === name) : null;
  const share = row ? row.share : (total ? counted / total : null);
  const songs = (a && a.songs) || [];
  $("me-line").textContent = `Artist · ${songs.length} song${songs.length === 1 ? "" : "s"} declared · ${byVenue.length} bar${byVenue.length === 1 ? "" : "s"} played you`;
  $("s-counted").textContent = fmtInt(counted);
  $("s-bars").textContent = fmtInt(byVenue.length);
  $("s-songs").textContent = fmtInt(songs.length);
  $("s-share").textContent = fmtPct(share);
  $("s-bars-list").innerHTML = [...byVenue].sort((x, y) => (y.plays_counted || 0) - (x.plays_counted || 0)).slice(0, 5)
    .map((v) => `<div class="row"><span>${esc(v.name)}</span><span class="num">${fmtInt(v.plays_counted)}</span><span class="sub">${esc(v.city)}</span></div>`).join("")
    || `<div class="empty">No bar has played you yet.</div>`;

  // Top songs (Apple Music style rows with square artwork)
  const songShare = new Map(((row && row.songs) || []).map((s) => [s.song_id, s]));
  $("top-songs").innerHTML = songs.map((s) => {
    const st = songShare.get(s.song_id);
    return `<div class="ts"><img src="${artFor(s.title)}" alt=""><div><b>${esc(s.title)}</b><span>${st ? `${fmtPct(st.share)} · ${fmtInt(st.counted_plays)} counted` : "No counted plays yet"}</span></div></div>`;
  }).join("") || `<div class="empty">Declare your first song to start counting.</div>`;

  // Activity feed: a weekly summary post, then one post per recent play
  const days = (a && a.plays_by_day) || [];
  const week = days.slice(-7).reduce((t, d) => t + (d.plays_counted || 0), 0);
  const posts = [];
  if (days.length) posts.push(`<article class="post summary"><div class="post-head"><span class="ph-mini">FP</span><div><b>Fair Play</b><span>${fmtDateTime(new Date().toISOString())}</span></div></div>
    <p>This week your songs were counted <b>${fmtInt(week)}</b> times across <b>${fmtInt(byVenue.length)}</b> bars.</p>
    <div class="mini-chart">${days.slice(-7).map((d) => `<i style="height:${(100 * (d.plays_counted || 0) / Math.max(1, ...days.slice(-7).map((x) => x.plays_counted || 0))).toFixed(0)}%"></i>`).join("")}</div></article>`);
  const venueName = new Map(byVenue.map((v) => [v.venue_id, `${v.name}, ${v.city}`]));
  for (const p of ((a && a.recent) || []).slice(0, 10)) posts.push(playPost(p.title || p.song_id, venueName.get(p.venue_id) || p.venue_id, p.started_at, false));
  $("feed-posts").innerHTML = posts.join("") || `<div class="card empty">Your activity appears here as soon as a bar plays one of your songs.</div>`;

  // Live: a new post at the top when a meter confirms one of this artist's songs
  const mine = new Set(songs.map((s) => s.song_id));
  feed(({ event, data }) => {
    if (event !== "play" || !mine.has(data.song_id)) return;
    $("feed-posts").insertAdjacentHTML("afterbegin", playPost(data.title, venueName.get(data.venue_id) || data.venue_id, data.started_at, true));
    const t = $("toast"); t.textContent = `Your song ${data.title} is playing in a bar`; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 5000);
  });
  showTab(location.hash === "#declare" ? "declare" : "activity");
}

function playPost(title, where, at, live) {
  return `<article class="post${live ? " live" : ""}"><div class="post-head"><img class="post-art" src="${artFor(title)}" alt="">
    <div><b>${esc(title)}</b><span>${live ? '<em class="live-tag">Live</em> ' : ""}${timeAgo(at)} · ${fmtTime(at)}</span></div></div>
    <p>Played at <b>${esc(where || "a bar")}</b>${live ? ", right now" : ""}.</p></article>`;
}

const who = store.get();
if (who) start(who); else showSignin();
