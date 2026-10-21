import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Gem } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useFilters } from "../hooks/useFilters";
import { fmtInt, pct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import GemList from "../components/GemList";
import RestaurantMap from "../components/RestaurantMap";
import { Card } from "../components/ui";
import { EmptyNote, ErrorBox, Loading, NoDataYet } from "../components/StateViews";

export default function HiddenGemsPage() {
  const nav = useNavigate();
  const { filters, key } = useFilters();
  const meta = useFetch((s) => api.meta(s), []);
  const g = useFetch((s) => api.gems({ ...filters, limit: 50 }, s), [key]);
  const [sel, setSel] = useState<number | null>(null);
  const [focus, setFocus] = useState<{ id: number; n: number } | null>(null);

  if (meta.data?.totals.restaurants === 0) return <div className="mx-auto max-w-3xl px-4 py-8"><NoDataYet /></div>;
  const c = g.data?.criteria;
  return (
    <div className="mx-auto max-w-[1280px] space-y-5 px-4 py-6 sm:px-6 lg:px-7">
      <header>
        <h1 className="text-[2rem] font-bold leading-tight sm:text-4xl">Hidden gems</h1>
        <p className="mt-1.5 max-w-3xl text-[15px] text-muted">Restaurants whose real reviews are consistently positive but that fewer people have rated. A place must clear a minimum amount of review evidence first, so a handful of glowing reviews is never enough.</p>
      </header>
      <FilterBar />
      {c && (
        <details className="panel p-4 text-sm">
          <summary className="cursor-pointer font-semibold">How a restaurant qualifies</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
            <li>At least <strong className="text-ink">{c.min_analysed_reviews}</strong> analysed reviews.</li>
            <li>Confidence-adjusted positive share (Wilson lower bound) of at least <strong className="text-ink">{pct(c.min_positive_confidence_bound)}</strong>.</li>
            <li>Adjusted rating of at least <strong className="text-ink">{c.min_adjusted_rating}</strong>.</li>
            <li>Low visibility: no higher than the {Math.round(c.max_visibility_percentile * 100)}th percentile for number of ratings.</li>
          </ul>
        </details>
      )}
      {g.loading && !g.data ? <Loading /> : g.error ? <ErrorBox error={g.error} onRetry={g.reload} /> :
        g.data && g.data.items.length === 0 ? (
          <EmptyNote title="No hidden gems in this selection" icon={<Gem className="h-7 w-7" />}>
            {g.data.insufficient_evidence_count > 0
              ? `${fmtInt(g.data.insufficient_evidence_count)} restaurants have too few analysed reviews to be judged. Importing more reviews, or loosening a filter, may surface some.`
              : "Import the review dataset to evaluate restaurants for this list."}
          </EmptyNote>
        ) : g.data && (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Card id="gem-list" icon={<Gem className="h-5 w-5 text-chili" />} title={`${g.data.items.length} hidden gem${g.data.items.length === 1 ? "" : "s"}`}
              subtitle={g.data.insufficient_evidence_count > 0 ? `${fmtInt(g.data.insufficient_evidence_count)} other restaurants don't have enough reviews to judge.` : "Ranked by gem score; the evidence behind each is shown."}>
              <GemList items={g.data.items} />
            </Card>
            <div className="h-[460px] overflow-hidden rounded-2xl border border-line shadow-soft lg:sticky lg:top-4">
              <RestaurantMap className="h-full" restaurants={g.data.items} selectedId={sel} focus={focus} fitKey={key} colorBy="sentiment"
                onSelect={(r) => { setSel(r.id); setFocus((f) => ({ id: r.id, n: (f?.n ?? 0) + 1 })); }} onOpen={(id) => nav(`/restaurants/${id}`)} />
            </div>
          </div>
        )}
    </div>
  );
}
