import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BarChart3, Gem, Layers, MapPinned, MessageSquareText, Smile, Utensils, Database, SearchX } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useFilters } from "../hooks/useFilters";
import type { HotspotMetric } from "../types";
import { fmtInt, pct } from "../lib/format";
import FilterBar from "../components/FilterBar";
import RestaurantMap from "../components/RestaurantMap";
import GemList from "../components/GemList";
import { AspectBars, CuisineBars, EnginePanel, NeighbourhoodBars, PipelineStrip, SentimentDonut, TimeTrend } from "../components/InsightCharts";
import { Card, KpiCard, Skeleton, ViewAll } from "../components/ui";
import { ErrorBox, NoDataYet } from "../components/StateViews";

type Layer = "sentiment" | "gems" | HotspotMetric;
const LAYERS: { v: Layer; l: string; note: string }[] = [
  { v: "sentiment", l: "Review sentiment", note: "Pins coloured by each restaurant’s positive share of analysed reviews." },
  { v: "gems", l: "Hidden gems", note: "Only restaurants that meet every hidden-gem criterion." },
  { v: "reviews", l: "Heatmap: review volume", note: "Where analysed reviews are concentrated." },
  { v: "popularity", l: "Heatmap: popularity score", note: "Weighted by the evidence-based popularity score." },
  { v: "density", l: "Heatmap: restaurant density", note: "Where discovered restaurants cluster (OpenStreetMap)." },
];

export default function OverviewPage() {
  const { filters, key, active, clear, set, search } = useFilters();
  const nav = useNavigate();
  const [layer, setLayer] = useState<Layer>("sentiment");
  const meta = useFetch((s) => api.meta(s), []);
  const ins = useFetch((s) => api.insights(filters, s), [key]);
  const list = useFetch((s) => api.restaurants({ ...filters, limit: 5000 }, s), [key]);
  const isHeat = layer === "reviews" || layer === "popularity" || layer === "density";
  const heat = useFetch((s) => api.hotspots(layer as HotspotMetric, filters, s), [key, layer], isHeat);

  const items = useMemo(() => {
    const all = list.data?.items ?? [];
    return layer === "gems" ? all.filter((r) => r.gem_status === "qualified") : all;
  }, [list.data, layer]);

  const d = ins.data;
  const dbEmpty = d ? d.scope.restaurants_in_database === 0 : meta.data?.totals.restaurants === 0;
  const minMentions = meta.data?.min_aspect_mentions ?? d?.aspects[0]?.min_mentions_required ?? 5;
  const noMatch = !!d && !dbEmpty && d.scope.restaurants === 0;
  const layerNote = LAYERS.find((l) => l.v === layer)!.note;

  return (
    <div className="mx-auto max-w-[1280px] space-y-5 px-4 py-6 sm:px-6 lg:px-7">
      <header>
        <h1 className="text-[2rem] font-bold leading-tight sm:text-[2.5rem]">Discover Bengaluru, one review at a time</h1>
        <p className="mt-2 max-w-2xl text-[15px] text-muted">Explore restaurants, analyse real customer reviews, find hidden gems and see what people say about food, service, ambience and value.</p>
      </header>

      <FilterBar />

      {ins.error && <ErrorBox error={ins.error} onRetry={ins.reload} />}
      {dbEmpty && <NoDataYet />}

      {!dbEmpty && (
        <>
          <section aria-label="Key figures" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {!d ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[92px]" />) : (
              <>
                <KpiCard tone="chili" icon={<Utensils className="h-7 w-7" />} label="Restaurants discovered" value={fmtInt(d.scope.restaurants)}
                  sub={active ? `of ${fmtInt(d.scope.restaurants_in_database)} in the database (OpenStreetMap)` : "locations from OpenStreetMap"} />
                <KpiCard tone="leaf" icon={<Database className="h-7 w-7" />} label="With matched real reviews" value={fmtInt(d.scope.restaurants_with_reviews)}
                  sub={d.scope.restaurants ? `${pct(d.scope.restaurants_with_reviews / d.scope.restaurants)} of discovered restaurants` : "–"} />
                <KpiCard tone="saffron" icon={<MessageSquareText className="h-7 w-7" />} label="Reviews analysed" value={fmtInt(d.scope.reviews_analysed)}
                  sub={d.engine.active === "bert" ? "sentiment: BERT" : "sentiment: VADER baseline"} />
                <KpiCard tone="chili" icon={<Gem className="h-7 w-7" />} label="Hidden gems identified" value={fmtInt(d.hidden_gems.status_counts.qualified ?? 0)}
                  sub={`${fmtInt(Object.values(d.hidden_gems.status_counts).reduce((a, b) => a + b, 0))} restaurants assessed with review evidence`} />
              </>
            )}
          </section>

          {noMatch && (
            <div className="panel flex flex-col items-center gap-2 px-6 py-10 text-center">
              <SearchX className="h-7 w-7 text-muted" aria-hidden />
              <h2 className="card-title">No restaurants match these filters</h2>
              <p className="max-w-md text-sm text-muted">The database has {fmtInt(d!.scope.restaurants_in_database)} restaurants, but none satisfy every selected filter. Loosen one of them to see charts again.</p>
              <button className="btn btn-primary mt-1" onClick={clear}>Clear all filters</button>
            </div>
          )}

          {!noMatch && (
            <>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
                <Card id="map-title" icon={<MapPinned className="h-5 w-5" />} title="Bengaluru restaurant map"
                  subtitle={`${layerNote} Showing ${fmtInt(items.length)} restaurant${items.length === 1 ? "" : "s"}.`}
                  action={
                    <label className="relative block shrink-0">
                      <span className="sr-only">Map layer</span>
                      <Layers className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" aria-hidden />
                      <select className="h-9 appearance-none rounded-lg border border-line bg-white pl-8 pr-3 text-[13px] font-medium" value={layer} onChange={(e) => setLayer(e.target.value as Layer)} aria-label="Map layer">
                        {LAYERS.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}
                      </select>
                    </label>}>
                  <div className="relative h-[380px] overflow-hidden rounded-xl border border-line sm:h-[430px]">
                    <RestaurantMap className="h-full" restaurants={isHeat ? list.data?.items ?? [] : items} colorBy="sentiment"
                      fitKey={`${key}|${layer === "gems"}`} heat={isHeat && heat.data ? { points: heat.data.points, metric: layer as HotspotMetric, maxWeight: heat.data.max_weight } : null}
                      onOpen={(id) => nav(`/restaurants/${id}`)} />
                    {isHeat && heat.data && heat.data.n_points === 0 && <p className="absolute inset-x-6 top-4 z-[500] rounded-lg bg-white/95 px-3 py-2 text-center text-sm text-muted shadow">No points to show for this layer with the current filters.</p>}
                    {(list.loading || heat.loading) && <span role="status" className="absolute right-3 top-3 z-[500] rounded-full bg-white px-3 py-1 text-xs shadow">Updating…</span>}
                  </div>
                  <div className="mt-2 text-right"><Link className="text-sm font-semibold text-leaf hover:underline" to={`/explore${search}`}>Open the full map with ranked list →</Link></div>
                </Card>

                <Card id="gems-title" icon={<Gem className="h-5 w-5 text-chili" />} title="Top hidden gems" action={<ViewAll to={`/hidden-gems${search}`} />}
                  subtitle="Well-reviewed restaurants that few people have rated, ranked by evidence.">
                  {!d ? <Skeleton className="h-64" /> : d.hidden_gems.items.length === 0 ? (
                    <div className="rounded-xl bg-paper px-4 py-6 text-sm text-muted">
                      <p className="font-semibold text-ink">No hidden gems in this selection.</p>
                      <p className="mt-1">A restaurant qualifies with at least {d.hidden_gems.criteria.min_analysed_reviews} analysed reviews, a confidence-adjusted positive share of {pct(d.hidden_gems.criteria.min_positive_confidence_bound)}+, an adjusted rating of {d.hidden_gems.criteria.min_adjusted_rating}+, and low visibility. Of {fmtInt(Object.values(d.hidden_gems.status_counts).reduce((a, b) => a + b, 0))} assessed restaurants, {fmtInt(d.hidden_gems.status_counts.insufficient_evidence ?? 0)} have too few reviews.</p>
                    </div>
                  ) : <GemList items={d.hidden_gems.items.slice(0, 5)} compact />}
                </Card>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card id="aspect-title" icon={<BarChart3 className="h-5 w-5" />} title="Aspect-based sentiment" subtitle="What reviewers say about food, service, ambience, value, hygiene and waiting time.">
                  {!d ? <Skeleton className="h-64" /> : d.scope.reviews_analysed === 0 ? <p className="rounded-lg bg-paper px-3 py-4 text-sm text-muted">No analysed reviews in this selection.</p> : <AspectBars aspects={d.aspects} minMentions={minMentions} />}
                </Card>
                <Card id="sent-title" icon={<Smile className="h-5 w-5" />} title="Review sentiment" subtitle="Positive, neutral and negative reviews in the current selection.">
                  {!d ? <Skeleton className="h-64" /> : d.scope.reviews_analysed === 0 ? <p className="rounded-lg bg-paper px-3 py-4 text-sm text-muted">No analysed reviews in this selection.</p> : (
                    <div className="space-y-4"><SentimentDonut s={d.sentiment} /><EnginePanel e={d.engine} comparison={d.engine_comparison} /></div>
                  )}
                </Card>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card id="hood-title" icon={<MapPinned className="h-5 w-5" />} title="Sentiment by neighbourhood" subtitle="How positive each area’s analysed reviews are.">
                  {!d ? <Skeleton className="h-56" /> : d.neighborhoods.length === 0 ? <p className="rounded-lg bg-paper px-3 py-4 text-sm text-muted">No neighbourhood has matched reviews yet.</p> : <NeighbourhoodBars items={d.neighborhoods} onSelect={(k) => set({ neighborhood: k })} />}
                </Card>
                {d?.time_trend.available ? (
                  <Card id="trend-title" icon={<BarChart3 className="h-5 w-5" />} title="Review sentiment over time" subtitle={`Share of positive reviews by month (${fmtInt(d.time_trend.dated_reviews)} dated reviews).`}><TimeTrend t={d.time_trend} /></Card>
                ) : (
                  <Card id="cuisine-title" icon={<Utensils className="h-5 w-5" />} title="Sentiment by cuisine" subtitle="Positive share of analysed reviews (cuisines with 3+ reviewed restaurants).">
                    {!d ? <Skeleton className="h-56" /> : <><CuisineBars items={d.cuisines} /><div className="mt-3"><TimeTrend t={d.time_trend} /></div></>}
                  </Card>
                )}
              </div>

              <Card id="pipe-title" icon={<Database className="h-5 w-5" />} title="Where these numbers come from" action={<ViewAll to="/methodology">Methodology &amp; data</ViewAll>}
                subtitle="Real review text → cleaning → restaurant matching → sentiment model → aspect extraction → aggregation → map &amp; ranking. Counts below cover the whole database, not the current filters.">
                {d ? <PipelineStrip p={d.pipeline} /> : <Skeleton className="h-16" />}
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
