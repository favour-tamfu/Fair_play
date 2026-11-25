// Data access for the dashboard. Mock mode (?mock=1) reads the fixtures in contract/fixtures/api
// (served by python -m http.server from the repo root); otherwise it calls B's /api/v1 endpoints.

export const MOCK = new URLSearchParams(location.search).get("mock") === "1";
const FIXTURES = "../contract/fixtures/api/";

const MOCK_FILES = {
  overview: "overview.json",
  venues: "venues.json",
  shares_raw: "shares_raw.json",
  shares_standardised: "shares_standardised.json",
  flags: "flags.json",
  ledger_status: "ledger_status.json",
  payouts: "payouts.json",
  artist_shares: "artist_shares.json",
  compare_flat: "compare_flat.json",
  feed: "feed_sample.txt",
  plays: "plays.json",
  songs: "songs.json",
};

async function getJson(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

export async function get(name, period = "live", mode = "standardised") {
  if (MOCK) {
    if (name === "shares") return getJson(FIXTURES + MOCK_FILES[`shares_${mode === "raw" ? "raw" : "standardised"}`]);
    if (!MOCK_FILES[name]) throw new Error(`no fixture for ${name}`);
    return getJson(FIXTURES + MOCK_FILES[name]);
  }
  const q = new URLSearchParams({ period, mode });
  const paths = {
    overview: `/api/v1/overview?${q}`,
    venues: `/api/v1/venues`,
    shares: `/api/v1/shares?${q}`,
    ledger_status: `/api/v1/ledger/status`,
    flags: `/api/v1/flags?${q}`,
    artist_shares: `/api/v1/artist-shares?${q}`,   // c-1.3: what each artist earned (sum of their songs' shares)
    compare_flat: `/api/v1/compare-flat`,
    anchors: `/api/v1/ledger/anchors?limit=24`,
    plays: `/api/v1/plays?period=${encodeURIComponent(period)}&limit=20`,
    songs: `/api/v1/songs`,
  };
  return getJson(paths[name]);
}

// Times: the API sends UTC; people read Cameroon time (D-012, Africa/Douala = UTC+1).
const TZ = { timeZone: "Africa/Douala" };
export const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString("fr-FR", TZ) : "");
export const fmtHm = (iso) => (iso ? new Date(iso).toLocaleTimeString("fr-FR", { ...TZ, hour: "2-digit", minute: "2-digit" }) : "");
export const fmtDateTime = (iso) => (iso ? new Date(iso).toLocaleString("fr-FR", { ...TZ, dateStyle: "short", timeStyle: "short" }) : "");

// Parse SSE text (the fixture file and the live stream use the same format).
export function parseSse(text) {
  const out = [];
  for (const block of text.split(/\n\n+/)) {
    let event = "message";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trim());
    }
    if (data.length) {
      try { out.push({ event, data: JSON.parse(data.join("\n")) }); } catch (_) { /* skip bad line */ }
    }
  }
  return out;
}

// Calls onEvent({event, data}) for each live message. Returns a stop function.
export function feed(onEvent) {
  if (MOCK) {
    let timer = null;
    let events = [];
    let i = 0;
    fetch(FIXTURES + MOCK_FILES.feed).then((r) => r.text()).then((t) => {
      events = parseSse(t);
      timer = setInterval(() => {
        if (!events.length) return;
        onEvent(events[i % events.length]);
        i += 1;
      }, 2000);
    });
    return () => clearInterval(timer);
  }
  const es = new EventSource("/api/v1/feed");
  for (const name of ["batch", "match", "play", "flag", "ledger", "meter", "stats"]) {
    es.addEventListener(name, (msg) => {
      try { onEvent({ event: name, data: JSON.parse(msg.data) }); } catch (_) { /* skip */ }
    });
  }
  return () => es.close();
}
