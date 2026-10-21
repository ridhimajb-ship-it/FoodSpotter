import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Layers, List, Map as MapIcon } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useFilters } from "../hooks/useFilters";
import type { HotspotMetric, Restaurant } from "../types";
import FilterBar from "../components/FilterBar";
import RestaurantMap from "../components/RestaurantMap";
import MenuRow from "../components/MenuRow";
import RestaurantPanel from "../components/RestaurantPanel";
import { EmptyNote, ErrorBox, Loading, NoDataYet } from "../components/StateViews";

const PAGE = 60;
const SORTS = [{ v: "popularity", l: "Most popular" }, { v: "gem", l: "Hidden-gem score" }, { v: "rating", l: "Highest rating" }, { v: "reviews", l: "Most analysed reviews" }, { v: "name", l: "Name A–Z" }];
type Layer = "pins" | HotspotMetric;
const LAYERS: { v: Layer; l: string }[] = [
  { v: "pins", l: "Pins: review sentiment" }, { v: "reviews", l: "Heatmap: review volume" }, { v: "popularity", l: "Heatmap: popularity" }, { v: "density", l: "Heatmap: restaurant density" },
];

export default function ExplorePage() {
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const { filters, key, active } = useFilters();
  const sort = sp.get("sort") ?? "popularity";
  const gems = sp.get("gems") === "1";
  const focusParam = Number(sp.get("focus")) || null;

  const [selectedId, setSelectedId] = useState<number | null>(focusParam);
  const [focus, setFocus] = useState<{ id: number; n: number } | null>(focusParam ? { id: focusParam, n: 1 } : null);
  const [shown, setShown] = useState(PAGE);
  const [view, setView] = useState<"list" | "map">("list");
  const [layer, setLayer] = useState<Layer>("pins");

  const meta = useFetch((s) => api.meta(s), []);
  const fk = `${key}|${sort}|${gems}`;
  const list = useFetch((s) => api.restaurants({ ...filters, hidden_gems_only: gems, sort, limit: 5000 }, s), [fk]);
  const isHeat = layer !== "pins";
  const heat = useFetch((s) => api.hotspots(layer as HotspotMetric, filters, s), [key, layer], isHeat);

  const items = useMemo(() => list.data?.items ?? [], [list.data]);
  const selected = useMemo(() => items.find((r) => r.id === selectedId) ?? null, [items, selectedId]);
  useEffect(() => { setShown(PAGE); }, [fk]);
  useEffect(() => { if (selectedId != null && list.data && !selected) setSelectedId(null); }, [list.data, selected, selectedId]);

  const choose = useCallback((r: Restaurant, fromList: boolean) => {
    setSelectedId(r.id);
    if (fromList) { setFocus((f) => ({ id: r.id, n: (f?.n ?? 0) + 1 })); setView("map"); }
  }, []);
  const setParam = (k: string, v: string | null) => setSp((cur) => { const n = new URLSearchParams(cur); if (v) n.set(k, v); else n.delete(k); return n; }, { replace: true });
  const empty = meta.data?.totals.restaurants === 0;
  const withReviews = items.filter((r) => r.review_count > 0).length;

  return (
    <div className="mx-auto max-w-[1500px] space-y-4 px-4 py-6 sm:px-6 lg:px-7">
      <header>
        <h1 className="text-[2rem] font-bold leading-tight sm:text-4xl">Explore the map</h1>
        <p className="mt-1.5 max-w-2xl text-[15px] text-muted">Every pin is an OpenStreetMap restaurant. Colour shows what its matched reviews say; grey pins have too few reviews to judge.</p>
      </header>
      <FilterBar />

      {empty ? <NoDataYet /> : (
        <div className="grid gap-4 lg:h-[calc(100vh-120px)] lg:min-h-[640px] lg:grid-cols-[minmax(0,1fr)_410px]">
          <section aria-label="Map" className={`relative min-h-[460px] overflow-hidden rounded-2xl border border-line shadow-soft ${view === "list" ? "hidden lg:block" : "block"}`}>
            <RestaurantMap className="h-full" restaurants={items} colorBy="sentiment" selectedId={selectedId} focus={focus} fitKey={fk}
              heat={isHeat && heat.data ? { points: heat.data.points, metric: layer as HotspotMetric, maxWeight: heat.data.max_weight } : null}
              onSelect={(r) => choose(r, false)} onOpen={(id) => nav(`/restaurants/${id}`)} />
            <label className="absolute right-3 top-3 z-[500] block">
              <span className="sr-only">Map layer</span><Layers className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" aria-hidden />
              <select className="h-9 appearance-none rounded-lg border border-line bg-white pl-8 pr-3 text-[13px] font-medium shadow" value={layer} onChange={(e) => setLayer(e.target.value as Layer)} aria-label="Map layer">
                {LAYERS.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}
              </select>
            </label>
            {(list.loading && list.data) && <div className="absolute left-14 top-3 z-[500] rounded-full bg-white px-3 py-1 text-xs shadow" role="status">Updating…</div>}
            {selected && (
              <div className="absolute inset-x-2 bottom-2 z-[900] max-h-[62%] lg:inset-x-auto lg:bottom-3 lg:left-3 lg:top-14 lg:max-h-none lg:w-[340px]">
                <RestaurantPanel r={selected} onClose={() => setSelectedId(null)} />
              </div>
            )}
          </section>

          <section aria-label="Ranked restaurants" className={`panel min-h-0 flex-col overflow-hidden p-0 ${view === "map" ? "hidden lg:flex" : "flex"}`}>
            <div className="border-b border-line p-4">
              <div className="flex items-center justify-between gap-2">
                <h2 className="card-title">Ranked restaurants</h2>
                <label><span className="sr-only">Sort by</span>
                  <select className="h-8 rounded-lg border border-line bg-white px-2 text-[13px]" aria-label="Sort by" value={sort} onChange={(e) => setParam("sort", e.target.value === "popularity" ? null : e.target.value)}>
                    {SORTS.map((r) => <option key={r.v} value={r.v}>{r.l}</option>)}
                  </select></label>
              </div>
              <div className="mt-2 flex items-center justify-between text-[13px] text-muted" aria-live="polite">
                <span>{list.loading && !list.data ? "Loading…" : list.data ? `${list.data.total.toLocaleString("en-IN")} restaurant${list.data.total === 1 ? "" : "s"} · ${withReviews.toLocaleString("en-IN")} with matched reviews` : ""}</span>
                <button className="chip" aria-pressed={gems} onClick={() => setParam("gems", gems ? null : "1")}>Hidden gems only</button>
              </div>
              {list.data && items.length - withReviews > 0 && <p className="mt-1 text-xs text-muted">Restaurants without matched reviews are listed but have no sentiment or score.</p>}
            </div>
            <div className="min-h-[300px] flex-1 overflow-y-auto">
              {list.loading && !list.data ? <Loading label="Loading restaurants…" /> :
                list.error ? <div className="p-3"><ErrorBox error={list.error} onRetry={list.reload} /></div> :
                items.length === 0 ? <div className="p-3"><EmptyNote title="No restaurants match these filters">Try removing a filter{active ? "" : ""} or searching for a different name.</EmptyNote></div> : (
                  <>
                    <ul>{items.slice(0, shown).map((r, i) => <MenuRow key={r.id} r={r} rank={sort === "name" ? undefined : i + 1} selected={r.id === selectedId} onSelect={(x) => choose(x, true)} showGemScore={sort === "gem"} />)}</ul>
                    {items.length > shown && <div className="p-3 text-center"><button className="btn btn-ghost" onClick={() => setShown((n) => n + PAGE)}>Show {Math.min(PAGE, items.length - shown)} more</button></div>}
                  </>
                )}
            </div>
          </section>

          <div className="fixed bottom-4 left-1/2 z-[1100] -translate-x-1/2 lg:hidden">
            <button className="btn btn-primary shadow-lift" onClick={() => setView((v) => (v === "list" ? "map" : "list"))}>
              {view === "list" ? <><MapIcon className="h-4 w-4" aria-hidden />Show map</> : <><List className="h-4 w-4" aria-hidden />Show list</>}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
