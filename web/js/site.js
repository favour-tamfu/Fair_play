// Shared by the public pages: keep mock mode (?mock=1) when moving between our own pages.
import { MOCK } from "./api.js";

if (MOCK) {
  for (const a of document.querySelectorAll('a[href$=".html"], a[href*=".html#"]')) {
    const u = new URL(a.getAttribute("href"), location.href);
    if (!u.searchParams.has("mock")) { u.searchParams.set("mock", "1"); a.href = u.pathname.split("/").pop() + u.search + u.hash; }
  }
}
