import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { fmtDate, fmtInt, pct } from "../lib/format";
import type { PipelineSummary } from "../types";
import { ErrorBox, Loading } from "../components/StateViews";

const P = ({ children }: { children: React.ReactNode }) => <p className="mt-2 leading-relaxed">{children}</p>;
const Sec = ({ id, title, children }: { id: string; title: string; children: React.ReactNode }) => (
  <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-24 border-t border-line py-7 first:border-0"><h2 id={`${id}-h`} className="text-2xl font-bold">{title}</h2>{children}</section>
);
const code = "rounded bg-white px-1.5 py-0.5 text-[0.85em]";
const num = (x: unknown, d = 3) => (typeof x === "number" ? x.toFixed(d) : "n/a");

type Dict = Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any

function MetricTable({ rows }: { rows: [string, Dict | undefined][] }) {
  const ok = rows.filter(([, m]) => m);
  if (!ok.length) return null;
  return (
    <table className="mt-2 w-full max-w-xl text-sm"><thead className="text-left text-muted"><tr><th className="py-1 pr-4 font-medium">Model</th><th className="py-1 pr-4 font-medium">Accuracy</th><th className="py-1 pr-4 font-medium">Macro F1</th><th className="py-1 font-medium">Reviews</th></tr></thead>
      <tbody>{ok.map(([title, m]) => <tr key={title} className="border-b border-line"><th scope="row" className="py-2 pr-4 text-left font-medium">{title}</th><td className="py-2 pr-4">{num(m!.accuracy)}</td><td className="py-2 pr-4">{num(m!.macro_f1)}</td><td className="py-2">{m!.n}</td></tr>)}</tbody></table>
  );
}

function SentimentResult({ r, title }: { r: Dict; title: string }) {
  const bv: Dict | undefined = r.bert_vs_vader;
  return (
    <div>
      <h3 className="font-bold">{title}</h3>
      {r.status?.startsWith("not evaluated") ? <P>Not evaluated. {r.reason}</P> : (
        <>
          <p className="mt-1 text-sm text-muted">{r.status}. {r.definition}</p>
          <MetricTable rows={[["VADER (baseline)", r.vader_baseline], ["VADER + domain terms", r.vader_plus_domain_lexicon]]} />
          {bv?.status === "evaluated" ? (
            <>
              <p className="mt-3 text-sm font-medium">BERT vs VADER baseline on the same {fmtInt(bv.n)} reviews</p>
              <MetricTable rows={[["BERT (nlptown)", bv.bert], ["VADER (baseline)", bv.vader_baseline_same_reviews]]} />
              <p className="mt-1 text-sm text-muted">{bv.caveat}</p>
            </>
          ) : <p className="mt-3 text-sm text-muted">BERT not evaluated: {bv?.reason ?? "no stored BERT predictions"}.</p>}
        </>
      )}
    </div>
  );
}

function Results() {
  const ev = useFetch((s) => api.evaluation(s), []);
  if (ev.loading) return <Loading />;
  if (ev.error) return <ErrorBox error={ev.error} onRetry={ev.reload} />;
  const r = ev.data as Dict;
  if (!r?.available) return <P>No evaluation has been run yet, so there are no results to report. After importing data, run <code className={code}>python scripts/evaluate_models.py run</code> and reload this page. {r?.message}</P>;
  const asp: Dict = r.aspects_manual ?? {}, rk: Dict = r.ranking_vs_rating_baseline ?? {}, mt: Dict = r.restaurant_matching ?? {};
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">Generated {fmtDate(r.generated_at)} from {fmtInt(r.dataset?.verified_reviews)} verified reviews and {fmtInt(r.dataset?.restaurants)} restaurants. {r.dataset?.note} Anything not evaluated says so and why; nothing is estimated.</p>
      <SentimentResult r={r.sentiment_proxy ?? {}} title="Sentiment: agreement with star ratings (proxy, not ground truth)" />
      <SentimentResult r={r.sentiment_manual ?? {}} title="Sentiment: hand-labelled sample" />
      <div><h3 className="font-bold">Aspect extraction and aspect sentiment</h3>
        {asp.status?.startsWith("evaluated") ? <P>On {asp.n_reviews} annotated reviews: extraction precision {num(asp.extraction?.precision)}, recall {num(asp.extraction?.recall)}; aspect-sentiment accuracy {num(asp.aspect_sentiment_accuracy?.accuracy)} (over {asp.aspect_sentiment_accuracy?.n} aspects found by both).</P> : <P>Not evaluated. {asp.reason}</P>}</div>
      <div><h3 className="font-bold">Ranking compared with a rating-only baseline</h3>
        {rk.status?.startsWith("evaluated") ? <P>On {rk.n} judged restaurants – Spearman with judgments: FoodSpotter {num(rk.spearman_vs_judgment?.foodspotter_score, 2)} vs rating-only {num(rk.spearman_vs_judgment?.rating_only_baseline, 2)}; NDCG@10: {num(rk.ndcg_at_10?.foodspotter_score, 2)} vs {num(rk.ndcg_at_10?.rating_only_baseline, 2)}. {rk.uncertainty_note}</P> : <P>Not evaluated. {rk.reason}</P>}</div>
      <div><h3 className="font-bold">Restaurant matching</h3>
        <P>Review match status counts: {Object.entries(mt.review_counts_by_match_status ?? {}).map(([k, v]) => `${k.replace("_", " ")} ${v}`).join(", ") || "none"}. {mt.note}</P>
        {mt.status?.startsWith("evaluated") ? <P>Manual check of {mt.verified_sample} matches: {mt.incorrect_matches} incorrect (precision {num(mt.precision, 2)}, 95% lower bound {num(mt.precision_95ci_lower_wilson, 2)}).</P> : <P>Not manually verified yet. {mt.reason}</P>}</div>
    </div>
  );
}

function Pipeline() {
  const p = useFetch((s) => api.pipeline(s), []);
  if (p.loading && !p.data) return <Loading />;
  if (p.error) return <ErrorBox error={p.error} onRetry={p.reload} />;
  const d = p.data as PipelineSummary;
  const im = d.import;
  const matchedShare = d.reviews_stored ? d.reviews_matched / d.reviews_stored : null;
  const stages = [
    { t: "1. Real review source", n: im ? fmtInt(im.review_entries_parsed) : "–", l: im ? `review entries parsed from ${im.filename}` : "no review file imported yet" },
    { t: "2. Cleaning", n: im ? fmtInt(im.valid_reviews_imported) : "–", l: im ? `valid reviews kept · ${fmtInt(im.malformed_review_entries)} malformed · ${fmtInt(im.duplicate_reviews_skipped)} duplicates dropped` : "nothing imported" },
    { t: "3. Restaurant matching", n: fmtInt(d.reviews_matched), l: `reviews matched to an OSM restaurant${matchedShare != null ? ` (${pct(matchedShare)} of stored)` : ""}` },
    { t: "4. Sentiment model", n: fmtInt(d.reviews_analysed), l: `reviews scored · ${d.engine.active === "bert" ? "BERT" : "VADER baseline"}` },
    { t: "5. Aspect extraction", n: fmtInt(d.reviews_analysed), l: "reviews scanned by the rule-based aspect analyser" },
    { t: "6. Aggregation", n: fmtInt(d.restaurants_with_matched_reviews), l: `restaurants with review evidence of ${fmtInt(d.restaurants_total)}` },
    { t: "7. Map & ranking", n: fmtInt(d.restaurants_discovered), l: "restaurants discovered (OpenStreetMap) shown on the map" },
  ];
  return (
    <div>
      <ol className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        {stages.map((s) => (
          <li key={s.t} className="rounded-xl border border-line bg-white p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">{s.t}</p>
            <p className="font-display text-2xl font-bold text-leaf-dark">{s.n}</p>
            <p className="text-xs leading-snug text-muted">{s.l}</p>
          </li>
        ))}
      </ol>
      <h3 className="mt-6 font-bold">Import and matching report</h3>
      {im ? (
        <table className="mt-2 w-full max-w-2xl text-sm"><tbody>
          {([
            ["Listing rows read", im.rows_read], ["Duplicate listing rows removed", im.duplicate_listing_rows_removed], ["Listings in the focus areas", im.rows_in_focus_areas],
            ["Listings matched to an OSM restaurant", im.listings_matched], ["Listings held for review (uncertain match)", im.listings_needs_review], ["Listings ambiguous (several candidates)", im.listings_ambiguous],
            ["Listings with no OSM record", im.listings_without_osm_record], ["Reviews dropped because the listing has no OSM record", im.reviews_unmatched_no_osm_record],
            ["Reviews stored but unresolved (excluded from every chart)", d.reviews_unresolved_stored], ["Restaurants with verified reviews", im.restaurants_with_verified_reviews],
          ] as [string, number | null][]).map(([k, v]) => <tr key={k} className="border-b border-line"><th scope="row" className="py-1.5 pr-4 text-left font-normal text-muted">{k}</th><td className="py-1.5 text-right font-semibold">{v == null ? "not recorded" : fmtInt(v)}</td></tr>)}
        </tbody></table>
      ) : <P>No review file has been imported into this database, so there is no import report. Run <code className={code}>python scripts/import_reviews.py data/zomato.csv</code>.</P>}
      {im?.dataset_note && <p className="mt-2 text-sm text-muted">{im.dataset_note} Last import: {fmtDate(im.finished_at)}.</p>}
      <p className="mt-3 text-sm text-muted">Review dates available: {fmtInt(d.dated_reviews)} of {fmtInt(d.reviews_stored)}.{d.dated_reviews === 0 ? " Without dates there is no time trend and no “trending” label." : ""}</p>
    </div>
  );
}

function Engines() {
  const e = useFetch((s) => api.sentimentEngine(s), []);
  if (e.loading && !e.data) return <Loading />;
  if (e.error) return <ErrorBox error={e.error} onRetry={e.reload} />;
  const d = e.data!;
  const m = d.bert.model;
  return (
    <div className="space-y-5">
      <div className={`rounded-xl border px-4 py-3 text-sm ${d.active === "bert" ? "border-leaf/30 bg-leaf-soft/50" : "border-saffron/50 bg-saffron-soft/50"}`}>
        <p><strong>Active engine:</strong> {d.active === "bert" ? "BERT" : "VADER baseline"} – {d.active_label}</p>
        <p className="mt-1 text-muted">{d.reason}</p>
        <p className="mt-1 text-muted">Coverage in this database: BERT {fmtInt(d.coverage.bert)} / VADER {fmtInt(d.coverage.vader)} of {fmtInt(d.coverage.matched_reviews)} matched reviews. FoodSpotter never mixes engines inside one chart: BERT becomes active only when it covers ≥95% of matched reviews.</p>
        {!d.bert.run_in_this_database && <p className="mt-1">{d.bert.unavailable_reason ? `BERT cannot run on this machine yet: ${d.bert.unavailable_reason}` : "BERT has not been run on this database yet: run python scripts/run_bert.py."}</p>}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-line bg-white p-4 text-sm">
          <h3 className="font-bold">BERT model</h3>
          <dl className="mt-2 space-y-1">
            <div><dt className="inline text-muted">Model: </dt><dd className="inline"><a className="font-mono text-xs text-leaf underline" href={m.card_url} target="_blank" rel="noreferrer">{m.id}</a></dd></div>
            <div><dt className="inline text-muted">Architecture: </dt><dd className="inline">{m.architecture}</dd></div>
            <div><dt className="inline text-muted">Output: </dt><dd className="inline">{m.output}</dd></div>
            <div><dt className="inline text-muted">Languages: </dt><dd className="inline">{m.languages.join(", ")}</dd></div>
            <div><dt className="inline text-muted">Licence: </dt><dd className="inline">{m.licence}</dd></div>
            <div><dt className="inline text-muted">Revision pinned: </dt><dd className="inline">{d.bert.revision ?? "no (latest files are used; set BERT_MODEL_REVISION)"}</dd></div>
            <div><dt className="inline text-muted">Token limit: </dt><dd className="inline">{d.bert.max_tokens} (longer reviews are truncated and flagged)</dd></div>
            <div><dt className="inline text-muted">Mapping: </dt><dd className="inline">{m.mapping}</dd></div>
          </dl>
        </div>
        <div className="rounded-xl border border-line bg-white p-4 text-sm">
          <h3 className="font-bold">VADER baseline</h3>
          <p className="mt-2">{d.vader.label}. A lexicon-and-rules scorer (compound score; positive ≥ 0.05, negative ≤ −0.05). It is the comparison baseline and the fallback when BERT has not been run. Model tag stored with each result: <code className={code}>{d.vader.model}</code>.</p>
          <h3 className="mt-4 font-bold">Aspects</h3>
          <p className="mt-2">Aspect findings (food, service, ambience, value, hygiene, waiting time) are always produced by the rule-based clause analyser, not by BERT.</p>
        </div>
      </div>
      <div className="rounded-xl border border-line bg-white p-4 text-sm">
        <h3 className="font-bold">Limitations – read before quoting any number</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5">{m.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="mt-2 text-muted">{m.authors_reported_accuracy_note}</p>
        <p className="mt-2 text-muted">No accuracy is claimed for either engine on restaurant reviews. That needs a hand-labelled sample (see Results). Agreement between BERT and VADER is shown where both exist, and is not accuracy.</p>
      </div>
    </div>
  );
}

export default function MethodologyPage() {
  return (
    <div className="mx-auto grid max-w-[1180px] gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[190px_1fr] lg:px-7">
      <nav aria-label="On this page" className="hidden text-sm lg:block"><ul className="sticky top-6 space-y-1.5">
        {[["abstract", "Abstract"], ["pipeline", "Data pipeline & counts"], ["sentiment-engines", "BERT & VADER"], ["problem", "Problem statement"], ["gap", "Research gap"], ["objectives", "Objectives"], ["data", "Data sources"], ["architecture", "Architecture"], ["algorithms", "Algorithms"], ["evaluation", "Evaluation method"], ["results", "Results"], ["limits", "Limitations"], ["future", "Future scope"], ["run", "Running it"]].map(([id, l]) => <li key={id}><a className="text-muted hover:text-leaf hover:underline" href={`#${id}`}>{l}</a></li>)}
      </ul></nav>
      <article className="max-w-3xl">
        <h1 className="text-3xl font-bold sm:text-4xl">Methodology &amp; data insights</h1>
        <p className="mt-2 text-muted">FoodSpotter: An Intelligent Geospatial Restaurant Discovery and Recommendation System Using Sentiment Analysis and Popularity-Based Ranking</p>

        <Sec id="abstract" title="Abstract">
          <P>FoodSpotter is a web application for exploring Bengaluru restaurants on an interactive map. It combines restaurant locations from OpenStreetMap with a historical set of customer reviews, analyses the review text for sentiment and for opinions on food, service, ambience, affordability, hygiene and waiting time, and ranks restaurants with a transparent score that accounts for how much evidence supports each rating. It also surfaces lesser-known, well-reviewed restaurants and tracks newly encountered establishments without claiming they have newly opened.</P>
        </Sec>
        <Sec id="pipeline" title="Data pipeline and real counts">
          <P>Every figure here is read from this database right now. Real review text goes in at one end; the map, charts and rankings come out of the other.</P>
          <Pipeline />
        </Sec>
        <Sec id="sentiment-engines" title="Sentiment engines: BERT and the VADER baseline">
          <Engines />
        </Sec>
        <Sec id="problem" title="Problem statement">
          <P>Choosing where to eat from a map or a star rating hides two things: <em>why</em> a place is rated as it is, and <em>how much evidence</em> is behind the number. A restaurant with three five-star ratings looks better than one with three thousand ratings averaging 4.4. Reading reviews fixes this but doesn't scale.</P>
        </Sec>
        <Sec id="gap" title="Research gap">
          <P>Existing restaurant discovery systems commonly provide geographical search, aggregate ratings, and customer reviews. However, there remains an opportunity to investigate the combined use of aspect-based sentiment analysis, confidence-aware restaurant ranking, hidden-gem discovery, and geospatial visualization within a unified restaurant intelligence platform.</P>
          <P>The project's contribution is the integration and evaluation of these features. It makes no claim that similar functionality hasn't been built before.</P>
        </Sec>
        <Sec id="objectives" title="Objectives and research questions">
          <ol className="mt-2 list-decimal space-y-1.5 pl-5">
            <li>Can review sentiment improve restaurant ranking compared with average ratings alone?</li>
            <li>Can aspect-based sentiment reveal restaurant strengths and weaknesses more effectively than aggregate ratings?</li>
            <li>Can confidence-adjusted ranking help identify underrated restaurants?</li>
            <li>How can a restaurant discovery platform incorporate newly discovered establishments without misleading users about their popularity?</li>
          </ol>
        </Sec>
        <Sec id="data" title="Data sources">
          <ul className="mt-2 list-disc space-y-2 pl-5">
            <li><strong>OpenStreetMap (Overpass API)</strong>: restaurant names, addresses, cuisine tags and coordinates, queried one neighbourhood box at a time, cached and rate-limited. © OpenStreetMap contributors, ODbL. The nine neighbourhood boxes are approximate search windows, not official boundaries.</li>
            <li><strong>Zomato Bangalore Restaurants (Kaggle)</strong>: a historical scrape providing ratings, vote counts, price for two, cuisines and the text of customer reviews. It has no coordinates and no review dates, and it is a snapshot from the past, so it is never presented as current. Review dates are left empty rather than invented.</li>
            <li><strong>Google Places API (New), optional</strong>: used only when a key is configured. Only Place IDs are stored. Live ratings and up to five reviews are fetched on request and shown with attribution; they are not stored and don't feed the rankings.</li>
          </ul>
          <P>A review is attached to a restaurant only when the name matches closely, the neighbourhood agrees, and the address text corroborates it. Names that differ in a number ("Outlet 1" and "Outlet 2") never match. Weaker matches are held back as <em>needs review</em> or <em>ambiguous</em> and excluded from every score and chart.</P>
        </Sec>
        <Sec id="architecture" title="Architecture">
          <P>A React and TypeScript single-page app (Tailwind, React Router, Leaflet, Recharts) talks to a FastAPI backend over a REST API documented at <a className="font-semibold text-leaf underline" href="/docs">/docs</a>. The backend uses SQLAlchemy with SQLite (schema kept portable to PostgreSQL), pandas for import, VADER (baseline), an optional BERT classifier (transformers + PyTorch) and a rule-based aspect module for NLP, and scikit-learn utilities. Administrative endpoints need a secret token; API keys stay on the server.</P>
          <pre className="mt-3 overflow-x-auto rounded-xl border border-line bg-white p-4 text-xs leading-relaxed" aria-label="Data flow diagram">{`Overpass / OSM ──► discovery ──► restaurants + locations ─┐
Kaggle CSV ──► importer ──► match (name+area+address) ───┤
                                  │ verified only         ▼
                                  └──► NLP: BERT / VADER + aspects ──► ranking ──► API ──► React UI
Google Places (optional) ──► Place IDs, live reviews (not stored)`}</pre>
        </Sec>
        <Sec id="algorithms" title="Algorithms">
          <h3 className="mt-3 font-bold">Text preparation</h3>
          <P>Reviews are cleaned (dataset prefix, URLs and stray whitespace removed), tokenised, stop-words removed while keeping negations such as "not" and "never", then lemmatised. The original text is kept for display.</P>
          <h3 className="mt-4 font-bold">Sentiment</h3>
          <P>Two engines are implemented. <strong>BERT</strong> (<code className={code}>nlptown/bert-base-multilingual-uncased-sentiment</code>) predicts 1–5 star probabilities per review; FoodSpotter maps 1–2★ to negative, 3★ to neutral and 4–5★ to positive and reports the winning class’s probability as its confidence. <strong>VADER</strong> stays as a labelled baseline.</P>
          <P>VADER gives a compound score in [−1, 1]. Positive at ≥ 0.05, negative at ≤ −0.05, otherwise neutral. A small, documented list of restaurant terms VADER doesn't know (for example "bland" or "overpriced") extends its lexicon, and the evaluation compares the baseline with the extended version.</P>
          <h3 className="mt-4 font-bold">Aspects</h3>
          <P>Each review is split into clauses (at punctuation and words like "but"). A clause mentions an aspect if it contains one of that aspect's keywords. Its polarity comes from aspect-specific cue words, checked for nearby negation, falling back to the clause's VADER score. For "The pizza was delicious, but the service was slow and the prices were high." the result is food positive, service negative, affordability negative. An aspect is shown for a restaurant only with enough mentions, and summaries are built only from those aggregates.</P>
          <h3 className="mt-4 font-bold">Popularity score</h3>
          <P>A weighted mean (0–100) of components that have data, with weights re-normalised over the available ones:</P>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li><code className={code}>rating</code>: Bayesian average (votes·rating + m·mean) / (votes + m), with m = 50, scaled to 0–1.</li>
            <li><code className={code}>volume</code>: log(1 + votes) relative to the most-rated restaurant.</li>
            <li><code className={code}>sentiment</code>: share of positive reviews, shrunk toward the overall share with strength 5.</li>
            <li><code className={code}>recency</code>: used only if reviews carry dates. The current data has none, so it is skipped and nothing is called "trending".</li>
          </ul>
          <P>Default weights are 0.35, 0.25, 0.30 and 0.10, and can be changed in the server's environment. Each restaurant page lists the numbers behind its score.</P>
          <h3 className="mt-4 font-bold">Hidden gems</h3>
          <P>A restaurant qualifies with at least 8 analysed reviews, a Wilson lower bound on its positive share of at least 0.55, an adjusted rating of at least 3.8, and a visibility (rating count) percentile no higher than the 50th. Its gem score is 0.60 × the lower bound + 0.25 × the adjusted rating + 0.15 × (1 − visibility percentile). Restaurants below the evidence threshold are reported as such rather than scored.</P>
          <h3 className="mt-4 font-bold">Newly discovered</h3>
          <P>The first successful scan of the area is a baseline. Places first seen in later scans are listed with their first-discovery time. A place missing from a later scan is flagged for recheck, never deleted. Opening dates aren't known, so the word "opened" is never used.</P>
          <h3 className="mt-4 font-bold">Heatmaps</h3>
          <P>Three separate measures, each with its own colours and description: restaurant density (where places are), review activity (where analysed reviews are), and popularity score. Density does not show popularity.</P>
        </Sec>
        <Sec id="evaluation" title="Evaluation method">
          <ul className="mt-2 list-disc space-y-1.5 pl-5">
            <li><strong>Sentiment:</strong> accuracy, precision, recall, F1 and a confusion matrix. Star ratings give only a proxy label, so a hand-labelled sample is the real test.</li>
            <li><strong>Aspects:</strong> extraction precision and recall, and sentiment accuracy on correctly extracted aspects, against a hand-annotated sample.</li>
            <li><strong>Ranking:</strong> coverage, rank correlation and the largest disagreements with a rating-only ranking, plus precision@k against relevance judgments when they exist.</li>
            <li><strong>Matching:</strong> a random sample of matches checked by hand, with incorrect matches and unmatched counts reported.</li>
          </ul>
          <P><code className={code}>python scripts/evaluate_models.py --export-templates</code> writes the samples to annotate.</P>
        </Sec>
        <Sec id="results" title="Results"><Results /></Sec>
        <Sec id="limits" title="Limitations">
          <ul className="mt-2 list-disc space-y-1.5 pl-5">
            <li>Reviews and ratings are a historical snapshot with no dates. They can't show current quality or real trends.</li>
            <li>Only restaurants found in both OpenStreetMap and the Zomato file, with a corroborating address, carry reviews. Coverage is partial, and OpenStreetMap itself is incomplete.</li>
            <li>The aspect method is rule-based: it misses dishes and phrasings outside its word lists, and sarcasm.</li>
            <li>VADER is a general-purpose lexicon model, not trained on restaurant reviews. The BERT model was fine-tuned on product reviews, so its accuracy on restaurant text is unmeasured until a labelled sample is evaluated.</li>
            <li>Google reviews are capped at five per place, can't be stored, and aren't used for ranking.</li>
            <li>The neighbourhood boxes are approximate, so edge cases may be assigned to a neighbouring area.</li>
          </ul>
        </Sec>
        <Sec id="future" title="Future scope">
          <ul className="mt-2 list-disc space-y-1.5 pl-5">
            <li>Measure BERT against VADER on a hand-labelled restaurant sample, and try a transformer for aspect extraction.</li>
            <li>Collect dated reviews from an authorised source to support genuine trend analysis.</li>
            <li>Personalised recommendations from user preferences and a user study on ranking quality.</li>
            <li>Move to PostgreSQL with PostGIS for larger areas and the rest of the city.</li>
          </ul>
        </Sec>
        <Sec id="run" title="Running and demonstrating the project">
          <P>The README lists the exact commands: set up the backend and frontend, run <code className={code}>scripts/discover_restaurants.py</code>, download the Kaggle CSV into <code className={code}>data/</code>, run <code className={code}>scripts/import_reviews.py</code>, then start both servers.</P>
        </Sec>
      </article>
    </div>
  );
}
