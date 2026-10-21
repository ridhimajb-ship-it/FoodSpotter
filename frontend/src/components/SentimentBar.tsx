import { SENTIMENT_COLOR, SENTIMENT_TEXT, fmtInt } from "../lib/format";
import type { SentimentLabel } from "../types";

const order: SentimentLabel[] = ["positive", "neutral", "negative"];

export default function SentimentBar({ counts, compact = false }: { counts: Record<SentimentLabel, number>; compact?: boolean }) {
  const total = order.reduce((s, k) => s + (counts[k] ?? 0), 0);
  if (!total) return <p className="text-sm text-muted">No analysed reviews.</p>;
  const label = order.map((k) => `${SENTIMENT_TEXT[k]} ${counts[k]}`).join(", ");
  return (
    <div>
      <div role="img" aria-label={`Sentiment of ${total} reviews: ${label}`} className={`flex w-full overflow-hidden rounded-full ${compact ? "h-2" : "h-3.5"}`}>
        {order.map((k) => counts[k] > 0 && <div key={k} style={{ width: `${(100 * counts[k]) / total}%`, background: SENTIMENT_COLOR[k] }} />)}
      </div>
      {!compact && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {order.map((k) => (
            <li key={k} className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: SENTIMENT_COLOR[k] }} aria-hidden />
              {SENTIMENT_TEXT[k]} <strong>{fmtInt(counts[k])}</strong> <span className="text-muted">({Math.round((100 * counts[k]) / total)}%)</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
