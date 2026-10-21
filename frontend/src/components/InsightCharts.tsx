import { Link } from "react-router-dom";
import { Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { CalendarOff, Check, ChevronRight, Info } from "lucide-react";
import type { AspectInsight, CuisineInsight, EngineInfo, HoodInsight, Insights } from "../types";
import { SENTIMENT_COLOR, SENTIMENT_TEXT, fmtInt, pct } from "../lib/format";
import { ShareBar } from "./ui";

const MIN_HOOD_REVIEWS = 10;

export function AspectBars({ aspects, minMentions }: { aspects: AspectInsight[]; minMentions: number }) {
  return (
    <div>
      <ul className="space-y-3.5">
        {aspects.map((a) => {
          const enough = a.mentions >= minMentions;
          return (
            <li key={a.aspect} className="grid grid-cols-[92px_1fr_auto] items-center gap-x-3 gap-y-0.5 sm:grid-cols-[130px_1fr_auto]">
              <span className="text-sm font-medium">{a.label}</span>
              {enough ? <ShareBar positive={a.positive} neutral={a.neutral} negative={a.negative} height="h-3.5" /> : <div className="h-3.5 rounded-full border border-dashed border-line" aria-hidden />}
              <span className="w-12 text-right font-display text-lg font-bold" style={{ color: enough ? SENTIMENT_COLOR.positive : "#9C9186" }}>{enough ? pct(a.positive_share) : "–"}</span>
              <span className="col-start-2 col-end-4 text-xs text-muted">
                {a.mentions === 0 ? "No mentions in this scope" : enough
                  ? `${fmtInt(a.mentions)} mentions · in ${pct(a.review_coverage)} of reviews · ${fmtInt(a.negative)} negative`
                  : `Only ${a.mentions} mention${a.mentions === 1 ? "" : "s"} (needs ${minMentions}) – not scored`}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 flex items-start gap-1.5 text-xs text-muted"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /><span>Bar = positive / neutral / negative mentions; the figure is the positive share of mentions. Aspects come from a rule-based, clause-level analyser (not BERT).</span></p>
    </div>
  );
}

export function SentimentDonut({ s }: { s: Insights["sentiment"] }) {
  const data = (["positive", "neutral", "negative"] as const).map((k) => ({ name: SENTIMENT_TEXT[k], key: k, value: s[k] }));
  return (
    <div className="flex flex-wrap items-center gap-5">
      <div className="relative h-[168px] w-[168px] shrink-0" role="img" aria-label={`Sentiment of ${s.n} reviews: ${data.map((d) => `${d.value} ${d.name.toLowerCase()}`).join(", ")}`}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" innerRadius={52} outerRadius={80} paddingAngle={2} stroke="none" isAnimationActive={false}>
              {data.map((d) => <Cell key={d.key} fill={SENTIMENT_COLOR[d.key]} />)}
            </Pie>
            <Tooltip formatter={(v: number, n: string) => [`${fmtInt(v)} reviews`, n]} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-display text-2xl font-bold">{pct(s.positive_share)}</span><span className="text-[11px] text-muted">positive</span>
        </div>
      </div>
      <ul className="min-w-[150px] flex-1 space-y-2 text-sm">
        {data.map((d) => (
          <li key={d.key} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: SENTIMENT_COLOR[d.key] }} aria-hidden />
            <span>{d.name}</span><span className="ml-auto font-semibold">{fmtInt(d.value)}</span>
            <span className="w-10 text-right text-muted">{pct(s[`${d.key}_share` as "positive_share"])}</span>
          </li>
        ))}
        <li className="border-t border-line pt-2 text-xs text-muted">{fmtInt(s.n)} analysed reviews</li>
      </ul>
    </div>
  );
}

export function EnginePanel({ e, comparison }: { e: EngineInfo; comparison: Insights["engine_comparison"] }) {
  const bert = e.active === "bert";
  return (
    <div className={`rounded-xl border px-3.5 py-3 text-sm ${bert ? "border-leaf/30 bg-leaf-soft/50" : "border-saffron/50 bg-saffron-soft/50"}`}>
      <p className="flex flex-wrap items-center gap-2 font-semibold">
        <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${bert ? "bg-leaf text-paper" : "bg-saffron text-ink"}`}>{bert ? "BERT" : "VADER baseline"}</span>
        <span className="font-normal text-ink/80">{e.active_label}</span>
      </p>
      <p className="mt-1.5 text-[13px] leading-snug text-muted">{e.reason}</p>
      {comparison && comparison.agreement != null && (
        <p className="mt-1.5 text-[13px]">Both engines scored {fmtInt(comparison.reviews_with_both)} reviews and agree on the label for <strong>{pct(comparison.agreement)}</strong>. Agreement between two models is not accuracy.</p>
      )}
      <Link to="/methodology#sentiment-engines" className="mt-1.5 inline-flex items-center gap-0.5 text-[13px] font-semibold text-leaf hover:underline">Model details &amp; limitations<ChevronRight className="h-3.5 w-3.5" aria-hidden /></Link>
    </div>
  );
}

function hoodNote(h: HoodInsight) { return h.reviews < MIN_HOOD_REVIEWS; }

export function NeighbourhoodBars({ items, onSelect }: { items: HoodInsight[]; onSelect?: (key: string | null) => void }) {
  const rows = [...items].sort((a, b) => b.reviews - a.reviews);
  return (
    <div>
      <ul className="space-y-2.5">
        {rows.map((h) => (
          <li key={h.neighborhood}>
            <button type="button" onClick={() => onSelect?.(h.selected ? null : h.neighborhood)} aria-pressed={h.selected}
              className={`grid w-full grid-cols-[110px_1fr_auto] items-center gap-x-3 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-leaf-soft/50 sm:grid-cols-[140px_1fr_auto] ${h.selected ? "bg-leaf-soft ring-1 ring-leaf/40" : ""}`}>
              <span className="truncate text-sm font-medium">{h.label}</span>
              {h.reviews > 0 ? <span className={hoodNote(h) ? "opacity-50" : ""}><ShareBar positive={h.positive} neutral={h.neutral} negative={h.negative} /></span> : <span className="h-3 rounded-full border border-dashed border-line" />}
              <span className="w-16 text-right text-sm font-semibold">{hoodNote(h) ? "–" : pct(h.positive_share)}</span>
              <span className="col-span-3 -mt-0.5 pl-0.5 text-[11.5px] text-muted sm:col-start-2 sm:col-span-2">
                {fmtInt(h.restaurants_with_reviews)} of {fmtInt(h.restaurants)} restaurants have reviews · {fmtInt(h.reviews)} reviews{hoodNote(h) && h.reviews > 0 ? ` – under ${MIN_HOOD_REVIEWS}, so no share shown` : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">Positive share of analysed reviews per area. Click an area to filter the whole page. This chart ignores the area filter so areas stay comparable.</p>
    </div>
  );
}

export function CuisineBars({ items }: { items: CuisineInsight[] }) {
  if (!items.length) return <p className="rounded-lg bg-paper px-3 py-4 text-sm text-muted">No cuisine has 3 or more restaurants with reviews in this scope yet.</p>;
  return (
    <ul className="space-y-2.5">
      {[...items].sort((a, b) => b.reviews - a.reviews).slice(0, 10).map((c) => (
        <li key={c.value} className="grid grid-cols-[110px_1fr_auto] items-center gap-x-3 sm:grid-cols-[140px_1fr_auto]">
          <span className="truncate text-sm font-medium">{c.cuisine}</span>
          <span className="relative block h-3 overflow-hidden rounded-full bg-[#EFE8D8]"><span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.round((c.positive_share ?? 0) * 100)}%`, background: SENTIMENT_COLOR.positive }} /></span>
          <span className="w-12 text-right text-sm font-semibold">{pct(c.positive_share)}</span>
          <span className="col-start-2 col-end-4 text-[11.5px] text-muted">{c.restaurants_with_reviews} restaurants · {fmtInt(c.reviews)} reviews</span>
        </li>
      ))}
    </ul>
  );
}

export function TimeTrend({ t }: { t: Insights["time_trend"] }) {
  if (!t.available || !t.series) {
    return (
      <div className="flex items-start gap-3 rounded-xl bg-paper px-4 py-4 text-sm text-muted">
        <CalendarOff className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
        <p><strong className="text-ink">No time trend is shown.</strong> {t.reason ?? "There are not enough dated reviews."} FoodSpotter does not guess dates, so sentiment is compared across areas, cuisines and aspects instead.</p>
      </div>
    );
  }
  const data = t.series.map((m) => ({ month: m.month, share: Math.round(m.positive_share * 100), reviews: m.reviews }));
  return (
    <div role="img" aria-label={`Share of positive reviews by month, ${data.length} months`}>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ left: -10, right: 12, top: 8, bottom: 0 }}>
          <CartesianGrid stroke="#EADFC9" vertical={false} />
          <XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: number, _n, p) => [`${v}% positive (${p.payload.reviews} reviews)`, "Sentiment"]} />
          <Line type="monotone" dataKey="share" stroke="#1E4D3B" strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PipelineStrip({ p }: { p: Insights["pipeline"] }) {
  const steps = [
    { n: fmtInt(p.restaurants_discovered), l: "restaurants discovered (OpenStreetMap)" },
    { n: fmtInt(p.reviews_stored), l: "real reviews stored (Zomato/Kaggle snapshot)" },
    { n: fmtInt(p.reviews_matched), l: `matched to a restaurant · ${fmtInt(p.reviews_unresolved_stored)} unresolved` },
    { n: fmtInt(p.reviews_analysed), l: `analysed – ${p.engine.active === "bert" ? "BERT" : "VADER baseline"}` },
    { n: fmtInt(p.restaurants_with_matched_reviews), l: "restaurants with review evidence" },
  ];
  return (
    <ol className="grid gap-2 sm:grid-cols-5">
      {steps.map((s, i) => (
        <li key={i} className="relative rounded-xl bg-paper px-3 py-2.5">
          <span className="flex items-center gap-1 font-display text-xl font-bold text-leaf-dark"><Check className="h-4 w-4 text-pos" aria-hidden />{s.n}</span>
          <span className="text-xs leading-snug text-muted">{s.l}</span>
        </li>
      ))}
    </ol>
  );
}
