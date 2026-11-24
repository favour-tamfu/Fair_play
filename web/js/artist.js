// Artist page (A-T14): an artist's counted plays, amount, venues, days, recent plays, and live notices.
import { MOCK, feed } from "./api.js";

const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const name = new URLSearchParams(location.search).get("name") || "Mock Artist 01";
const $ = (id) => document.getElementById(id);

async function load() {
  const url = MOCK ? "../contract/fixtures/api/artist.json" : `/api/v1/artists/${encodeURIComponent(name)}`;
  let a;
  try {
    a = await (await fetch(url, { cache: "no-store" })).json();
  } catch (e) {
    $("name").textContent = name;
    $("songs").textContent = "Could not load this artist's data.";
    return null;
  }
  $("name").textContent = a.artist_name || name;
  $("songs").textContent = (a.songs || []).map((s) => s.title).join(" · ");
  const counted = (a.plays_by_venue || []).reduce((t, v) => t + (v.plays_counted || 0), 0);
  $("counted").textContent = fmtInt(counted);
  // The amount is only shown once the period is closed and its statistics are final.
  const closed = new URLSearchParams(location.search).get("period") === "closed";
  $("amount").textContent = closed ? `${fmtInt(a.amount_fcfa)} FCFA` : "paid at period close";
  $("venues").innerHTML = (a.plays_by_venue || []).map((v) => `
    <div class="row"><span>${v.name} <span class="muted">${v.city}</span></span>
    <span>${fmtInt(v.plays_counted)} counted · ${fmtInt(v.plays_raw)} raw</span></div>`).join("")
    || `<div class="muted">No bars yet.</div>`;
  const days = a.plays_by_day || [];
  const max = Math.max(1, ...days.map((d) => d.plays_counted || 0));
  $("chart").innerHTML = days.map((d) => `<i title="${d.date}: ${d.plays_counted}" style="height:${(100 * (d.plays_counted || 0)) / max}%"></i>`).join("");
  if (days.length) $("chart-range").textContent = `${days[0].date} to ${days[days.length - 1].date}`;
  $("recent").innerHTML = (a.recent || []).slice(0, 15).map((p) => `
    <div class="row"><span>${p.title || p.song_id}</span><span class="muted">${(p.started_at || "").slice(0, 16).replace("T", " ")} · ${p.venue_id || ""}</span></div>`).join("")
    || `<div class="muted">No recent plays.</div>`;
  return new Set((a.songs || []).map((s) => s.song_id));
}

async function main() {
  const mySongs = await load();
  if (!mySongs) return;
  feed(({ event, data }) => {
    if (event !== "play" || !mySongs.has(data.song_id)) return;
    const b = $("banner");
    b.textContent = `Your song was just played at ${data.venue_id || "a bar"}.`;
    b.classList.add("show");
    setTimeout(() => b.classList.remove("show"), 8000);
  });
}

main();
