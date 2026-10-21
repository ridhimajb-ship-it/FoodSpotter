import { Link } from "react-router-dom";
import { ArrowRight, Check, MapPinned, Navigation, Plus, X } from "lucide-react";
import type { Restaurant } from "../types";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useCompare } from "../hooks/useCompare";
import { cuisineText, directionsUrl, fmtInt, sourceLabel } from "../lib/format";
import SentimentBar from "./SentimentBar";
import { GemBadge, RecheckBadge } from "./Badges";
import { Loading } from "./StateViews";

/** Quick-look panel for the Explore page. Everything shown comes from the API; nothing is inferred client-side. */
export default function RestaurantPanel({ r, onClose }: { r: Restaurant; onClose: () => void }) {
  const cmp = useCompare();
  const sent = useFetch((s) => api.sentiment(r.id, s), [r.id]);
  const asp = useFetch((s) => api.aspects(r.id, s), [r.id]);
  const inCmp = cmp.has(r.id);
  return (
    <aside aria-label={`Details for ${r.name}`} className="panel flex max-h-full flex-col overflow-hidden shadow-lift">
      <div className="flex items-start justify-between gap-2 border-b border-line p-4">
        <div className="min-w-0">
          <h2 className="text-xl font-bold leading-tight">{r.name}</h2>
          <p className="mt-0.5 text-sm text-muted">{r.address ?? "Address not available"}</p>
          <p className="mt-0.5 text-sm">{cuisineText(r.cuisines)} · {r.neighborhood_label ?? "Area unknown"}</p>
        </div>
        <button className="btn btn-ghost px-2 py-1.5" onClick={onClose} aria-label="Close details"><X className="h-4 w-4" aria-hidden /></button>
      </div>
      <div className="space-y-4 overflow-y-auto p-4">
        <div className="flex flex-wrap items-center gap-2"><GemBadge r={r} /><RecheckBadge r={r} />
          {r.popularity_rank != null && <span className="rounded-full bg-leaf-soft px-2 py-0.5 text-xs font-semibold text-leaf-dark">Popularity rank #{r.popularity_rank}</span>}
        </div>
        <dl className="grid grid-cols-3 gap-3 text-sm">
          <div><dt className="text-xs text-muted">Rating</dt><dd className="font-display text-lg font-bold">{r.rating != null ? r.rating.toFixed(1) : "–"}</dd></div>
          <div><dt className="text-xs text-muted">Votes</dt><dd className="font-display text-lg font-bold">{fmtInt(r.rating_count)}</dd></div>
          <div><dt className="text-xs text-muted">Score</dt><dd className="font-display text-lg font-bold">{r.popularity_score != null ? r.popularity_score.toFixed(0) : "–"}</dd></div>
        </dl>
        {r.rating != null && <p className="-mt-2 text-xs text-muted">Rating source: {sourceLabel(r.rating_source)}.</p>}
        <section aria-labelledby="p-sent">
          <h3 id="p-sent" className="mb-1.5 text-sm font-semibold">What reviewers say <span className="font-normal text-muted">· {sent.data?.engine ? (sent.data.engine.active === "bert" ? "BERT" : "VADER baseline") : "…"}</span></h3>
          {sent.loading ? <Loading label="Analysing reviews…" /> : sent.error ? <p className="text-sm text-neg">{sent.error.message}</p> :
            sent.data?.available && sent.data.distribution ? (
              <>
                <SentimentBar counts={sent.data.distribution} />
                {asp.data?.summary.text ? <p className="mt-2 text-sm">{asp.data.summary.text}</p> : <p className="mt-2 text-sm text-muted">{asp.data?.summary.reason}</p>}
              </>
            ) : <p className="text-sm text-muted">{sent.data?.message ?? "No verified reviews are available for this restaurant."}</p>}
        </section>
        {r.popularity_score == null && <p className="text-sm text-muted">This restaurant isn't ranked: there is no rating or analysed review text for it.</p>}
        <div className="flex flex-wrap gap-2">
          <Link to={`/restaurants/${r.id}`} className="btn btn-primary">Full details <ArrowRight className="h-4 w-4" aria-hidden /></Link>
          {r.latitude != null && r.longitude != null && <a className="btn btn-ghost" href={directionsUrl(r.latitude, r.longitude)} target="_blank" rel="noreferrer"><Navigation className="h-4 w-4" aria-hidden />Directions</a>}
          <button className="btn btn-ghost" onClick={() => cmp.toggle(r.id)} disabled={!inCmp && cmp.full} aria-pressed={inCmp}>
            {inCmp ? <Check className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}{inCmp ? "In comparison" : "Compare"}
          </button>
        </div>
        <p className="flex items-center gap-1 text-xs text-muted"><MapPinned className="h-3.5 w-3.5" aria-hidden />Location © OpenStreetMap contributors</p>
      </div>
    </aside>
  );
}
