// Sign-in helpers for the role-based pages (D-028). Roles: "sonacam" (SONACAM app) and "artist" (artist portal).
import { MOCK } from "./api.js";

// Make sure someone with `role` is signed in; otherwise go to the sign-in page (and come back afterwards).
// A signed-in user with another role is sent to their own home page. Returns the user.
export async function requireRole(role) {
  if (MOCK) return { name: role === "sonacam" ? "SONACAM" : "Artist", role, home: "" };
  let user = null;
  try {
    const r = await fetch("/api/v1/auth/me", { cache: "no-store" });
    if (r.ok) user = (await r.json()).user;
  } catch (_) { /* treated as signed out */ }
  if (!user) {
    location.replace(`login.html?next=${encodeURIComponent(location.pathname.replace(/^\//, "") + location.search + location.hash)}`);
    return new Promise(() => {});   // the page stops here while the browser leaves
  }
  if (user.role !== role) {
    location.replace(user.home);
    return new Promise(() => {});
  }
  return user;
}

export async function signOut() {
  try { await fetch("/api/v1/auth/logout", { method: "POST" }); } catch (_) { /* leave anyway */ }
  location.replace("login.html");
}

// Fill a "Signed in as … · Sign out" element when the page has one.
export function showUser(user, el) {
  if (!el || !user) return;
  el.innerHTML = `<span>${String(user.name).replace(/[&<>"']/g, "")}</span><button type="button" class="signout">Sign out</button>`;
  el.querySelector(".signout").addEventListener("click", signOut);
}
