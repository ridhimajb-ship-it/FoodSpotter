import { useNavigate } from "react-router-dom";
import { ChevronDown, RotateCcw, Search } from "lucide-react";
import type { ReactNode } from "react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { ASPECTS, MIN_REVIEW_OPTIONS, PRICE_RANGES, RATINGS, useFilters } from "../hooks/useFilters";
import type { Suggestion } from "../types";
import SearchBox from "./SearchBox";

function Select({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children: ReactNode }) {
  return (
    <label className="relative block">
      <span className="sr-only">{label}</span>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
        className={`h-10 w-full appearance-none rounded-xl border bg-white pl-3.5 pr-8 text-sm font-medium shadow-soft focus:border-leaf ${value ? "border-leaf text-leaf-dark" : "border-line text-ink"}`}>
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
    </label>
  );
}

/**
 * Search + filters shared by every analytics view. State lives in the URL (see useFilters), so the map, charts,
 * rankings and counts on the page all react to the same selection.
 */
export default function FilterBar({ advanced = true }: { advanced?: boolean }) {
  const { raw, set, clear, active } = useFilters();
  const nav = useNavigate();
  const meta = useFetch((s) => api.meta(s), []);
  const onPick = (s: Suggestion) => {
    if (s.type === "restaurant" && s.restaurant_id) nav(`/restaurants/${s.restaurant_id}`);
    else if (s.type === "neighborhood") set({ neighborhood: s.value, q: null });
    else set({ cuisine: s.value, q: null });
  };
  const hoods = meta.data?.neighborhoods ?? [];
  const cuisines = meta.data?.cuisines ?? [];
  return (
    <section aria-label="Search and filters" className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <form className="flex min-w-[260px] flex-1 items-center gap-2" onSubmit={(e) => { e.preventDefault(); }} role="presentation">
          <div className="min-w-0 flex-1"><SearchBox value={raw.q} onSubmit={(v) => set({ q: v || null })} onPick={onPick} placeholder="Search for restaurants, cuisines or areas…" /></div>
          <button type="button" className="btn btn-primary h-10 px-5" onClick={() => { const el = document.querySelector<HTMLInputElement>('input[aria-label="Search restaurants"]'); set({ q: el?.value.trim() || null }); }}>
            <Search className="h-4 w-4 sm:hidden" aria-hidden /><span className="hidden sm:inline">Search</span>
          </button>
        </form>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-4">
        <Select label="Cuisine" value={raw.cuisine} onChange={(v) => set({ cuisine: v || null })}>
          <option value="">All cuisines</option>
          {cuisines.map((c) => <option key={c.value} value={c.value}>{c.label} ({c.restaurants})</option>)}
          {raw.cuisine && !cuisines.some((c) => c.value === raw.cuisine) && <option value={raw.cuisine}>{raw.cuisine}</option>}
        </Select>
        <Select label="Area" value={raw.neighborhood} onChange={(v) => set({ neighborhood: v || null })}>
          <option value="">All areas</option>
          {hoods.map((n) => <option key={n.key} value={n.key}>{n.label}{n.restaurants ? ` (${n.restaurants})` : ""}</option>)}
        </Select>
        <Select label="Price range (cost for two)" value={raw.price} onChange={(v) => set({ price: v || null })}>
          {PRICE_RANGES.map((p) => <option key={p.v} value={p.v}>{p.v ? p.l : "Price range"}</option>)}
        </Select>
        <Select label="Minimum rating" value={raw.min_rating} onChange={(v) => set({ min_rating: v || null })}>
          {RATINGS.map((p) => <option key={p.v} value={p.v}>{p.v ? p.l : "Rating"}</option>)}
        </Select>
      </div>
      {advanced && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Select label="Dominant review sentiment" value={raw.sentiment} onChange={(v) => set({ sentiment: v || null })}>
            <option value="">Any sentiment</option>
            <option value="positive">Mostly positive</option>
            <option value="neutral">Mostly neutral</option>
            <option value="negative">Mostly negative</option>
          </Select>
          <Select label="Aspect with enough evidence" value={raw.aspect} onChange={(v) => set({ aspect: v || null })}>
            <option value="">Any aspect</option>
            {ASPECTS.map((a) => <option key={a.v} value={a.v}>{a.l} discussed</option>)}
          </Select>
          <Select label="Minimum analysed reviews" value={raw.min_reviews} onChange={(v) => set({ min_reviews: v || null })}>
            {MIN_REVIEW_OPTIONS.map((a) => <option key={a.v} value={a.v}>{a.v ? a.l : "Review count"}</option>)}
          </Select>
          <button type="button" className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl border border-line bg-white text-sm font-semibold text-leaf shadow-soft hover:border-leaf disabled:opacity-40" disabled={!active} onClick={clear}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />{active ? `Clear ${active} filter${active > 1 ? "s" : ""}` : "No filters"}
          </button>
        </div>
      )}
    </section>
  );
}
