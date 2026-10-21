import { useState } from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useCompare } from "../hooks/useCompare";
import { cuisineText, fmtInt, pct } from "../lib/format";
import SearchBox from "../components/SearchBox";
import SentimentBar from "../components/SentimentBar";
import { GemBadge } from "../components/Badges";
import { EmptyNote, ErrorBox, Loading, PageHeader } from "../components/StateViews";
import type { AspectStat, CompareItem } from "../types";

const ASPECT_ROWS = [["food", "Food sentiment"], ["service", "Service sentiment"], ["ambience", "Ambience sentiment"], ["affordability", "Affordability sentiment"]] as const;

function AspectCell({ a, min }: { a: AspectStat | undefined; min: number }) {
  if (!a || !a.sufficient_evidence) return <span className="text-muted">Not enough mentions ({a?.mentions ?? 0} of {min})</span>;
  const tone = (a.score ?? 0) > 0.2 ? "#2E7D4F" : (a.score ?? 0) < -0.2 ? "#B3382C" : "#8A7F73";
  return <span><strong style={{ color: tone }}>{(a.score ?? 0) > 0 ? "+" : ""}{(a.score ?? 0).toFixed(2)}</strong> <span className="text-xs text-muted">{pct(a.positive_share)} positive · {a.mentions} mentions</span></span>;
}

export default function ComparePage() {
  const cmp = useCompare();
  const data = useFetch((s) => api.compare(cmp.ids, s), [cmp.ids.join(",")], cmp.ids.length >= 2);
  const items = data.data?.items ?? [];
  const min = data.data?.min_aspect_mentions ?? 5;

  const row = (label: string, render: (r: CompareItem) => React.ReactNode) => (
    <tr className="border-b border-line align-top last:border-0">
      <th scope="row" className="w-40 bg-paper/60 px-4 py-3 text-left font-medium text-muted">{label}</th>
      {items.map((r) => <td key={r.id} className="px-4 py-3">{render(r)}</td>)}
    </tr>
  );

  return (
    <div className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-7">
      <PageHeader title="Compare restaurants">Pick two or three restaurants to compare their ratings, review sentiment and how confident we are in each.</PageHeader>
      <div className="panel mb-6 p-4">
        <h2 className="mb-2 font-bold">Selected ({cmp.ids.length} of 3)</h2>
        <PickerBar />
        <p className="mt-2 text-sm text-muted">You can also add restaurants from the map, the lists, or any restaurant page.</p>
      </div>

      {cmp.ids.length < 2 ? (
        <EmptyNote title={cmp.ids.length === 0 ? "Nothing to compare yet" : "Add one more restaurant"}>
          Search above for restaurants to compare, or <Link className="font-semibold text-leaf underline" to="/explore">browse the map</Link> and use the + button.
        </EmptyNote>
      ) : data.loading && !data.data ? <Loading /> : data.error ? <ErrorBox error={data.error} onRetry={data.reload} /> : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <caption className="sr-only">Side-by-side comparison of selected restaurants</caption>
            <thead>
              <tr className="border-b border-line">
                <td className="bg-paper/60" />
                {items.map((r) => (
                  <th key={r.id} scope="col" className="px-4 py-4 align-top">
                    <div className="flex items-start justify-between gap-2">
                      <div><Link to={`/restaurants/${r.id}`} className="font-display text-lg font-bold hover:underline">{r.name}</Link>
                        <p className="mt-0.5 text-xs font-normal text-muted">{cuisineText(r.cuisines)} · {r.neighborhood_label ?? "Area unknown"}</p><div className="mt-1"><GemBadge r={r} /></div></div>
                      <button className="btn btn-ghost px-1.5 py-1" aria-label={`Remove ${r.name}`} onClick={() => cmp.remove(r.id)}><X className="h-4 w-4" aria-hidden /></button>
                    </div>
                  </th>))}
              </tr>
            </thead>
            <tbody>
              {row("Rating", (r) => r.rating != null ? <span className="font-display text-xl font-bold">{r.rating.toFixed(1)}</span> : <span className="text-muted">Not available</span>)}
              {row("Ratings counted", (r) => fmtInt(r.rating_count))}
              {row("Reviews analysed", (r) => fmtInt(r.review_count))}
              {row("Overall sentiment", (r) => r.sentiment ? <SentimentBar counts={{ positive: r.sentiment.positive, neutral: r.sentiment.neutral, negative: r.sentiment.negative }} /> : <span className="text-muted">No reviews analysed</span>)}
              {ASPECT_ROWS.map(([k, l]) => row(l, (r) => <AspectCell a={r.aspects[k]} min={min} />))}
              {row("Popularity score", (r) => r.popularity_score != null ? <span className="font-display text-xl font-bold text-leaf">{r.popularity_score.toFixed(0)}</span> : <span className="text-muted">Not scored</span>)}
              {row("Confidence", (r) => r.confidence != null ? (
                <div><span className="font-semibold">{pct(r.confidence)}</span><div className="mt-1 h-1.5 w-28 rounded-full bg-line"><div className="h-1.5 rounded-full bg-leaf" style={{ width: pct(r.confidence) }} /></div>
                  <span className="mt-1 block text-xs text-muted">{r.confidence < 0.5 ? "Limited evidence" : "Reasonable evidence"}</span></div>) : <span className="text-muted">Not available</span>)}
            </tbody>
          </table>
          <p className="border-t border-line px-4 py-3 text-xs text-muted">Aspect scores run from −1 (all mentions negative) to +1 (all positive) and appear only with at least {min} mentions. Confidence reflects how many ratings and reviews back the numbers.</p>
        </div>
      )}
    </div>
  );
}

function NameChip({ id, hint }: { id: number; hint?: string }) {
  const cmp = useCompare();
  const r = useFetch((sig) => api.restaurant(id, sig), [id], !hint);
  const name = hint ?? r.data?.name ?? (r.error ? `Restaurant ${id} (unavailable)` : "Loading…");
  return (
    <li className="flex items-center gap-1 rounded-full border border-line bg-paper pl-3 text-sm font-medium">
      {name}<button className="rounded-full p-1.5 hover:bg-line" aria-label={`Remove ${name}`} onClick={() => cmp.remove(id)}><X className="h-3.5 w-3.5" aria-hidden /></button>
    </li>
  );
}

function PickerBar() {
  const cmp = useCompare();
  const [names, setNames] = useState<Record<number, string>>({});
  const [note, setNote] = useState<string | null>(null);
  return (
    <div>
      <ul className="mb-3 flex flex-wrap gap-2">
        {cmp.ids.map((id) => <NameChip key={id} id={id} hint={names[id]} />)}
        {cmp.ids.length > 0 && <li><button className="btn btn-ghost px-2.5 py-1 text-xs" onClick={cmp.clear}>Clear all</button></li>}
      </ul>
      <SearchBox value="" placeholder="Search for a restaurant to add" onSubmit={() => {}}
        onPick={(s) => {
          if (s.type !== "restaurant" || !s.restaurant_id) { setNote("Choose a restaurant from the suggestions to add it."); return; }
          const ok = cmp.add(s.restaurant_id);
          setNames((n) => ({ ...n, [s.restaurant_id!]: s.label }));
          setNote(ok ? null : "You can compare up to three restaurants. Remove one first.");
        }} />
      {note && <p role="status" className="mt-2 text-sm text-chili-dark">{note}</p>}
    </div>
  );
}
