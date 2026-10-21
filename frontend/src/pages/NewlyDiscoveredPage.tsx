import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MapPin, RefreshCw } from "lucide-react";
import { api, ApiError } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { cuisineText, fmtDate } from "../lib/format";
import { InfoNote } from "../components/Badges";
import { EmptyNote, ErrorBox, Loading, PageHeader } from "../components/StateViews";

export default function NewlyDiscoveredPage() {
  const nd = useFetch((s) => api.newlyDiscovered(s), []);
  const [token, setToken] = useState("");   // kept only in memory, never persisted
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const running = nd.data?.refresh_running ?? false;

  useEffect(() => {
    if (!running) return;
    const t = setInterval(nd.reload, 3000);   // poll while a refresh is in progress
    return () => clearInterval(t);
  }, [running, nd.reload]);

  const start = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.refresh(token, { source: "osm" });
      setMsg({ ok: true, text: r.is_baseline ? "Baseline scan started. Restaurants found now count as existing, not new." : "Refresh started." });
      nd.reload();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? (e.status === 401 ? "That admin token wasn't accepted." : e.status === 503 ? "Admin access is switched off on the server. Set ADMIN_TOKEN in .env and restart." : e.message) : "Couldn't start the refresh." });
    } finally { setBusy(false); }
  };

  const d = nd.data;
  const run = d?.last_run;
  return (
    <div className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-7">
      <PageHeader title="Newly discovered">Restaurants FoodSpotter has found since its first scan of the area. "Newly discovered" describes when we found a place, not when it opened.</PageHeader>
      {d && <div className="mb-5"><InfoNote>{d.note}</InfoNote></div>}

      {nd.loading && !d ? <Loading /> : nd.error ? <ErrorBox error={nd.error} onRetry={nd.reload} /> : d && (
        <>
          {run && (
            <p className={`mb-4 text-sm ${run.status === "failed" ? "text-neg" : "text-muted"}`} aria-live="polite">
              Last refresh ({run.source === "osm" ? "OpenStreetMap" : "Google Places"}): <strong>{run.status}</strong>, {fmtDate(run.finished_at ?? run.started_at)}. Found {run.found}, new {run.new}, flagged for recheck {run.flagged}.
              {run.errors.length > 0 && <span className="mt-1 block">Problems: {run.errors.slice(0, 3).join("; ")}</span>}
            </p>
          )}
          {running && <p role="status" className="mb-4 flex items-center gap-2 text-sm text-leaf"><RefreshCw className="h-4 w-4 animate-spin" aria-hidden />Refresh in progress…</p>}

          {d.items.length === 0 ? (
            <EmptyNote title={d.baseline_established ? "Nothing new since the baseline scan" : "No baseline scan yet"}>
              {d.baseline_established
                ? "The next refresh will list any restaurant that wasn't in the baseline. Refreshes are manual, or scheduled on the server."
                : "Run a first scan to record the restaurants that already exist. Only places found in later scans are listed here."}
            </EmptyNote>
          ) : (
            <div className="panel overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <caption className="sr-only">Restaurants first discovered after the baseline scan</caption>
                <thead className="border-b border-line text-muted"><tr><th scope="col" className="px-4 py-3 font-medium">Restaurant</th><th scope="col" className="px-4 py-3 font-medium">Area</th><th scope="col" className="px-4 py-3 font-medium">Cuisine</th><th scope="col" className="px-4 py-3 font-medium">Rating</th><th scope="col" className="px-4 py-3 font-medium">First discovered</th><th scope="col" className="px-4 py-3"><span className="sr-only">Map</span></th></tr></thead>
                <tbody>
                  {d.items.map((r) => (
                    <tr key={r.id} className="border-b border-line last:border-0">
                      <th scope="row" className="px-4 py-3 font-display font-bold"><Link className="hover:underline" to={`/restaurants/${r.id}`}>{r.name}</Link></th>
                      <td className="px-4 py-3">{r.neighborhood_label ?? "Unknown"}</td>
                      <td className="px-4 py-3">{cuisineText(r.cuisines)}</td>
                      <td className="px-4 py-3">{r.rating != null ? r.rating.toFixed(1) : <span className="text-muted">No rating yet</span>}</td>
                      <td className="px-4 py-3 text-muted">{fmtDate(r.first_discovered_at)}</td>
                      <td className="px-4 py-3"><Link className="btn btn-ghost px-2 py-1.5" to={`/?focus=${r.id}`} aria-label={`Show ${r.name} on the map`}><MapPin className="h-4 w-4" aria-hidden /></Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <details className="panel mt-8 p-4">
            <summary className="cursor-pointer font-semibold">Run a refresh now (administrators)</summary>
            <p className="mt-2 text-sm text-muted">Fetches the latest restaurants from OpenStreetMap, respecting its rate limits. This takes a few minutes. The first scan becomes the baseline.</p>
            <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); void start(); }}>
              <label className="flex-1 text-sm"><span className="mb-1 block font-medium">Admin token</span>
                <input className="field" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="The ADMIN_TOKEN from the server's .env" /></label>
              <button className="btn btn-primary" type="submit" disabled={!token || busy || running}>{busy || running ? "Refreshing…" : "Refresh restaurants"}</button>
            </form>
            {msg && <p role={msg.ok ? "status" : "alert"} className={`mt-2 text-sm ${msg.ok ? "text-leaf" : "text-neg"}`}>{msg.text}</p>}
          </details>
        </>
      )}
    </div>
  );
}
