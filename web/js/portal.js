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

async function load() {
  const r = await fetch("/api/v1/me/songs", { cache: "no-store" });
  if (r.status === 403) { location.replace("login.html?next=portal.html"); return; }
  data = await r.json();
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
