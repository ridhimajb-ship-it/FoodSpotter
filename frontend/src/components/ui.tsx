import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import type { SentimentLabel } from "../types";
import { SENTIMENT_COLOR, SENTIMENT_TEXT, fmtInt } from "../lib/format";

export function Card({ title, subtitle, icon, action, children, className = "", id }: { title: string; subtitle?: ReactNode; icon?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section aria-labelledby={id} className={`panel flex min-w-0 flex-col p-4 sm:p-5 ${className}`}>
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          {icon && <span className="mt-0.5 text-leaf-dark" aria-hidden>{icon}</span>}
          <div className="min-w-0">
            <h2 id={id} className="card-title">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[13px] leading-snug text-muted">{subtitle}</p>}
          </div>
        </div>
        {action}
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export function ViewAll({ to, children = "View all" }: { to: string; children?: ReactNode }) {
  return <Link to={to} className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-leaf hover:underline">{children}<ArrowRight className="h-3.5 w-3.5" aria-hidden /></Link>;
}

const TONES = { chili: "bg-chili-soft text-chili", saffron: "bg-saffron-soft text-[#B8780F]", leaf: "bg-leaf-soft text-leaf", plain: "bg-[#EFE8D8] text-muted" } as const;
export function KpiCard({ label, value, sub, icon, tone = "leaf" }: { label: string; value: ReactNode; sub?: ReactNode; icon: ReactNode; tone?: keyof typeof TONES }) {
  return (
    <div className="panel flex items-center gap-4 p-4">
      <span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl ${TONES[tone]}`} aria-hidden>{icon}</span>
      <div className="min-w-0">
        <p className="text-[13px] text-ink/80">{label}</p>
        <p className="font-display text-[1.75rem] font-bold leading-tight text-ink">{value}</p>
        {sub && <p className="mt-0.5 text-xs leading-snug text-muted">{sub}</p>}
      </div>
    </div>
  );
}

/** Stacked positive / neutral / negative bar with the three counts in its accessible label. */
export function ShareBar({ positive, neutral, negative, height = "h-3" }: { positive: number; neutral: number; negative: number; height?: string }) {
  const total = positive + neutral + negative;
  const parts: [SentimentLabel, number][] = [["positive", positive], ["neutral", neutral], ["negative", negative]];
  return (
    <div role="img" aria-label={`${total} reviews: ${parts.map(([k, n]) => `${fmtInt(n)} ${SENTIMENT_TEXT[k].toLowerCase()}`).join(", ")}`}
         className={`flex w-full overflow-hidden rounded-full bg-[#EFE8D8] ${height}`}>
      {total > 0 && parts.map(([k, n]) => n > 0 && <div key={k} style={{ width: `${(100 * n) / total}%`, background: SENTIMENT_COLOR[k] }} />)}
    </div>
  );
}

export function RankBadge({ n }: { n: number }) {
  const tone = n === 1 ? "bg-chili text-white" : n === 2 ? "bg-saffron text-ink" : "bg-leaf text-paper";
  return <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-display text-base font-bold ${tone}`} aria-label={`Rank ${n}`}>{n}</span>;
}

export function Tag({ children, tone = "leaf" }: { children: ReactNode; tone?: "leaf" | "chili" | "saffron" | "plain" }) {
  return <span className={`inline-block whitespace-nowrap rounded-md px-2 py-0.5 text-[11.5px] font-medium ${TONES[tone]}`}>{children}</span>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-[#EFE8D8] ${className}`} aria-hidden />;
}
