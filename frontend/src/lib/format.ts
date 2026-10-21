export const fmtInt = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("en-IN"));
export const pct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const fmtDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "–";

export const SOURCE_LABEL: Record<string, string> = {
  zomato_kaggle: "Zomato dataset (historical)",
  osm: "OpenStreetMap",
  google_places: "Google Places",
};
export const sourceLabel = (s: string | null | undefined) => (s ? SOURCE_LABEL[s] ?? s : "unknown source");

export const SENTIMENT_COLOR = { positive: "#2E7D4F", neutral: "#8A7F73", negative: "#B3382C" } as const;
export const SENTIMENT_TEXT = { positive: "Positive", neutral: "Neutral", negative: "Negative" } as const;

export const GEM_REASON: Record<string, string> = {
  qualified: "Hidden gem",
  insufficient_evidence: "Not enough reviews to judge",
  not_positive_enough: "Feedback isn't positive enough",
  not_low_visibility: "Already well known",
};

export const directionsUrl = (lat: number, lon: number) => `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`;
export const cuisineText = (c: string[]) => (c.length ? c.map((x) => x.replace(/\b\w/g, (m) => m.toUpperCase())).join(", ") : "Cuisine not listed");
