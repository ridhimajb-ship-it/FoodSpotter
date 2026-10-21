import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { Filters, SentimentLabel } from "../types";

/** Price presets are expressed as "approximate cost for two" bounds in ₹ (from the dataset's own price field). */
export const PRICE_RANGES = [
  { v: "", l: "Any price" },
  { v: "0-500", l: "Up to ₹500" },
  { v: "500-1000", l: "₹500 – ₹1,000" },
  { v: "1000-2000", l: "₹1,000 – ₹2,000" },
  { v: "2000-", l: "₹2,000 and up" },
] as const;
export const RATINGS = [{ v: "", l: "Any rating" }, { v: "3.5", l: "3.5 and up" }, { v: "4", l: "4.0 and up" }, { v: "4.5", l: "4.5 and up" }];
export const ASPECTS = [
  { v: "food", l: "Food" }, { v: "service", l: "Service" }, { v: "ambience", l: "Ambience" },
  { v: "affordability", l: "Value for money" }, { v: "hygiene", l: "Hygiene" }, { v: "waiting_time", l: "Waiting time" },
];
export const MIN_REVIEW_OPTIONS = [{ v: "", l: "Any number" }, { v: "5", l: "5+ reviews" }, { v: "10", l: "10+ reviews" }, { v: "25", l: "25+ reviews" }, { v: "50", l: "50+ reviews" }];

const KEYS = ["q", "neighborhood", "cuisine", "min_rating", "price", "sentiment", "aspect", "min_reviews"] as const;
export type FilterKey = (typeof KEYS)[number];

export function toApiFilters(sp: URLSearchParams): Filters {
  const f: Filters = {};
  const g = (k: string) => sp.get(k) ?? "";
  if (g("q")) f.q = g("q");
  if (g("neighborhood")) f.neighborhood = g("neighborhood");
  if (g("cuisine")) f.cuisine = g("cuisine");
  if (g("min_rating") && !Number.isNaN(Number(g("min_rating")))) f.min_rating = Number(g("min_rating"));
  const m = /^(\d*)-(\d*)$/.exec(g("price"));
  if (m) { if (m[1]) f.price_min = Number(m[1]); if (m[2]) f.price_max = Number(m[2]); }
  if (["positive", "neutral", "negative"].includes(g("sentiment"))) f.sentiment = g("sentiment") as SentimentLabel;
  if (ASPECTS.some((a) => a.v === g("aspect"))) f.aspect = g("aspect");
  if (g("min_reviews") && Number(g("min_reviews")) > 0) f.min_reviews = Number(g("min_reviews"));
  return f;
}

/** Filters live in the URL so every view (overview, map, charts) shares them and links are shareable. */
export function useFilters() {
  const [sp, setSp] = useSearchParams();
  const filters = useMemo(() => toApiFilters(sp), [sp]);
  const raw = useMemo(() => Object.fromEntries(KEYS.map((k) => [k, sp.get(k) ?? ""])) as Record<FilterKey, string>, [sp]);
  const set = useCallback((patch: Partial<Record<FilterKey, string | null>>) => {
    setSp((cur) => {
      const n = new URLSearchParams(cur);
      Object.entries(patch).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k)));
      n.delete("focus");
      return n;
    }, { replace: true });
  }, [setSp]);
  const clear = useCallback(() => setSp((cur) => { const n = new URLSearchParams(cur); KEYS.forEach((k) => n.delete(k)); return n; }, { replace: true }), [setSp]);
  const active = KEYS.filter((k) => raw[k]).length;
  const key = JSON.stringify(filters);
  const search = useMemo(() => { const n = new URLSearchParams(); KEYS.forEach((k) => raw[k] && n.set(k, raw[k])); const s = n.toString(); return s ? `?${s}` : ""; }, [raw]);
  return { filters, raw, set, clear, active, key, search };
}
