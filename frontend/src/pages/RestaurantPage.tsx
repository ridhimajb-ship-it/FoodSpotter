import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowLeft, Check, ExternalLink, MapPin, Navigation, Plus, ShieldCheck, Star } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useCompare } from "../hooks/useCompare";
import { cuisineText, fmtDate, fmtInt, pct, sourceLabel, SENTIMENT_COLOR, SENTIMENT_TEXT } from "../lib/format";
import type { ReviewItem, SentimentLabel } from "../types";
import { ASPECTS } from "../hooks/useFilters";
import { Card, ShareBar, Tag } from "../components/ui";
import { EnginePanel } from "../components/InsightCharts";
import AspectChart from "../components/AspectChart";
import RestaurantMap from "../components/RestaurantMap";
import SentimentBar from "../components/SentimentBar";
import { GemBadge, InfoNote, RecheckBadge } from "../components/Badges";
import { EmptyNote, ErrorBox, Loading } from "../components/StateViews";

const PAGE = 10;
const HIST_COLORS = ["#B3382C", "#D98B80", "#8A7F73", "#7FB58F", "#2E7D4F"];

function Section({ id, title, children, hint }: { id: string; title: string; children: React.ReactNode; hint?: string }) {
  return <Card id={id} title={title} subtitle={hint}>{children}</Card>;
}

const STAR_COLORS = ["#B3382C", "#D98B80", "#8A7F73", "#7FB58F", "#2E7D4F"];

/** One review with the model output that produced its label. BERT and VADER are always labelled as such. */
function ReviewCard({ r }: { r: ReviewItem }) {
  const b = r.bert;
  const lab = (l: SentimentLabel) => SENTIMENT_TEXT[l];
  return (
    <li className="rounded-xl border border-line bg-paper/60 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
        {b ? (
          <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-semibold text-white" style={{ background: SENTIMENT_COLOR[b.label] }} title={`${b.model_id}${b.model_revision ? ` @ ${b.model_revision}` : ""}`}>
            BERT: {lab(b.label)} · {Math.round(b.confidence * 100)}% confidence
          </span>
        ) : r.sentiment ? (
          <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-semibold text-white" style={{ background: SENTIMENT_COLOR[r.sentiment.label] }}>
            VADER baseline: {lab(r.sentiment.label)} ({r.sentiment.compound.toFixed(2)})
          </span>
        ) : null}
        {b && r.vader && <span className="rounded-full border border-line px-2 py-0.5 text-muted">VADER baseline: {lab(r.vader.label)} ({r.vader.compound.toFixed(2)}){r.vader.label !== b.label ? " – differs" : ""}</span>}
        {r.rating != null && <span className="inline-flex items-center gap-0.5 font-semibold"><Star className="h-3 w-3 fill-saffron text-saffron" aria-hidden />{r.rating.toFixed(1)} given by reviewer</span>}
        <span className="text-muted">{r.date_note ?? fmtDate(r.reviewed_at)}</span>
        {b?.truncated && <Tag tone="chili">Long review – BERT read only the first 512 tokens</Tag>}
      </div>
      <p className="whitespace-pre-line text-[0.95rem] leading-relaxed">“{r.text}”</p>
      {b && (
        <details className="mt-2 text-xs text-muted">
          <summary className="cursor-pointer font-medium text-leaf">BERT star probabilities</summary>
          <div className="mt-1.5 flex items-end gap-1.5" role="img" aria-label={`Probability of 1 to 5 stars: ${b.star_probabilities.map((p, i) => `${i + 1} star ${Math.round(p * 100)}%`).join(", ")}`}>
            {b.star_probabilities.map((p, i) => (
              <div key={i} className="flex w-9 flex-col items-center gap-0.5">
                <span>{Math.round(p * 100)}%</span><div className="w-full rounded-t" style={{ height: `${Math.max(2, p * 56)}px`, background: STAR_COLORS[i] }} /><span>{i + 1}★</span>
              </div>
            ))}
            <p className="ml-2 max-w-[220px] leading-snug">Mapped to negative (1–2★), neutral (3★), positive (4–5★). Expected stars: {b.expected_stars?.toFixed(1) ?? "–"}.</p>
          </div>
        </details>
      )}
      {r.aspects.length > 0 && (
        <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Aspects mentioned">
          {r.aspects.map((a) => <li key={a.aspect} title={a.evidence ? `“${a.evidence}”` : undefined} className="rounded-full border px-2 py-0.5 text-xs" style={{ borderColor: SENTIMENT_COLOR[a.label], color: SENTIMENT_COLOR[a.label] }}>{a.aspect.replace("_", " ")}: {a.label}</li>)}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted">Source: {r.source_label}</p>
    </li>
  );
}

function Reviews({ id }: { id: number }) {
  const [filter, setFilter] = useState<"" | SentimentLabel>("");
  const [sort, setSort] = useState("most_positive");
  const [aspect, setAspect] = useState("");
  const [offset, setOffset] = useState(0);
  const rv = useFetch((s) => api.reviews(id, { sentiment: filter || undefined, aspect: aspect || undefined, sort, limit: PAGE, offset }, s), [id, filter, aspect, sort, offset]);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Filter by sentiment" className="flex gap-1.5">
          {([["", "All"], ["positive", "Positive"], ["neutral", "Neutral"], ["negative", "Negative"]] as const).map(([v, l]) => (
            <button key={v} className="chip" aria-pressed={filter === v} onClick={() => { setFilter(v); setOffset(0); }}>{l}</button>
          ))}
        </div>
        <select className="field w-auto" aria-label="Filter by aspect" value={aspect} onChange={(e) => { setAspect(e.target.value); setOffset(0); }}>
          <option value="">Any aspect</option>{ASPECTS.map((a) => <option key={a.v} value={a.v}>Mentions {a.l.toLowerCase()}</option>)}
        </select>
        <select className="field ml-auto w-auto" aria-label="Sort reviews" value={sort} onChange={(e) => { setSort(e.target.value); setOffset(0); }}>
          <option value="most_confident">Most confident prediction</option><option value="most_positive">Most positive text</option><option value="most_negative">Most negative text</option>
          <option value="rating_desc">Highest star rating</option><option value="rating_asc">Lowest star rating</option>
        </select>
      </div>
      {rv.loading && !rv.data ? <Loading /> : rv.error ? <ErrorBox error={rv.error} onRetry={rv.reload} /> :
        rv.data && rv.data.items.length === 0 ? <EmptyNote title="No reviews to show">{filter || aspect ? "No reviews match these filters." : "No verified reviews are attributed to this restaurant. Reviews appear only when the restaurant match is verified by name, area and address."}</EmptyNote> : (
          <>
            <ol className="space-y-3">
              {rv.data?.items.map((r) => <ReviewCard key={r.id} r={r} />)}
            </ol>
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-muted">{offset + 1}–{Math.min(offset + PAGE, rv.data?.total ?? 0)} of {fmtInt(rv.data?.total)}</span>
              <div className="flex gap-2">
                <button className="btn btn-ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <button className="btn btn-ghost" disabled={!rv.data || offset + PAGE >= rv.data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
            </div>
          </>
        )}
    </div>
  );
}

function LiveReviews({ id }: { id: number }) {
  const [go, setGo] = useState(false);
  const live = useFetch((s) => api.liveReviews(id, s), [id], go);
  return (
    <div>
      {!go && <button className="btn btn-ghost" onClick={() => setGo(true)}>Load current Google reviews</button>}
      {go && live.loading && <Loading />}
      {live.error && <ErrorBox error={live.error} onRetry={live.reload} />}
      {live.data && !live.data.configured && <p className="text-sm text-muted">{live.data.message}</p>}
      {live.data?.configured && live.data.reviews.length === 0 && <p className="text-sm text-muted">{live.data.message ?? "Google returned no reviews for this place."}</p>}
      {live.data && live.data.reviews.length > 0 && (
        <>
          <ul className="space-y-3">{live.data.reviews.map((r, i) => (
            <li key={i} className="rounded-xl border border-line p-4 text-sm">
              <p className="mb-1 text-xs text-muted">{r.rating != null && <>★ {r.rating} · </>}{r.relative_time}{r.author && <> · {r.author_url ? <a className="underline" href={r.author_url} target="_blank" rel="noreferrer">{r.author}</a> : r.author}</>}</p>
              <p>{r.text}</p>
            </li>))}
          </ul>
          <p className="mt-2 text-xs text-muted">{live.data.attribution} Google returns at most five reviews per place.</p>
        </>
      )}
    </div>
  );
}

export default function RestaurantPage() {
  const id = Number(useParams().id);
  const cmp = useCompare();
  const r = useFetch((s) => api.restaurant(id, s), [id], Number.isInteger(id));
  const sent = useFetch((s) => api.sentiment(id, s), [id], Number.isInteger(id));
  const asp = useFetch((s) => api.aspects(id, s), [id], Number.isInteger(id));
  const meta = useFetch((s) => api.meta(s), []);

  if (!Number.isInteger(id)) return <div className="mx-auto max-w-3xl p-6"><EmptyNote title="Invalid restaurant link" /></div>;
  if (r.loading && !r.data) return <Loading label="Loading restaurant…" />;
  if (r.error) return (
    <div className="mx-auto max-w-3xl space-y-3 p-6">
      {r.error.status === 404 ? <EmptyNote title="Restaurant not found">It may have been removed. <Link className="font-semibold text-leaf underline" to="/">Back to the overview</Link></EmptyNote> : <ErrorBox error={r.error} onRetry={r.reload} />}
    </div>
  );
  const d = r.data!;
  const inCmp = cmp.has(d.id);
  const sd = sent.data;
  const comps = Object.entries(d.ranking_components ?? {});
  const eng = sd?.engine;
  const stat = (label: string, value: React.ReactNode, sub?: string) => (
    <div className="rounded-xl bg-paper px-4 py-3"><dt className="text-xs text-muted">{label}</dt><dd className="font-display text-2xl font-bold leading-tight">{value}</dd>{sub && <p className="text-[11.5px] text-muted">{sub}</p>}</div>
  );
  return (
    <div className="mx-auto max-w-[1180px] px-4 py-6 sm:px-6 lg:px-7">
      <nav aria-label="Breadcrumb" className="mb-3 text-sm"><Link className="inline-flex items-center gap-1 font-medium text-leaf hover:underline" to="/explore"><ArrowLeft className="h-3.5 w-3.5" aria-hidden />Explore map</Link></nav>
      <header className="panel mb-5 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold sm:text-[2.4rem]">{d.name}</h1>
            <p className="mt-1.5 flex items-center gap-1.5 text-muted"><MapPin className="h-4 w-4 shrink-0" aria-hidden />{d.address ?? "Address not available in the source data"}</p>
            <p className="mt-1">{cuisineText(d.cuisines)} · {d.neighborhood_label ?? "Area unknown"}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2"><GemBadge r={d} /><RecheckBadge r={d} />
              {d.popularity_rank != null && <span className="rounded-full bg-leaf-soft px-2 py-0.5 text-xs font-semibold text-leaf-dark">Popularity rank #{d.popularity_rank}</span>}</div>
            {d.needs_recheck && d.recheck_reason && <p className="mt-2 text-sm text-chili-dark">{d.recheck_reason}. Check before visiting.</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            {d.directions_url && <a className="btn btn-accent" href={d.directions_url} target="_blank" rel="noreferrer"><Navigation className="h-4 w-4" aria-hidden />Get directions</a>}
            <button className="btn btn-ghost" onClick={() => cmp.toggle(d.id)} disabled={!inCmp && cmp.full} aria-pressed={inCmp}>{inCmp ? <Check className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}{inCmp ? "Added to comparison" : "Add to comparison"}</button>
            {cmp.ids.length >= 2 && <Link className="btn btn-ghost" to="/compare">Open comparison</Link>}
            {d.source_url && <a className="btn btn-ghost" href={d.source_url} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" aria-hidden />OpenStreetMap</a>}
          </div>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stat("Dataset rating", d.rating != null ? <>★ {d.rating.toFixed(1)}</> : "Not available", d.rating != null ? sourceLabel(d.rating_source) : undefined)}
          {stat("Ratings counted", fmtInt(d.rating_count))}
          {stat("Reviews analysed", fmtInt(d.review_count), d.review_count ? "matched by name, area and address" : "no verified reviews attributed")}
          {stat("Positive reviews", d.review_count ? pct(d.positive_share) : "–", eng ? (eng.active === "bert" ? "by BERT" : "by VADER baseline") : undefined)}
        </dl>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <Section id="sentiment" title="What the reviews say" hint="Computed from the text of each review, so it can differ from the star rating.">
            {sent.loading && !sd ? <Loading /> : sent.error ? <ErrorBox error={sent.error} onRetry={sent.reload} /> : !sd?.available || !sd.distribution ? (
              <EmptyNote title="No reviews analysed">{sd?.message ?? "Verified reviews are needed for sentiment analysis."}</EmptyNote>
            ) : (
              <>
                <ShareBar positive={sd.distribution.positive} neutral={sd.distribution.neutral} negative={sd.distribution.negative} height="h-4" />
                <SentimentBar counts={sd.distribution} />
                {eng && <div className="mt-4"><EnginePanel e={eng} comparison={sd.comparison && sd.comparison.agreement != null ? { other_engine: sd.comparison.other_engine, reviews_with_both: sd.comparison.reviews_with_both, agreement: sd.comparison.agreement, matrix: {} } : null} /></div>}
                {sd.mean_confidence != null && <p className="mt-2 text-sm text-muted">Mean BERT confidence across these reviews: <strong className="text-ink">{pct(sd.mean_confidence)}</strong>. Confidence is the model’s own probability, not a measured accuracy.</p>}
                <div className="mt-5 grid gap-4 sm:grid-cols-2">
                  <div>
                    <h3 className="mb-1 text-sm font-semibold">Spread of sentiment scores</h3>
                    <div role="img" aria-label={`Histogram: ${sd.histogram?.map((h) => `${h.range} ${h.count}`).join(", ")}`}>
                      <ResponsiveContainer width="100%" height={170}>
                        <BarChart data={sd.histogram} margin={{ left: -18, right: 4 }}>
                          <CartesianGrid vertical={false} stroke="#EADFC9" /><XAxis dataKey="range" tick={{ fontSize: 10 }} interval={0} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                          <Tooltip cursor={{ fill: "rgba(0,0,0,.04)" }} /><Bar dataKey="count" name="Reviews">{sd.histogram?.map((_, i) => <Cell key={i} fill={HIST_COLORS[i]} />)}</Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  <div className="text-sm">
                    <h3 className="mb-1 font-semibold">Common themes</h3>
                    {sd.themes && sd.themes.positive.length + sd.themes.negative.length > 0 ? (
                      <div className="space-y-2">
                        <div><p className="text-xs text-muted">In positive reviews</p><div className="mt-1 flex flex-wrap gap-1.5">{sd.themes.positive.map((t) => <span key={t.term} className="rounded-full bg-[#E3F1E8] px-2 py-0.5 text-xs text-[#1D5B38]">{t.term} <span className="opacity-60">×{t.count}</span></span>)}</div></div>
                        <div><p className="text-xs text-muted">In negative reviews</p><div className="mt-1 flex flex-wrap gap-1.5">{sd.themes.negative.length ? sd.themes.negative.map((t) => <span key={t.term} className="rounded-full bg-[#F8E3E0] px-2 py-0.5 text-xs text-[#8C2A20]">{t.term} <span className="opacity-60">×{t.count}</span></span>) : <span className="text-xs text-muted">Not enough negative reviews to find themes.</span>}</div></div>
                        <p className="text-xs text-muted">Terms that appear in at least two reviews and stand out for that sentiment.</p>
                      </div>
                    ) : <p className="text-muted">Not enough reviews to find repeated themes.</p>}
                  </div>
                </div>
                {sd.star_rating != null && sd.share && <p className="mt-3 text-xs text-muted">Dataset star rating {sd.star_rating.toFixed(1)}/5 vs {pct(sd.share.positive)} of review texts positive.</p>}
              </>
            )}
          </Section>

          <Section id="aspects" title="Aspect findings" hint={`Food, service, ambience, value, hygiene and waiting time. An aspect is scored only when at least ${asp.data?.min_mentions_required ?? meta.data?.min_aspect_mentions ?? 5} reviews mention it. Rule-based, not BERT.`}>
            {asp.loading && !asp.data ? <Loading /> : asp.error ? <ErrorBox error={asp.error} onRetry={asp.reload} /> : asp.data && (
              <>
                {asp.data.summary.text ? <p className="mb-4 rounded-lg bg-leaf-soft/60 p-3 text-[0.95rem]">{asp.data.summary.text} <span className="text-xs text-muted">(from {asp.data.summary.basis_reviews} reviews)</span></p> : <p className="mb-4 text-sm text-muted">{asp.data.summary.reason}</p>}
                <AspectChart aspects={asp.data.aspects} minMentions={asp.data.min_mentions_required} />
              </>
            )}
          </Section>

          <Section id="reviews" title="Customer reviews" hint="Real review excerpts from the Zomato Bangalore dataset (Kaggle), a past snapshot that may not reflect the restaurant today. Each shows the model label that was used.">
            <Reviews id={d.id} />
          </Section>

          <Section id="ranking" title="Why it ranks where it does" hint="Every number comes from the ranking formula described on the methodology page.">
            {d.ranking_explanation.length ? (
              <>
                <ul className="list-disc space-y-1.5 pl-5 text-sm">{d.ranking_explanation.map((e, i) => <li key={i}>{e}</li>)}</ul>
                {comps.length > 0 && (
                  <div className="mt-4 space-y-2">{comps.map(([k, c]) => (
                    <div key={k} className="text-sm"><div className="flex justify-between"><span className="capitalize">{k}</span><span className="text-muted">{Math.round(c.value * 100)}% · weight {c.weight}</span></div>
                      <div className="mt-1 h-2 rounded-full bg-line"><div className="h-2 rounded-full bg-leaf" style={{ width: `${Math.round(c.value * 100)}%` }} /></div></div>))}</div>
                )}
                {d.gem_explanation && <p className="mt-4 flex items-start gap-2 text-sm"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-leaf" aria-hidden /><span><strong>Hidden-gem check:</strong> {d.gem_explanation}</span></p>}
                <p className="mt-3 text-xs text-muted">Confidence in this ranking: {d.confidence != null ? pct(d.confidence) : "not available"}.</p>
              </>
            ) : <p className="text-sm text-muted">No ranking explanation is available yet.</p>}
          </Section>

          {(meta.data?.features.google_live_reviews ?? false) && (
            <Section id="live" title="Current Google reviews" hint="Fetched live when you ask, limited to five by Google, and never stored or used in rankings.">
              <LiveReviews id={d.id} />
            </Section>
          )}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          <div className="panel overflow-hidden">
            {d.latitude != null && d.longitude != null
              ? <RestaurantMap className="h-72" restaurants={[d]} selectedId={d.id} center={[d.latitude, d.longitude]} zoom={16} />
              : <p className="p-4 text-sm text-muted">No verified location.</p>}
          </div>
          <div className="panel p-4 text-xs text-muted">
            <h2 className="mb-2 font-display text-base font-bold text-ink">Data provenance</h2>
            <dl className="space-y-1">
              <div className="flex gap-1"><dt>Location:</dt><dd>{d.source_attribution ?? sourceLabel(d.source)}</dd></div>
              <div className="flex gap-1"><dt>Last verified:</dt><dd>{fmtDate(d.last_verified_at)}</dd></div>
              <div className="flex gap-1"><dt>Rating:</dt><dd>{d.rating != null ? sourceLabel(d.rating_source) : "none"}</dd></div>
              <div className="flex gap-1"><dt>Price:</dt><dd>{d.price_info ?? "not available"}</dd></div>
              <div className="flex gap-1"><dt>Opening date:</dt><dd>{d.opening_date ?? "unknown (not verified)"}</dd></div>
            </dl>
            {d.rating_note && <p className="mt-2">{d.rating_note}</p>}
          </div>
          <InfoNote>Coordinates come from OpenStreetMap. Directions open in Google Maps.</InfoNote>
        </aside>
      </div>
    </div>
  );
}
