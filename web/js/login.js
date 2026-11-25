// Sign-in page (D-028): POST /api/v1/auth/login, then go back to the page that asked, or to the user's home.
const $ = (id) => document.getElementById(id);
const next = new URLSearchParams(location.search).get("next");
const safeNext = next && /^[\w.-]+\.html([?#].*)?$/.test(next) ? next : null;   // only our own pages

fetch("/api/v1/auth/me", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((d) => {
  if (d && d.user) location.replace(safeNext && roleFits(d.user, safeNext) ? safeNext : d.user.home);
}).catch(() => {});

function roleFits(user, page) {
  const sonacamPage = page.startsWith("sonacam-");
  return user.role === "sonacam" ? sonacamPage : page.startsWith("portal.html");
}

$("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("go").disabled = true; $("msg").textContent = "";
  try {
    const r = await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("u").value.trim(), password: $("p").value }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "Wrong name or password.");
    location.replace(safeNext && roleFits(d.user, safeNext) ? safeNext : d.user.home);
  } catch (err) {
    $("msg").textContent = err.message;
    $("p").select();
  } finally { $("go").disabled = false; }
});
$("u").focus();
