import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.markercluster";
import "leaflet.heat";
import type { Restaurant, HotspotMetric } from "../types";
import { fmtInt } from "../lib/format";

const BENGALURU: [number, number] = [12.9716, 77.5946];
const LABEL_ZOOM = 16;

export const MARKER_COLORS = { selected: "#B8441C", gem: "#E9A23B", scored: "#1E4D3B", unscored: "#8A7F73" } as const;
/** Sentiment colouring uses only the stored positive share of analysed reviews, and needs a minimum of reviews. */
export const SENTIMENT_PIN = { good: "#2E7D4F", mixed: "#E9A23B", poor: "#C4452D", few: "#9C9186" } as const;
export const MIN_REVIEWS_FOR_PIN_COLOUR = 3;
export type ColorBy = "default" | "sentiment";

export function sentimentPin(r: Pick<Restaurant, "positive_share" | "review_count">) {
  if (r.positive_share == null || r.review_count < MIN_REVIEWS_FOR_PIN_COLOUR) return SENTIMENT_PIN.few;
  return r.positive_share >= 0.7 ? SENTIMENT_PIN.good : r.positive_share >= 0.5 ? SENTIMENT_PIN.mixed : SENTIMENT_PIN.poor;
}

function pinIcon(color: string, big = false) {
  const s = big ? 32 : 26;
  return L.divIcon({ className: "fs-pin", html: `<span style="background:${color};width:${s}px;height:${s}px"></span>`, iconSize: [s, s], iconAnchor: [s / 2, s] });
}

function colorFor(r: Restaurant, selected: boolean, by: ColorBy = "default") {
  if (selected) return MARKER_COLORS.selected;
  if (by === "sentiment") return sentimentPin(r);
  if (r.gem_status === "qualified") return MARKER_COLORS.gem;
  return r.popularity_score != null ? MARKER_COLORS.scored : MARKER_COLORS.unscored;
}

function popupContent(r: Restaurant, onOpen: (id: number) => void): HTMLElement {
  const el = document.createElement("div");   // built with textContent: restaurant names are never parsed as HTML
  el.style.minWidth = "190px";
  const t = document.createElement("strong"); t.textContent = r.name; t.style.display = "block"; t.style.fontSize = "14px";
  const s = document.createElement("div"); s.style.cssText = "color:#6B5E54;font-size:12px;margin:2px 0 6px";
  s.textContent = [r.neighborhood_label, r.rating != null ? `★ ${r.rating.toFixed(1)} (${fmtInt(r.rating_count)} votes)` : "No rating on record",
    r.review_count > 0 ? `${r.review_count} analysed review${r.review_count === 1 ? "" : "s"}${r.positive_share != null ? `, ${Math.round(r.positive_share * 100)}% positive` : ""}` : "No matched reviews"].filter(Boolean).join(" · ");
  const b = document.createElement("button"); b.textContent = "View details"; b.type = "button";
  b.style.cssText = "background:#1E4D3B;color:#fff;border:0;border-radius:6px;padding:5px 10px;font-weight:600;cursor:pointer";
  b.onclick = () => onOpen(r.id);
  el.append(t, s, b);
  return el;
}

interface MarkersProps { restaurants: Restaurant[]; selectedId: number | null; onSelect: (r: Restaurant) => void; onOpen: (id: number) => void; focus: { id: number; n: number } | null; fitKey: string; colorBy: ColorBy }

function Markers({ restaurants, selectedId, onSelect, onOpen, focus, fitKey, colorBy }: MarkersProps) {
  const map = useMap();
  const group = useRef<L.MarkerClusterGroup | null>(null);
  const byId = useRef(new Map<number, { marker: L.Marker; r: Restaurant }>());
  const prevSel = useRef<number | null>(null);
  const handlers = useRef({ onSelect, onOpen });
  handlers.current = { onSelect, onOpen };
  const selRef = useRef(selectedId);
  selRef.current = selectedId;
  const lastFit = useRef<string | null>(null);

  useEffect(() => {
    const g = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 48, disableClusteringAtZoom: 17, chunkedLoading: true });
    byId.current.clear();
    restaurants.forEach((r) => {
      if (r.latitude == null || r.longitude == null) return;   // never place a marker without verified coordinates
      const m = L.marker([r.latitude, r.longitude], { icon: pinIcon(colorFor(r, r.id === selRef.current, colorBy), r.id === selRef.current), title: r.name, alt: r.name, keyboard: true });
      m.bindTooltip(r.name, { permanent: true, direction: "right", offset: [12, -14], className: "fs-label fs-label-perm" });
      m.bindPopup(() => popupContent(r, (id) => handlers.current.onOpen(id)), { closeButton: true, autoPanPadding: [40, 40] });
      m.on("click", () => handlers.current.onSelect(r));
      g.addLayer(m);
      byId.current.set(r.id, { marker: m, r });
    });
    map.addLayer(g);
    group.current = g;
    if (lastFit.current !== fitKey && restaurants.length > 0) {
      lastFit.current = fitKey;
      const b = g.getBounds();
      if (b.isValid()) map.fitBounds(b, { padding: [40, 40], maxZoom: 15 });
    }
    return () => { map.removeLayer(g); group.current = null; };
  }, [restaurants, map, fitKey, colorBy]);

  // highlight selection without rebuilding every marker
  useEffect(() => {
    const prev = prevSel.current && byId.current.get(prevSel.current);
    if (prev) prev.marker.setIcon(pinIcon(colorFor(prev.r, false, colorBy)));
    const cur = selectedId != null ? byId.current.get(selectedId) : undefined;
    if (cur) cur.marker.setIcon(pinIcon(MARKER_COLORS.selected, true));
    prevSel.current = selectedId;
  }, [selectedId, restaurants, colorBy]);

  // list click / deep link: reveal the marker even inside a cluster, then open its popup
  useEffect(() => {
    if (!focus) return;
    const hit = byId.current.get(focus.id);
    if (!hit || !group.current) return;
    group.current.zoomToShowLayer(hit.marker, () => { map.panTo(hit.marker.getLatLng()); hit.marker.openPopup(); });
  }, [focus, map]);

  // permanent name labels only when zoomed in enough to avoid clutter
  useEffect(() => {
    const el = map.getContainer();
    const apply = () => el.classList.toggle("labels-on", map.getZoom() >= LABEL_ZOOM);
    apply();
    map.on("zoomend", apply);
    return () => { map.off("zoomend", apply); };
  }, [map]);
  return null;
}

const GRADIENTS: Record<HotspotMetric, Record<number, string>> = {
  density: { 0.2: "#BFD8E6", 0.5: "#5B9BB8", 1: "#1F5C7A" },
  reviews: { 0.2: "#F6DFD2", 0.55: "#E08A5C", 1: "#93350F" },
  popularity: { 0.2: "#DCE9E1", 0.55: "#6BAA86", 1: "#143628" },
};

export function HeatLayer({ points, metric, maxWeight }: { points: [number, number, number][]; metric: HotspotMetric; maxWeight: number }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    const max = maxWeight || 1;
    const layer = L.heatLayer(points.map(([la, lo, w]) => [la, lo, w / max] as [number, number, number]), { radius: 22, blur: 20, maxZoom: 15, minOpacity: 0.3, gradient: GRADIENTS[metric] });
    layer.addTo(map);
    return () => { map.removeLayer(layer); };
  }, [points, metric, maxWeight, map]);
  return null;
}

interface Props {
  restaurants?: Restaurant[];
  selectedId?: number | null;
  onSelect?: (r: Restaurant) => void;
  onOpen?: (id: number) => void;
  focus?: { id: number; n: number } | null;
  fitKey?: string;
  heat?: { points: [number, number, number][]; metric: HotspotMetric; maxWeight: number } | null;
  className?: string;
  center?: [number, number];
  zoom?: number;
  colorBy?: ColorBy;
}

export default function RestaurantMap({ restaurants = [], selectedId = null, onSelect = () => {}, onOpen = () => {}, focus = null, fitKey = "", heat = null, className = "", center = BENGALURU, zoom = 12, colorBy = "default" }: Props) {
  const rs = useMemo(() => restaurants, [restaurants]);
  return (
    <div className={`relative ${className}`}>
      <MapContainer center={center} zoom={zoom} scrollWheelZoom className="h-full w-full" aria-label="Map of restaurants" zoomControl>
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
        <Markers restaurants={rs} selectedId={selectedId} onSelect={onSelect} onOpen={onOpen} focus={focus} fitKey={fitKey} colorBy={colorBy} />
        {heat && <HeatLayer {...heat} />}
      </MapContainer>
      {!heat && colorBy === "default" && (
        <ul className="pointer-events-none absolute bottom-6 left-3 z-[500] flex flex-wrap gap-x-3 gap-y-1 rounded-lg bg-white/90 px-2.5 py-1.5 text-[11px] shadow" aria-label="Map legend">
          <li className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full" style={{ background: MARKER_COLORS.scored }} />Scored</li>
          <li className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full" style={{ background: MARKER_COLORS.gem }} />Hidden gem</li>
          <li className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-full" style={{ background: MARKER_COLORS.unscored }} />No score yet</li>
        </ul>
      )}
      {!heat && colorBy === "sentiment" && (
        <ul className="pointer-events-none absolute bottom-6 left-3 z-[500] space-y-1 rounded-lg bg-white/92 px-2.5 py-2 text-[11px] shadow" aria-label="Map legend">
          <li className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full" style={{ background: SENTIMENT_PIN.good }} />70%+ positive reviews</li>
          <li className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full" style={{ background: SENTIMENT_PIN.mixed }} />50–69% positive</li>
          <li className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full" style={{ background: SENTIMENT_PIN.poor }} />Under 50% positive</li>
          <li className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full" style={{ background: SENTIMENT_PIN.few }} />Fewer than {MIN_REVIEWS_FOR_PIN_COLOUR} reviews</li>
        </ul>
      )}
      {heat && (
        <div className="pointer-events-none absolute bottom-6 left-3 z-[500] rounded-lg bg-white/92 px-2.5 py-2 text-[11px] shadow" aria-label="Heatmap legend">
          <div className="h-2 w-36 rounded-full" style={{ background: `linear-gradient(90deg, ${Object.values(GRADIENTS[heat.metric]).join(",")})` }} />
          <div className="mt-0.5 flex justify-between text-muted"><span>Low</span><span>{heat.metric === "density" ? "Restaurant density" : heat.metric === "reviews" ? "Analysed reviews" : "Popularity score"}</span><span>High</span></div>
        </div>
      )}
    </div>
  );
}
