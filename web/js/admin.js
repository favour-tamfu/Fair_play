// SONACAM admin page (A-T17): meters, recalculate, anchor, demo reset (in-page confirm, R-016),
// register a meter key, approve suspected duplicates, review flags. Admin actions send the admin password
// (header X-Admin-Token, D-020), kept in sessionStorage so it is forgotten when the tab closes.
import { MOCK, get, feed, fmtTime, fmtDateTime } from "./api.js";
import { requireRole, showUser } from "./session.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("fr-FR"));
const FIX = "../contract/fixtures/api/";

// ---------- activity log ----------
function log(text, kind = "") {
  const li = document.createElement("li");
  li.className = kind;
  li.innerHTML = `<span class="t">${fmtTime(new Date().toISOString())}</span> ${text}`;
  $("log").prepend(li);
}

// ---------- admin password (D-020) ----------
// D-028: the SONACAM session (cookie) authorises every admin call; no password box on the page.
const USER = await requireRole("sonacam");
showUser(USER, $("who"));

// POST helper. In mock mode nothing is sent: the page says what it would have done.
async function post(url, body) {
  if (MOCK) return { mock: true };
  const headers = {};
  const opts = { method: "POST", headers };
  if (body !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(url, opts);
  let data = null;
  try { data = await r.json(); } catch (_) { /* empty body */ }
  if (r.status === 403) { location.replace("login.html?next=sonacam-x7k2q9-admin.html"); throw new Error("signed out"); }
  if (!r.ok) throw new Error((data && (data.detail || data.error)) ? `${data.error || ""} ${typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || "")}`.trim() : `HTTP ${r.status}`);
  return data;
}
async function getJson(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
function busy(btn, on) { btn.disabled = on; btn.classList.toggle("busy", on); }

// ---------- meters ----------
async function loadMeters() {
  try {
    const venues = await get("venues");
    const rows = venues.flatMap((v) => (v.meters || []).map((m) => ({ ...m, venue: v })))
      .sort((a, b) => (b.online - a.online) || a.meter_id.localeCompare(b.meter_id));
    const online = rows.filter((m) => m.online).length;
    $("meters").innerHTML = rows.map((m) => `<tr>
      <td><b>${esc(m.meter_id)}</b></td><td>${esc(m.venue.name)}</td><td>${esc(m.venue.city)}</td>
      <td><span class="pill ${m.online ? "ok" : ""}">${m.online ? "online" : "offline"}</span></td>
      <td>${m.last_seen ? fmtDateTime(m.last_seen) : "never"}</td>
      <td class="n${m.queued ? " amber" : ""}">${fmtInt(m.queued)}</td>
      <td class="n">${m.catch_rate == null ? "–" : Math.round(100 * m.catch_rate) + " %"}</td></tr>`).join("")
      || `<tr><td colspan="7" class="note">No meters registered.</td></tr>`;
    $("meters-note").textContent = `${online} of ${rows.length} online · ${venues.length} bars`;
  } catch (e) { $("meters-note").textContent = `could not load: ${e.message}`; }
}

// ---------- ledger ----------
async function loadLedger() {
  try {
    const l = await get("ledger_status");
    const el = $("ledger");
    el.className = "ledger " + (l.intact ? "ok" : "bad");
    el.textContent = l.intact ? `Log intact · ${fmtInt(l.plays_checked)} plays checked` : `Log changed${l.broken_at_play_id ? ` at ${l.broken_at_play_id}` : ""} · results withheld`;
  } catch (_) { /* keep */ }
}

// ---------- actions ----------
$("btn-stats").addEventListener("click", async (ev) => {
  const period = $("stats-period").value;
  busy(ev.target, true);
  try {
    const r = await post(`/api/v1/stats/run?period=${period}&mode=both`);
    if (r.mock) log(`mock: would run stats for <b>${period}</b>`, "mock");
    else log(`Stats run <b>${esc(r.stats_run_id)}</b> for ${period}: ${fmtInt(r.n_plays)} plays, ${fmtInt(r.n_songs)} songs, ${fmtInt(r.n_flags)} flags, ${fmtInt(r.duration_ms)} ms`, "ok");
    loadFlags();
  } catch (e) { log(`Stats run failed: ${esc(e.message)}`, "err"); }
  busy(ev.target, false);
});

$("btn-anchor").addEventListener("click", async (ev) => {
  busy(ev.target, true);
  try {
    const r = await post("/api/v1/ledger/anchor");
    if (r.mock) log("mock: would anchor the current hour", "mock");
    else if (r.ok) log(`Anchored ${fmtDateTime(r.hour)}: ${fmtInt(r.n_plays)} plays, root <code>${esc(r.root.slice(0, 16))}…</code> (${esc(r.via)})`, "ok");
    else log(`Not anchored: ${esc(r.detail)}`, "warn");
    loadLedger();
  } catch (e) { log(`Anchor failed: ${esc(e.message)}`, "err"); }
  busy(ev.target, false);
});

// Reset: no browser confirm() dialog; the person types RESET in the page (plan A-T17).
const resetBox = $("reset-confirm");
$("btn-reset").addEventListener("click", () => { resetBox.classList.add("show"); $("reset-word").value = ""; $("btn-reset-go").disabled = true; $("reset-word").focus(); });
$("btn-reset-cancel").addEventListener("click", () => resetBox.classList.remove("show"));
$("reset-word").addEventListener("input", (e) => { $("btn-reset-go").disabled = e.target.value.trim() !== "RESET"; });
$("btn-reset-go").addEventListener("click", async (ev) => {
  const reason = $("reset-reason").value.trim() || "demo reset";
  busy(ev.target, true);
  try {
    const r = await post(`/api/v1/demo/reset?confirm=yes&reason=${encodeURIComponent(reason)}`);
    if (r.mock) log(`mock: would reset live data (reason "${esc(reason)}")`, "mock");
    else log(`Live data reset, epoch <b>${r.epoch}</b>: ${fmtInt(r.plays_removed)} plays, ${fmtInt(r.batches_removed)} samples, ${fmtInt(r.match_events_removed)} matches removed; ${fmtInt(r.anchors_archived)} anchors archived`, "ok");
    resetBox.classList.remove("show");
    loadMeters(); loadLedger(); loadFlags();
  } catch (e) { log(`Reset failed: ${esc(e.message)}`, "err"); }
  busy(ev.target, false);
});

// ---------- register a meter ----------
let pubKey = null;
$("pub-file").addEventListener("change", async (e) => {
  pubKey = null;
  $("btn-register").disabled = true;
  const f = e.target.files[0];
  if (!f) { $("pub-preview").textContent = ""; return; }
  try {
    const j = JSON.parse(await f.text());
    const missing = ["meter_id", "venue_id", "public_key_b64"].filter((k) => !j[k]);
    if (missing.length) throw new Error(`missing ${missing.join(", ")}`);
    if (j.private_key_b64 || j.seed_b64 || j.seed) throw new Error("this file holds a private key: never upload it, use the .pub.json");
    pubKey = j;
    $("pub-preview").textContent = `${j.meter_id} at ${j.venue_id}\nkey ${j.public_key_b64.slice(0, 20)}…`;
    $("btn-register").disabled = false;
  } catch (err) { $("pub-preview").textContent = `Not a meter key file: ${err.message}`; }
});
$("btn-register").addEventListener("click", async (ev) => {
  if (!pubKey) return;
  busy(ev.target, true);
  try {
    const r = await post("/v1/meters/register", pubKey);
    if (r.mock) log(`mock: would register <b>${esc(pubKey.meter_id)}</b> at ${esc(pubKey.venue_id)}`, "mock");
    else log(`Meter <b>${esc(pubKey.meter_id)}</b> registered at ${esc(pubKey.venue_id)}`, "ok");
    loadMeters();
  } catch (e) { log(`Register failed: ${esc(e.message)}`, "err"); }
  busy(ev.target, false);
});

// ---------- catalogue ----------
let songs = [];
let songFilter = "all";
const STATUS_ORDER = ["duplicate_suspected", "failed", "processing", "uploaded", "ready"];
async function loadSongs() {
  try {
    songs = await getJson(MOCK ? FIX + "songs.json" : "/api/v1/songs");
    renderSongs();
  } catch (e) { $("songs-note").textContent = `could not load: ${e.message}`; }
}
function renderSongs() {
  const counts = {};
  for (const s of songs) counts[s.status] = (counts[s.status] || 0) + 1;
  const keys = ["all", ...STATUS_ORDER.filter((k) => counts[k])];
  $("song-filters").innerHTML = keys.map((k) => `<button data-f="${k}" class="${k === songFilter ? "on" : ""}">${k.replace("_", " ")} ${k === "all" ? songs.length : counts[k]}</button>`).join("");
  const list = songs.filter((s) => songFilter === "all" || s.status === songFilter)
    .sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || a.song_id.localeCompare(b.song_id));
  $("songs").innerHTML = list.map((s) => `<tr>
    <td class="mono">${esc(s.song_id)}</td><td>${esc(s.title)}</td><td>${esc(s.artist_name)}</td>
    <td><span class="pill st-${esc(s.status)}">${esc(s.status.replace("_", " "))}</span>${s.duplicate_of ? ` <span class="note">of ${esc(s.duplicate_of)}</span>` : ""}</td>
    <td class="n">${fmtInt(s.n_hashes)}</td><td>${s.uploaded_at ? fmtDateTime(s.uploaded_at) : ""}</td>
    <td>${s.status === "duplicate_suspected" ? `<button class="small" data-approve="${esc(s.song_id)}">Not a duplicate: index it</button>` : ""}</td></tr>`).join("")
    || `<tr><td colspan="7" class="note">No songs.</td></tr>`;
  const dup = counts.duplicate_suspected || 0;
  $("songs-note").textContent = `${songs.length} songs · ${counts.ready || 0} ready${dup ? ` · ${dup} waiting for review` : ""}`;
}
$("song-filters").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-f]");
  if (!b) return;
  songFilter = b.dataset.f;
  renderSongs();
});
$("songs").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-approve]");
  if (!b) return;
  // Two-step in-page confirm: first click arms the button, second click sends.
  if (!b.classList.contains("armed")) { b.classList.add("armed"); b.textContent = "Click again to confirm"; setTimeout(() => { b.classList.remove("armed"); b.textContent = "Not a duplicate: index it"; }, 4000); return; }
  const id = b.dataset.approve;
  busy(b, true);
  try {
    const r = await post(`/api/v1/songs/${encodeURIComponent(id)}/approve`);
    if (r.mock) log(`mock: would approve <b>${esc(id)}</b> and index it`, "mock");
    else log(`<b>${esc(id)}</b> approved: indexing it now`, "ok");
    loadSongs();
  } catch (err) { log(`Approve ${esc(id)} failed: ${esc(err.message)}`, "err"); busy(b, false); }
});

// ---------- flags ----------
async function loadFlags() {
  try {
    const period = $("flags-period").value;
    const flags = MOCK ? await getJson(FIX + "flags.json") : await getJson(`/api/v1/flags?period=${period}`);
    $("flags").innerHTML = flags.map((f) => `<li><span class="chip">${esc(f.type)}</span> <b>${esc(f.song_id || "")}</b>
      ${f.venue_id ? `<span class="note">${esc(f.venue_id)}</span>` : ""}<div class="note">${esc(f.detail)} · ${fmtDateTime(f.created_at)}</div></li>`).join("")
      || `<li class="note">No flags for this period.</li>`;
  } catch (e) { $("flags").innerHTML = `<li class="note">could not load: ${esc(e.message)}</li>`; }
}
$("flags-period").addEventListener("change", loadFlags);

// ---------- live updates ----------
let meterTimer = null;
feed(({ event, data }) => {
  if (event === "meter") { clearTimeout(meterTimer); meterTimer = setTimeout(loadMeters, 1000); }
  if (event === "ledger") { loadLedger(); log(data.intact ? "Play log intact again" : "Play log changed: results withheld", data.intact ? "ok" : "err"); }
  if (event === "flag") loadFlags();
  if (event === "stats") loadFlags();
});

function tick() { $("clock").textContent = new Date().toLocaleString("fr-FR", { timeZone: "Africa/Douala", weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
tick(); setInterval(tick, 1000);
$("mode-note").textContent = MOCK ? " · mock data (?mock=1): actions are not sent" : "";
loadMeters(); loadLedger(); loadSongs(); loadFlags();
setInterval(() => { loadMeters(); if (songs.some((s) => s.status === "processing" || s.status === "uploaded")) loadSongs(); }, 15000);
log(MOCK ? "Admin page opened with mock data: actions are not sent" : "Admin page opened", "mock");

// ---------- activity log (D-024): GET /api/v1/admin/activity, polled every 3 s while "Live" is on ----------
const ACT_KINDS = [["", "All"], ["play", "Plays"], ["heard", "Songs heard"], ["report", "Meter reports"], ["meter", "Meters on/off"],
  ["flag", "Flags"], ["rejected", "Refused requests"], ["admin", "Admin actions"], ["catalogue", "Catalogue"], ["ledger", "Play log"], ["stats", "Shares"]];
const ACT_LABEL = Object.fromEntries(ACT_KINDS.filter(([k]) => k));
const act = { kind: "", rows: [], newest: null, oldest: null, live: true, timer: null, busy: false };
const actHeaders = () => ({});
function actParams(extra = {}) {
  const p = new URLSearchParams();
  if (act.kind) p.set("kind", act.kind);
  if ($("act-level").value) p.set("level", $("act-level").value);
  if ($("act-meter").value) p.set("meter_id", $("act-meter").value);
  if ($("act-q").value.trim()) p.set("q", $("act-q").value.trim());
  for (const [k, v] of Object.entries(extra)) if (v != null) p.set(k, v);
  return p;
}
async function actFetch(extra) {
  const r = await fetch(`/api/v1/admin/activity?${actParams(extra)}`, { headers: actHeaders(), cache: "no-store" });
  if (r.status === 403) throw Object.assign(new Error("password"), { code: 403 });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
function actRow(r) {
  return `<tr class="lv-${esc(r.level)}"><td class="t">${fmtDateTime(r.at)}</td><td><span class="kind k-${esc(r.kind)}">${esc(ACT_LABEL[r.kind] || r.kind)}</span></td>
    <td>${esc(r.message)}</td><td>${esc(r.meter_id || "")}</td><td class="soft">${esc(r.actor || "")}</td></tr>`;
}
function actDraw() {
  $("act-rows").innerHTML = act.rows.map(actRow).join("") || `<tr><td colspan="5" class="soft">Nothing matches these filters yet.</td></tr>`;
}
async function actReload() {
  if (MOCK) { $("act-note").textContent = "Not available with mock data."; return; }
  try {
    const d = await actFetch({ limit: 200 });
    act.rows = d.rows;
    act.newest = d.rows.length ? d.rows[0].id : act.newest;
    act.oldest = d.rows.length ? d.rows[d.rows.length - 1].id : null;
    $("act-older").hidden = !d.next_before_id;
    $("act-note").textContent = `newest first · kept ${d.keep_days} days · times in Cameroon time`;
    actDraw();
  } catch (e) {
    act.rows = []; actDraw();
    $("act-note").textContent = `Could not load the log (${e.message}).`;
  }
}
async function actPoll() {
  if (!act.live || act.busy || MOCK) return;
  act.busy = true;
  try {
    if (act.newest == null) { await actReload(); return; }
    const d = await actFetch({ after_id: act.newest, limit: 500 });
    if (d.rows.length) {
      act.rows = d.rows.concat(act.rows).slice(0, 1000);
      act.newest = d.rows[0].id;
      actDraw();
    }
  } catch (_) { /* keep what is shown; the note says why on the next reload */ } finally { act.busy = false; }
}
$("act-kinds").innerHTML = ACT_KINDS.map(([k, label]) => `<button type="button" data-kind="${k}" class="${k ? "" : "on"}">${label}</button>`).join("");
$("act-kinds").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-kind]"); if (!b) return;
  act.kind = b.dataset.kind;
  $("act-kinds").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
  act.newest = null; actReload();
});
for (const id of ["act-level", "act-meter"]) $(id).addEventListener("change", () => { act.newest = null; actReload(); });
let actSearch = null;
$("act-q").addEventListener("input", () => { clearTimeout(actSearch); actSearch = setTimeout(() => { act.newest = null; actReload(); }, 350); });
$("act-live").addEventListener("click", () => {
  act.live = !act.live;
  $("act-live").setAttribute("aria-pressed", String(act.live));
  $("act-live").textContent = act.live ? "● Live" : "❚❚ Paused";
  if (act.live) actPoll();
});
$("act-older").addEventListener("click", async () => {
  try {
    const d = await actFetch({ before_id: act.oldest, limit: 200 });
    act.rows = act.rows.concat(d.rows);
    act.oldest = d.rows.length ? d.rows[d.rows.length - 1].id : act.oldest;
    $("act-older").hidden = !d.next_before_id;
    actDraw();
  } catch (_) { /* keep */ }
});
$("act-csv").addEventListener("click", async () => {
  try {
    const r = await fetch(`/api/v1/admin/activity.csv?${actParams()}`, { headers: actHeaders() });
    if (!r.ok) throw new Error(r.status === 403 ? "enter the admin password first" : `HTTP ${r.status}`);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob());
    a.download = "fair_play_activity.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  } catch (e) { log(`CSV export failed: ${esc(e.message)}`, "err"); }
});
get("venues").then((vs) => {
  const ids = vs.filter((v) => v.source !== "mock").flatMap((v) => (v.meters || []).map((m) => m.meter_id)).sort();
  $("act-meter").insertAdjacentHTML("beforeend", ids.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join(""));
}).catch(() => {});
actReload();
setInterval(actPoll, 3000);
