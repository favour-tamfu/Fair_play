// Artist portal (D-028): the signed-in artist's own songs (GET /api/v1/me/songs) and the song upload (POST /api/v1/songs).
import { fmtDateTime } from "./api.js";
import { requireRole, showUser } from "./session.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const fmtPct = (x) => (x == null ? "–" : (100 * x).toFixed(x < 0.1 ? 2 : 1) + " %");
const STATUS = { ready: ["ready", "Recognisable"], uploaded: ["wait", "Processing"], processing: ["wait", "Processing"],
  duplicate_suspected: ["warn", "Being checked by SONACAM"], failed: ["bad", "Could not be read"] };
const ROLES = [["singer", "Singer"], ["composer", "Composer"], ["producer", "Producer"], ["publisher", "Publisher"]];

const user = await requireRole("artist");
showUser(user, $("who"));
$("hello").textContent = `Welcome, ${user.name}.`;
$("f-artist").value = user.artist_name;
let period = "mock_month", data = null;
const plays = {};   // period -> GET /api/v1/me/plays

async function load() {
  const r = await fetch("/api/v1/me/songs", { cache: "no-store" });
  if (r.status === 403) { location.replace("login.html?next=portal.html"); return; }
  data = await r.json();
  await Promise.all(["mock_month", "live"].map(async (p) => {
    const x = await fetch(`/api/v1/me/plays?period=${p}&limit=20`, { cache: "no-store" });
    if (x.ok) plays[p] = await x.json();
  }));
  draw();
}
function draw() {
  if (!data) return;
  const t = data.totals[period];
  $("t-share").textContent = t.frozen ? "Held" : fmtPct(t.share);
  $("t-share-sub").textContent = t.frozen ? "Withheld until SONACAM's play log is restored." : period === "live" ? "of plays counted live" : "of all plays counted in the month";
  $("t-counted").textContent = fmtInt(t.counted_plays);
  $("t-counted-sub").textContent = `${fmtInt(t.raw_plays)} heard; repeats close together count less`;
  const ready = data.songs.filter((s) => s.status === "ready").length;
  $("t-songs").textContent = fmtInt(data.songs.length);
  $("t-songs-sub").textContent = `${ready} recognisable by the meters`;
  $("songs-sub").textContent = period === "live" ? "live" : "last 30 days (mock month)";
  $("song-rows").innerHTML = data.songs.map((s) => {
    const [cls, label] = STATUS[s.status] || ["wait", s.status];
    const p = s.periods[period] || {};
    return `<tr><td><b>${esc(s.title)}</b><span class="soft">${esc([s.isrc, s.iswc].filter(Boolean).join(" · ") || s.song_id)}</span></td>
      <td><span class="st st-${cls}">${label}</span></td><td class="n">${fmtInt(p.counted_plays)}</td><td class="n">${fmtPct(p.share)}</td>
      <td class="soft">${fmtDateTime(s.uploaded_at)}</td></tr>`;
  }).join("") || `<tr><td colspan="5" class="soft">No song yet. Upload your first song below.</td></tr>`;
  drawWhen(); drawHow();
}

// ---------- when your songs were played (dates and times only, never the bar) ----------
const dayLabel = (date, o) => new Date(date + "T12:00:00Z").toLocaleDateString("en-GB", o);
function drawWhen() {
  const d = plays[period] || { days: [], recent: [] };
  const days = d.days || [];
  $("when-sub").textContent = period === "live" ? "live" : "last 30 days (mock month)";
  const total = days.reduce((n, x) => n + x.plays, 0);
  const busiest = days.reduce((b, x) => (!b || x.plays > b.plays ? x : b), null);
  $("chart-range").textContent = days.length ? `${fmtInt(total)} plays` + (busiest && days.length > 1
    ? ` · busiest ${dayLabel(busiest.date, { weekday: "short", day: "numeric", month: "short" })} (${fmtInt(busiest.plays)})` : "") : "";
  const peak = Math.max(1, ...days.map((x) => x.plays));
  const raw = peak / 4, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
  const top = Math.max(step * 4, 4), ticks = [0, 1, 2, 3, 4].map((k) => Math.round(k * top / 4));
  $("chart-y").innerHTML = ticks.map((v) => `<span style="bottom:${(100 * v) / top}%">${fmtInt(v)}</span>`).join("");
  $("chart-grid").innerHTML = ticks.map((v) => `<i style="bottom:${(100 * v) / top}%"></i>`).join("");
  $("chart").innerHTML = days.map((x) => {
    const label = `${dayLabel(x.date, { weekday: "short", day: "numeric", month: "short" })}: ${fmtInt(x.plays)} plays`;
    return `<i data-v="${esc(label)}" aria-label="${esc(label)}" style="height:${(100 * x.plays) / top}%"></i>`;
  }).join("") || "";
  const every = days.length > 10 ? Math.ceil(days.length / 6) : 1;
  $("chart-x").innerHTML = days.map((x, i) => `<span>${i % every === 0 ? dayLabel(x.date, days.length > 10 ? { day: "numeric", month: "short" } : { weekday: "short" }) : ""}</span>`).join("")
    || `<span class="soft">No play yet in this period.</span>`;
  const recent = d.recent || [];
  $("recent").innerHTML = recent.map((p) => `<li><b>${esc(p.title)}</b><span>${fmtDateTime(p.started_at)}${p.counted_less
    ? ` · ${p.weight === 0 ? "not counted (repeat pause)" : `counted ${p.weight === 0.5 ? "½" : p.weight === 0.25 ? "¼" : p.weight}`}` : ""}</span></li>`).join("")
    || `<li class="soft">No play yet in this period.</li>`;
}

// ---------- how your share is computed, with the artist's own numbers ----------
function drawHow() {
  const t = data.totals[period];
  const where = period === "live" ? "live, since the meters started" : "in the last 30 days (mock month)";
  if (t.frozen) { $("how-steps").innerHTML = `<li>SONACAM's play log failed its integrity check, so results are withheld until it is restored.</li>`; return; }
  $("how-steps").innerHTML = [
    `<b>Heard.</b> Meters in bars heard your songs <b>${fmtInt(t.raw_plays)}</b> times ${where}.`,
    `<b>Counted.</b> Repeats of the same song close together count less (the 3rd in a row counts ½, the 4th ¼, then nothing for 2 hours), so <b>${fmtInt(t.counted_plays)}</b> plays count.`,
    `<b>Compared.</b> All artists together have <b>${fmtInt(t.all_counted)}</b> counted plays in the same period.`,
    `<b>Your share</b> = ${fmtInt(t.counted_plays)} ÷ ${fmtInt(t.all_counted)} = <b>${fmtPct(t.share)}</b>. It is the sum of your songs' shares. SONACAM shares the levy by these shares and pays its members under its own rules.`,
  ].map((s) => `<li>${s}</li>`).join("");
}
document.querySelectorAll("[data-p]").forEach((b) => b.addEventListener("click", () => {
  period = b.dataset.p;
  document.querySelectorAll("[data-p]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  draw();
}));

// ---------- owners ----------
function ownerRow(name = "", role = "singer", share = "") {
  const d = document.createElement("div");
  d.className = "owner";
  d.innerHTML = `<input class="o-name" placeholder="Name" value="${esc(name)}" required>
    <select class="o-role">${ROLES.map(([v, l]) => `<option value="${v}"${v === role ? " selected" : ""}>${l}</option>`).join("")}</select>
    <input class="o-share" type="number" min="0.01" max="100" step="0.01" placeholder="%" value="${esc(share)}" required>
    <button type="button" class="o-del" aria-label="Remove this owner">×</button>`;
  d.querySelector(".o-del").addEventListener("click", () => { if ($("owners").children.length > 1) { d.remove(); sum(); } });
  d.querySelector(".o-share").addEventListener("input", sum);
  $("owners").appendChild(d);
}
function owners() {
  return [...$("owners").children].map((d) => ({ name: d.querySelector(".o-name").value.trim(), role: d.querySelector(".o-role").value,
    share_pct: Number(d.querySelector(".o-share").value) }));
}
function sum() {
  const total = owners().reduce((t, o) => t + (o.share_pct || 0), 0);
  $("owner-sum").textContent = `Total: ${total.toLocaleString("fr-FR")} %${Math.abs(total - 100) > 0.01 ? " (must be 100 %)" : ""}`;
  return total;
}
ownerRow(user.artist_name, "singer", 100);
sum();
$("add-owner").addEventListener("click", () => { ownerRow(); sum(); });

// ---------- upload ----------
$("up").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("f-msg");
  if (Math.abs(sum() - 100) > 0.01) { msg.textContent = "The owners' shares must add up to 100 %."; return; }
  const f = $("f-file").files[0];
  if (!f) return;
  if (f.size > 50 * 1024 * 1024) { msg.textContent = "The file is larger than 50 MB."; return; }
  const fd = new FormData();
  fd.append("file", f);
  fd.append("title", $("f-title").value.trim());
  fd.append("artist_name", user.artist_name);
  if ($("f-isrc").value.trim()) fd.append("isrc", $("f-isrc").value.trim());
  if ($("f-iswc").value.trim()) fd.append("iswc", $("f-iswc").value.trim());
  fd.append("owners", JSON.stringify(owners()));
  fd.append("consent", $("f-consent").checked ? "true" : "false");
  $("f-go").disabled = true; msg.textContent = "Uploading…";
  try {
    const r = await fetch("/api/v1/songs", { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : d.error || `HTTP ${r.status}`);
    msg.textContent = `Uploaded (${d.song_id}). SONACAM is fingerprinting it; it shows as Recognisable in about a minute.`;
    $("up").reset(); $("owners").innerHTML = ""; ownerRow(user.artist_name, "singer", 100); sum();
    $("f-artist").value = user.artist_name;
    load();
    let n = 0; const t = setInterval(() => { load(); if (++n > 12) clearInterval(t); }, 10000);   // follow the processing
  } catch (err) { msg.textContent = `Upload refused: ${err.message}`; } finally { $("f-go").disabled = false; }
});

load();
