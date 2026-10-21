import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import type { HotspotMetric } from "../types";
import MenuRow from "../components/MenuRow";
import RestaurantMap from "../components/RestaurantMap";
import { InfoNote } from "../components/Badges";
import { EmptyNote, ErrorBox, Loading, NoDataYet, PageHeader } from "../components/StateViews";

const METRICS: { v: HotspotMetric; l: string }[] = [
  { v: "density", l: "Restaurant density" }, { v: "reviews", l: "Review activity" }, { v: "popularity", l: "Popularity score" },
];

export default function PopularPage() {
  const [hood, setHood] = useState("");
  const [metric, setMetric] = useState<HotspotMetric>("density");
  const meta = useFetch((s) => api.meta(s), []);
  const pop = useFetch((s) => api.popular({ neighborhood: hood || undefined, limit: 30 }, s), [hood]);
  const heat = useFetch((s) => api.hotspots(metric, {}, s), [metric]);
  const hoods = useFetch((s) => api.neighborhoods(s), []);
  const cuisines = useFetch((s) => api.cuisines(s), []);
  const label = pop.data?.label ?? "Popular Restaurants";

  if (meta.data?.totals.restaurants === 0) return <div className="mx-auto max-w-3xl px-4 py-8"><NoDataYet /></div>;
  return (
    <div className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-7">
      <PageHeader title={label}>{pop.data?.basis_note ?? "Ranked by rating, review volume and review sentiment, adjusted for how much evidence each restaurant has."}</PageHeader>

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <section aria-labelledby="rank-h">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 id="rank-h" className="text-xl font-bold">Top restaurants</h2>
            <select className="field w-auto" aria-label="Filter by neighbourhood" value={hood} onChange={(e) => setHood(e.target.value)}>
              <option value="">All neighbourhoods</option>
              {meta.data?.neighborhoods.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}
            </select>
          </div>
          <div className="panel">
            {pop.loading && !pop.data ? <Loading /> : pop.error ? <div className="p-3"><ErrorBox error={pop.error} onRetry={pop.reload} /></div> :
              pop.data && pop.data.items.length === 0 ? <div className="p-3"><EmptyNote title="Nothing ranked yet">Restaurants are ranked once they have a rating or analysed reviews. Import the review dataset to populate this list.</EmptyNote></div> :
              <ul>{pop.data?.items.map((r) => <MenuRow key={r.id} r={r} rank={r.popularity_rank ?? undefined} />)}</ul>}
          </div>
          <p className="mt-2 text-xs text-muted">The number on the right is the popularity score out of 100. Open a restaurant to see how it was calculated.</p>
          {pop.data?.trending_available && (
            <div className="panel mt-6 p-4"><h3 className="mb-2 font-bold">Reviews over time</h3>
              <ResponsiveContainer width="100%" height={200}><LineChart data={pop.data.time_trend}><CartesianGrid stroke="#E6DAC4" /><XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} /><Tooltip /><Line dataKey="reviews" stroke="#B8441C" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>
          )}
        </section>

        <div className="space-y-6">
          <section aria-labelledby="heat-h">
            <h2 id="heat-h" className="mb-2 text-xl font-bold">Hotspot map</h2>
            <div role="radiogroup" aria-label="Heatmap measure" className="mb-2 flex flex-wrap gap-1.5">
              {METRICS.map((m) => <button key={m.v} role="radio" aria-checked={metric === m.v} className="chip" aria-pressed={metric === m.v} onClick={() => setMetric(m.v)}>{m.l}</button>)}
            </div>
            <div className="panel h-80 overflow-hidden">
              {heat.error ? <div className="p-3"><ErrorBox error={heat.error} onRetry={heat.reload} /></div> :
                <RestaurantMap className="h-full" heat={heat.data && heat.data.points.length ? { points: heat.data.points, metric, maxWeight: heat.data.max_weight } : null} />}
            </div>
            <div className="mt-2" aria-live="polite">{heat.loading ? <p className="text-sm text-muted">Loading…</p> : heat.data && <InfoNote>{heat.data.description} ({heat.data.n_points} points)</InfoNote>}</div>
            {heat.data && heat.data.n_points === 0 && <p className="mt-2 text-sm text-muted">No data for this measure yet.</p>}
          </section>

          <section aria-labelledby="hood-h" className="panel p-4">
            <h2 id="hood-h" className="mb-1 text-lg font-bold">Neighbourhoods by average popularity score</h2>
            {hoods.loading ? <Loading /> : hoods.error ? <ErrorBox error={hoods.error} /> : (() => {
              const rows = (hoods.data?.items ?? []).filter((h) => h.mean_popularity != null).map((h) => ({ name: h.label, score: h.mean_popularity, n: h.rated_restaurants }));
              return rows.length ? (
                <div role="img" aria-label={`Average popularity by neighbourhood: ${rows.map((r) => `${r.name} ${r.score}`).join(", ")}`}>
                  <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 34)}><BarChart data={rows} layout="vertical" margin={{ left: 12, right: 16 }}><CartesianGrid horizontal={false} stroke="#E6DAC4" /><XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="name" width={96} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="score" name="Mean score" fill="#1E4D3B" /></BarChart></ResponsiveContainer>
                </div>) : <p className="text-sm text-muted">No scored restaurants yet.</p>;
            })()}
          </section>

          <section aria-labelledby="cui-h" className="panel p-4">
            <h2 id="cui-h" className="mb-1 text-lg font-bold">Cuisines by average popularity score</h2>
            {cuisines.loading ? <Loading /> : cuisines.error ? <ErrorBox error={cuisines.error} /> : cuisines.data && cuisines.data.popularity.length ? (
              <>
                <div role="img" aria-label={`Average popularity by cuisine: ${cuisines.data.popularity.slice(0, 10).map((c) => `${c.cuisine} ${c.mean_popularity}`).join(", ")}`}>
                  <ResponsiveContainer width="100%" height={Math.max(160, Math.min(10, cuisines.data.popularity.length) * 30)}><BarChart data={cuisines.data.popularity.slice(0, 10)} layout="vertical" margin={{ left: 12, right: 16 }}><CartesianGrid horizontal={false} stroke="#E6DAC4" /><XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="cuisine" width={96} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="mean_popularity" name="Mean score" fill="#B8441C" /></BarChart></ResponsiveContainer>
                </div>
                <p className="mt-1 text-xs text-muted">Only cuisines with at least {cuisines.data.min_restaurants_for_popularity} scored restaurants are shown.</p>
              </>
            ) : <p className="text-sm text-muted">Not enough scored restaurants with a listed cuisine yet.</p>}
          </section>
        </div>
      </div>
    </div>
  );
}
