// Album covers for catalogue artists (assets/covers/index.json, built from the iTunes Search API lookup).
// Covers are only ever matched by artist name or song title, never assigned to someone else.
let cache = null;

const norm = (s) => String(s ?? "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");

export async function loadCovers() {
  if (cache) return cache;
  let list = [];
  try {
    const r = await fetch(new URL("../assets/covers/index.json", import.meta.url));
    if (r.ok) list = await r.json();
  } catch (_) { /* no covers: callers fall back to initials */ }
  const byArtist = new Map(), bySong = new Map();
  for (const c of list) {
    c.src = new URL(`../assets/covers/${c.file}`, import.meta.url).href;
    const a = norm(c.artist);
    if (!byArtist.has(a)) byArtist.set(a, []);
    byArtist.get(a).push(c);
    bySong.set(a + "|" + norm(c.title), c);
  }
  // One cover per album, for decorative walls of covers.
  const seen = new Set();
  const albums = list.filter((c) => { const k = norm(c.album) || c.file; if (seen.has(k)) return false; seen.add(k); return true; });
  cache = {
    list, albums,
    artist(name) { return (byArtist.get(norm(name)) || [])[0] || null; },
    song(artist, title) {
      return bySong.get(norm(artist) + "|" + norm(title)) || null;
    },
  };
  return cache;
}

export const initials = (name) => String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
