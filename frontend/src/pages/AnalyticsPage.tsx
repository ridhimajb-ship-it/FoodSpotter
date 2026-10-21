import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useFilters } from "../hooks/useFilters";
import { fmtInt, pct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import { AspectBars, CuisineBars, EnginePanel, NeighbourhoodBars, SentimentDonut, TimeTrend } from "../components/InsightCharts";
import { Card, Skeleton } from "../components/ui";
import { ErrorBox, NoDataYet } from "../components/StateViews";

function Cloud({ terms, tone }: { terms: { term: string; count: number }[]; tone: string }) {
  if (!terms.length) return <p className="text-sm text-muted">Not enough repeated terms yet.</p>;
  const max = Math.max(...terms.map((t) => t.count));
  return <ul className="flex flex-wrap items-baseline gap-x-3 gap-y-1">{terms.map((t) => <li key={t.term} style={{ fontSize: `${0.85 + (t.count / max) * 0.9}rem`, color: tone }} className="font-display font-semibold" title={`${t.count} reviews`}>{t.term}</li>)}</ul>;
}

export default function AnalyticsPage() {
  const { filters, key, set, active } = useFilters();
  const meta = useFetch((s) => api.meta(s), []);
  const ins = useFetch((s) => api.insights(filters, s), [key]);
  const kw = useFetch((s) => api.keywords(s), []);
  const d = ins.data;
  const minMentions = meta.data?.min_aspect_mentions ?? 5;
  const empty = d?.scope.restaurants_in_database === 0;
  const none = !!d && !empty && d.scope.reviews_analysed === 0;
  return (
    <div className="mx-auto max-w-[1280px] space-y-5 px-4 py-6 sm:px-6 lg:px-7">
      <header>
        <h1 className="text-[2rem] font-bold leading-tight sm:text-4xl">Sentiment insights</h1>
        <p className="mt-1.5 max-w-3xl text-[15px] text-muted">What real customer reviews say, overall and by aspect, area and cuisine. Every chart follows the filters below.</p>
      </header>
      <FilterBar />
      {ins.error && <ErrorBox error={ins.error} onRetry={ins.reload} />}
      {empty && <NoDataYet />}
      {!empty && (
        <>
          {d && (
            <p className="text-sm text-muted" aria-live="polite">
              Based on <strong className="text-ink">{fmtInt(d.scope.reviews_analysed)}</strong> analysed reviews from <strong className="text-ink">{fmtInt(d.scope.restaurants_with_reviews)}</strong> restaurants
              {active ? ` (filtered from ${fmtInt(d.scope.restaurants_in_database)} restaurants in the database)` : ""}.
            </p>
          )}
          {none && <div className="panel px-6 py-8 text-center text-sm text-muted">No analysed reviews match these filters. Loosen a filter to see charts.</div>}
          {!none && (
            <>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card id="a-sent" title="Overall sentiment" subtitle="Positive, neutral and negative reviews.">
                  {!d ? <Skeleton className="h-56" /> : <div className="space-y-4"><SentimentDonut s={d.sentiment} /><EnginePanel e={d.engine} comparison={d.engine_comparison} /></div>}
                </Card>
                <Card id="a-aspect" title="Aspect-based sentiment" subtitle="Food, service, ambience, value, hygiene and waiting time.">
                  {!d ? <Skeleton className="h-56" /> : <AspectBars aspects={d.aspects} minMentions={minMentions} />}
                </Card>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card id="a-hood" title="By neighbourhood" subtitle="Positive share of analysed reviews. Click an area to filter.">
                  {!d ? <Skeleton className="h-56" /> : <NeighbourhoodBars items={d.neighborhoods} onSelect={(k) => set({ neighborhood: k })} />}
                </Card>
                <Card id="a-cuisine" title="By cuisine" subtitle="Cuisines with at least 3 restaurants that have reviews.">
                  {!d ? <Skeleton className="h-56" /> : <CuisineBars items={d.cuisines} />}
                </Card>
              </div>
              <Card id="a-time" title="Sentiment over time" subtitle="Only shown when the reviews carry real dates.">
                {!d ? <Skeleton className="h-20" /> : <TimeTrend t={d.time_trend} />}
              </Card>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card id="a-kwp" title="What positive reviews talk about" subtitle="Terms that stand out in positive reviews (whole database).">
                  {kw.data ? <Cloud terms={kw.data.distinctive.positive} tone="#1D5B38" /> : <Skeleton className="h-20" />}
                </Card>
                <Card id="a-kwn" title="What negative reviews talk about" subtitle="Terms that stand out in negative reviews (whole database).">
                  {kw.data ? <Cloud terms={kw.data.distinctive.negative} tone="#8C2A20" /> : <Skeleton className="h-20" />}
                </Card>
              </div>
              {d && d.sentiment.n > 0 && <p className="text-xs text-muted">Positive share {pct(d.sentiment.positive_share)} · negative {pct(d.sentiment.negative_share)}. Keyword terms are computed with the active engine’s labels.</p>}
            </>
          )}
        </>
      )}
    </div>
  );
}
