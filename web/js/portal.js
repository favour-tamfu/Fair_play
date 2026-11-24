// Upload portal (A-T12): validate, send POST /api/v1/songs (multipart), show the catalogue status.
import { MOCK } from "./api.js";

const MAX_BYTES = 50 * 1024 * 1024; // contract c-1.1: 50 MB (was 30 MB)
const ROLES = ["singer", "composer", "producer", "publisher"];
const $ = (id) => document.getElementById(id);

function ownerRow(o = {}) {
  const row = document.createElement("div");
  row.className = "owner";
  row.innerHTML = `
    <label>Name <input data-k="name" value="${o.name || ""}" required></label>
    <label>Role <select data-k="role">${ROLES.map((r) => `<option ${r === (o.role || "singer") ? "selected" : ""}>${r}</option>`).join("")}</select></label>
    <label>Share % <input data-k="share_pct" type="number" min="0" max="100" step="0.01" value="${o.share_pct ?? ""}" required></label>
    <label>MoMo (+2376…) <input data-k="momo" pattern="\\+2376[0-9]{8}" value="${o.momo || ""}"></label>
    <button type="button" class="rm">remove</button>`;
  row.querySelector(".rm").addEventListener("click", () => { row.remove(); sumShares(); });
  row.querySelector('[data-k="share_pct"]').addEventListener("input", sumShares);
  return row;
}

function owners() {
  return [...document.querySelectorAll("#owners .owner")].map((row) => {
    const g = (k) => row.querySelector(`[data-k="${k}"]`).value.trim();
    return { name: g("name"), role: g("role"), share_pct: Number(g("share_pct")), momo: g("momo") || null };
  });
}

function sumShares() {
  const total = owners().reduce((a, o) => a + (Number.isFinite(o.share_pct) ? o.share_pct : 0), 0);
  $("share-sum").textContent = `total ${total.toFixed(2)} %`;
  $("share-sum").style.color = Math.abs(total - 100) < 0.005 ? "var(--teal)" : "var(--red)";
  return total;
}

function validate() {
  const file = $("file").files[0];
  if (!file) return "Choose an audio file.";
  if (file.size > MAX_BYTES) return `The file is ${(file.size / 1048576).toFixed(1)} MB. The limit is 50 MB.`;
  const list = owners();
  if (!list.length) return "Add at least one owner.";
  if (Math.abs(sumShares() - 100) > 0.005) return "Owner shares must add up to 100.";
  if (!$("consent").checked) return "Please confirm the consent.";
  return "";
}

function uploadWithProgress(form) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/songs");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) $("progress").textContent = `uploading ${Math.round((100 * e.loaded) / e.total)} %`;
    };
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch (_) { /* not JSON */ }
      if (xhr.status === 201) resolve(body);
      else reject(new Error(body.detail || body.error || `HTTP ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("network error: is the server reachable?"));
    xhr.send(form);
  });
}

async function submit(ev) {
  ev.preventDefault();
  $("err").textContent = ""; $("ok").textContent = "";
  const problem = validate();
  if (problem) { $("err").textContent = problem; return; }
  const form = new FormData();
  form.append("file", $("file").files[0]);
  form.append("title", $("title").value.trim());
  form.append("artist_name", $("artist").value.trim());
  if ($("isrc").value.trim()) form.append("isrc", $("isrc").value.trim());
  if ($("iswc").value.trim()) form.append("iswc", $("iswc").value.trim());
  form.append("owners", JSON.stringify(owners()));
  form.append("consent", "true");
  if (MOCK) { $("progress").textContent = ""; $("ok").textContent = "Mock mode: the upload is not sent."; return; }
  $("submit").disabled = true;
  try {
    const res = await uploadWithProgress(form);
    $("ok").textContent = `Uploaded as ${res.song_id}. It will show as ready once fingerprinted.`;
    const me = $("artist").value;
    $("form").reset();
    $("artist").value = me;
    document.getElementById("owners").innerHTML = "";
    document.getElementById("owners").appendChild(ownerRow({ share_pct: 100 }));
    sumShares();
    loadCatalogue();
  } catch (e) {
    $("err").textContent = `Upload failed: ${e.message}`;
  } finally {
    $("submit").disabled = false;
    $("progress").textContent = "";
  }
}

const STATUS_TEXT = {
  uploaded: "Uploaded", processing: "Processing", ready: "Ready",
  duplicate_suspected: "Possible duplicate", failed: "Failed",
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Only the signed-in artist's songs (the artist field is filled by me.js and read-only).
async function loadCatalogue() {
  let songs = [];
  try {
    const url = MOCK ? "../contract/fixtures/api/songs.json" : "/api/v1/songs";
    songs = await (await fetch(url, { cache: "no-store" })).json();
  } catch (_) { songs = []; }
  const me = $("artist").value.trim();
  const mine = me ? songs.filter((s) => s.artist_name === me) : songs;
  $("cat").innerHTML = mine.map((s) => `<tr>
      <td><b>${esc(s.title)}</b></td>
      <td><span class="chip2 s-${s.status}">${STATUS_TEXT[s.status] || esc(s.status)}</span></td>
      <td>${s.duplicate_of ? `Same audio as ${esc(s.duplicate_of)}, waiting for review` : s.status === "ready" ? "Recognised in every metered bar" : ""}</td></tr>`).join("")
    || `<tr><td colspan="3" class="empty">No songs declared yet.</td></tr>`;
  return mine.some((s) => s.status === "processing" || s.status === "uploaded");
}

async function pollWhileProcessing() {
  if (await loadCatalogue()) setTimeout(pollWhileProcessing, 2000);
}

$("add-owner").addEventListener("click", () => { $("owners").appendChild(ownerRow()); sumShares(); });
$("form").addEventListener("submit", submit);
$("owners").appendChild(ownerRow({ share_pct: 100 }));
sumShares();
// wait a moment so me.js has set the signed-in artist before the catalogue is filtered
setTimeout(pollWhileProcessing, 300);
