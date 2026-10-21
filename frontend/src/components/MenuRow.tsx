import { Link } from "react-router-dom";
import { Plus, Check, Star } from "lucide-react";
import type { Restaurant } from "../types";
import { cuisineText, fmtInt, pct } from "../lib/format";
import { GemBadge, RecheckBadge } from "./Badges";
import { useCompare } from "../hooks/useCompare";

interface Props {
  r: Restaurant;
  rank?: number;
  selected?: boolean;
  onSelect?: (r: Restaurant) => void;
  showGemScore?: boolean;
}

/** A restaurant listed like a line on a menu: name, dotted leader, score. */
export default function MenuRow({ r, rank, selected, onSelect, showGemScore }: Props) {
  const cmp = useCompare();
  const inCmp = cmp.has(r.id);
  const score = showGemScore ? r.hidden_gem_score : r.popularity_score;
  const body = (
    <>
      <span className="flex items-baseline gap-2">
        {rank != null && <span className="w-7 shrink-0 text-right font-display text-sm font-bold text-chili">{rank}</span>}
        <span className="font-display text-[1.05rem] font-bold leading-snug">{r.name}</span>
        <span className="leader" aria-hidden />
        <span className="shrink-0 font-display text-lg font-bold text-leaf" title={score == null ? "Not scored: no rating or analysed review text" : showGemScore ? "Hidden-gem score" : "Popularity score (0–100)"}>
          {score == null ? "–" : score.toFixed(0)}
        </span>
      </span>
      <span className={`mt-0.5 block text-sm text-muted ${rank != null ? "pl-9" : ""}`}>
        {cuisineText(r.cuisines)} · {r.neighborhood_label ?? "Area unknown"}
      </span>
      <span className={`mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs ${rank != null ? "pl-9" : ""}`}>
        {r.rating != null ? (
          <span className="inline-flex items-center gap-1 font-semibold"><Star className="h-3.5 w-3.5 fill-saffron text-saffron" aria-hidden />{r.rating.toFixed(1)}<span className="font-normal text-muted">({fmtInt(r.rating_count)} votes)</span></span>
        ) : <span className="text-muted">No rating on record</span>}
        {r.review_count > 0 ? <span className="text-muted">{r.review_count} reviews analysed · {pct(r.positive_share)} positive</span> : <span className="text-muted">No reviews analysed</span>}
        <GemBadge r={r} /><RecheckBadge r={r} />
      </span>
    </>
  );
  return (
    <li className={`flex items-stretch gap-2 border-b border-line px-3 py-3 transition-colors last:border-0 ${selected ? "bg-chili-soft/50" : "hover:bg-white"}`}>
      {onSelect ? (
        <button type="button" aria-pressed={selected} onClick={() => onSelect(r)} className="min-w-0 flex-1 text-left">{body}</button>
      ) : (
        <Link to={`/restaurants/${r.id}`} className="min-w-0 flex-1">{body}</Link>
      )}
      <button
        type="button" aria-pressed={inCmp}
        aria-label={inCmp ? `Remove ${r.name} from comparison` : `Add ${r.name} to comparison`}
        title={inCmp ? "Remove from comparison" : cmp.full ? "You can compare up to three restaurants" : "Add to comparison"}
        disabled={!inCmp && cmp.full}
        onClick={() => cmp.toggle(r.id)}
        className={`btn self-start px-2 py-1.5 ${inCmp ? "btn-primary" : "btn-ghost"}`}
      >
        {inCmp ? <Check className="h-4 w-4" aria-hidden /> : <Plus className="h-4 w-4" aria-hidden />}
      </button>
    </li>
  );
}
