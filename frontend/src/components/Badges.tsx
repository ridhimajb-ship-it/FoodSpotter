import { AlertCircle, Gem, Info } from "lucide-react";
import type { Restaurant } from "../types";
import { GEM_REASON } from "../lib/format";

export function GemBadge({ r }: { r: Pick<Restaurant, "gem_status"> }) {
  if (r.gem_status !== "qualified") return null;
  return <span className="inline-flex items-center gap-1 rounded-full bg-saffron-soft px-2 py-0.5 text-xs font-semibold text-[#7A4B00]"><Gem className="h-3 w-3" aria-hidden />Hidden gem</span>;
}

export function RecheckBadge({ r }: { r: Pick<Restaurant, "needs_recheck"> }) {
  if (!r.needs_recheck) return null;
  return <span title="Not returned by the latest source check; it may have closed or moved." className="inline-flex items-center gap-1 rounded-full bg-chili-soft px-2 py-0.5 text-xs font-semibold text-chili-dark"><AlertCircle className="h-3 w-3" aria-hidden />Needs recheck</span>;
}

export function GemStatusText({ status }: { status: string }) {
  return <span className="text-xs text-muted">{GEM_REASON[status] ?? status}</span>;
}

export function InfoNote({ children }: { children: React.ReactNode }) {
  return <p className="flex items-start gap-2 rounded-lg bg-leaf-soft/60 px-3 py-2 text-sm text-leaf-dark"><Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /><span>{children}</span></p>;
}
