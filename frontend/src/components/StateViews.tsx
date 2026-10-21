import { ReactNode } from "react";
import { AlertTriangle, DatabaseZap, Loader2, SearchX } from "lucide-react";
import { Link } from "react-router-dom";
import type { ApiError } from "../services/api";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center justify-center gap-2 py-16 text-muted">
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden /> <span>{label}</span>
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="panel flex items-start gap-3 border-neg/40 bg-[#FDF1EF] p-4">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-neg" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">Something went wrong</p>
        <p className="mt-0.5 break-words text-sm text-muted">{error.message}</p>
      </div>
      {onRetry && <button className="btn btn-ghost" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function EmptyNote({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="panel flex flex-col items-center gap-2 px-6 py-10 text-center">
      <div className="text-muted" aria-hidden>{icon ?? <SearchX className="h-7 w-7" />}</div>
      <h3 className="text-lg font-semibold">{title}</h3>
      {children && <div className="max-w-xl text-sm text-muted">{children}</div>}
    </div>
  );
}

/** Shown when the database holds no restaurants yet. No placeholder data is ever substituted. */
export function NoDataYet() {
  return (
    <EmptyNote title="No restaurants loaded yet" icon={<DatabaseZap className="h-8 w-8" />}>
      <p>FoodSpotter only shows real data, and none has been imported into this database yet. To load it:</p>
      <ol className="mx-auto mt-3 max-w-md list-decimal space-y-1.5 pl-5 text-left">
        <li>Run <code className="rounded bg-paper px-1">python scripts/discover_restaurants.py</code> to fetch restaurants and coordinates from OpenStreetMap.</li>
        <li>Download the Kaggle <em>Zomato Bangalore Restaurants</em> CSV into <code className="rounded bg-paper px-1">data/</code>, then run <code className="rounded bg-paper px-1">python scripts/import_reviews.py data/zomato.csv</code>.</li>
        <li>Reload this page.</li>
      </ol>
      <p className="mt-3">Full steps are in the <Link className="font-semibold text-leaf underline" to="/methodology">methodology page</Link> and the README.</p>
    </EmptyNote>
  );
}

export function PageHeader({ title, children, aside }: { title: string; children?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <h1 className="text-3xl font-bold sm:text-4xl">{title}</h1>
        {children && <p className="mt-2 text-muted">{children}</p>}
      </div>
      {aside}
    </header>
  );
}
