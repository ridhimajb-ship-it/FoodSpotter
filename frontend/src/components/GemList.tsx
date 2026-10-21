import { Link } from "react-router-dom";
import { MapPin, Star } from "lucide-react";
import type { GemItem } from "../types";
import { cuisineText, fmtInt, pct } from "../lib/format";
import { RankBadge, Tag } from "./ui";

/** Ranked hidden-gem rows. Every figure is from the stored evidence object returned by the API. */
export default function GemList({ items, compact = false }: { items: GemItem[]; compact?: boolean }) {
  return (
    <ol className="divide-y divide-line">
      {items.map((g, i) => (
        <li key={g.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
          <RankBadge n={i + 1} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-start justify-between gap-x-3">
              <div className="min-w-0">
                <Link to={`/restaurants/${g.id}`} className="font-display text-[15px] font-bold leading-tight text-ink hover:text-leaf hover:underline">{g.name}</Link>
                <p className="text-xs text-muted">{cuisineText(g.cuisines)}</p>
                <p className="mt-0.5 flex items-center gap-1 text-xs text-muted"><MapPin className="h-3 w-3" aria-hidden />{g.neighborhood_label ?? "Area unknown"}</p>
              </div>
              <p className="flex items-center gap-1 text-sm font-semibold" title="Rating and vote count from the historical dataset">
                {g.rating != null ? <><Star className="h-3.5 w-3.5 fill-saffron text-saffron" aria-hidden />{g.rating.toFixed(1)}<span className="font-normal text-muted">({fmtInt(g.rating_count)})</span></> : <span className="font-normal text-muted">No rating</span>}
              </p>
            </div>
            <p className="mt-1.5 flex flex-wrap gap-1.5">
              <Tag tone="leaf">{g.evidence.positive_reviews}/{g.evidence.analysed_reviews} reviews positive</Tag>
              <Tag tone="saffron">≥{pct(g.evidence.positive_lower_bound)} (confidence-adjusted)</Tag>
              {g.evidence.visibility_percentile != null && <Tag tone="plain">more visible than {pct(g.evidence.visibility_percentile)} of restaurants</Tag>}
              {g.evidence.praised_aspects.slice(0, compact ? 2 : 4).map((a) => <Tag key={a} tone="chili">Praised: {a}</Tag>)}
            </p>
            {!compact && g.explanation && <p className="mt-1.5 text-[13px] leading-snug text-muted">{g.explanation}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
