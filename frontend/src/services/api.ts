import type * as T from "../types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<R>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<R> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, signal, headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...(init?.headers as Record<string, string> | undefined) } });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Can't reach the FoodSpotter server. Start the backend (uvicorn backend.main:app) and reload.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join("; ") : detail;
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<R>;
}

const qs = (p: Record<string, string | number | boolean | undefined | null>) => {
  const u = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "" && v !== false) u.set(k, String(v)); });
  const s = u.toString();
  return s ? `?${s}` : "";
};

export interface ListParams { q?: string; neighborhood?: string; cuisine?: string; min_rating?: number; price_min?: number; price_max?: number; sentiment?: string; aspect?: string; min_reviews?: number; min_popularity?: number; hidden_gems_only?: boolean; has_reviews?: boolean; sort?: string; limit?: number; offset?: number }

export const api = {
  meta: (s?: AbortSignal) => request<T.Meta>("/api/meta", undefined, s),
  restaurants: (p: ListParams, s?: AbortSignal) => request<T.Page<T.Restaurant>>(`/api/restaurants${qs({ ...p })}`, undefined, s),
  suggest: (q: string, s?: AbortSignal) => request<{ suggestions: T.Suggestion[] }>(`/api/restaurants/search${qs({ q })}`, undefined, s),
  restaurant: (id: number, s?: AbortSignal) => request<T.RestaurantDetail>(`/api/restaurants/${id}`, undefined, s),
  reviews: (id: number, p: { sentiment?: string; aspect?: string; sort?: string; limit?: number; offset?: number }, s?: AbortSignal) =>
    request<T.ReviewPage>(`/api/restaurants/${id}/reviews${qs(p)}`, undefined, s),
  sentiment: (id: number, s?: AbortSignal) => request<T.SentimentInfo>(`/api/restaurants/${id}/sentiment`, undefined, s),
  aspects: (id: number, s?: AbortSignal) => request<T.AspectInfo>(`/api/restaurants/${id}/aspects`, undefined, s),
  liveReviews: (id: number, s?: AbortSignal) => request<T.LiveReviews>(`/api/restaurants/${id}/live-reviews`, undefined, s),
  popular: (p: { neighborhood?: string; cuisine?: string; limit?: number }, s?: AbortSignal) => request<T.PopularResponse>(`/api/restaurants/popular${qs(p)}`, undefined, s),
  gems: (p: T.Filters & { limit?: number }, s?: AbortSignal) => request<T.GemsResponse>(`/api/restaurants/hidden-gems${qs({ ...p })}`, undefined, s),
  newlyDiscovered: (s?: AbortSignal) => request<T.NewResponse>("/api/restaurants/newly-discovered", undefined, s),
  compare: (ids: number[], s?: AbortSignal) => request<{ items: T.CompareItem[]; min_aspect_mentions: number }>("/api/restaurants/compare", { method: "POST", body: JSON.stringify({ ids }) }, s),
  overview: (s?: AbortSignal) => request<T.Overview>("/api/analytics/overview", undefined, s),
  hotspots: (metric: T.HotspotMetric, f: T.Filters = {}, s?: AbortSignal) => request<T.Hotspots>(`/api/analytics/hotspots${qs({ metric, ...f })}`, undefined, s),
  insights: (f: T.Filters, s?: AbortSignal) => request<T.Insights>(`/api/insights${qs({ ...f })}`, undefined, s),
  pipeline: (s?: AbortSignal) => request<T.PipelineSummary>("/api/analytics/pipeline", undefined, s),
  sentimentEngine: (s?: AbortSignal) => request<T.EngineInfo>("/api/analytics/sentiment-engine", undefined, s),
  cuisines: (s?: AbortSignal) => request<T.CuisineStats>("/api/analytics/cuisines", undefined, s),
  neighborhoods: (s?: AbortSignal) => request<T.HoodStats>("/api/analytics/neighborhoods", undefined, s),
  keywords: (s?: AbortSignal) => request<T.Keywords>("/api/analytics/keywords", undefined, s),
  evaluation: (s?: AbortSignal) => request<T.EvaluationResults>("/api/evaluation/latest", undefined, s),
  /** Admin: starts a background refresh. The token is typed by the admin at runtime and is never stored or bundled. */
  refresh: (token: string, body: { source?: "osm" | "google"; neighborhoods?: string[]; use_cache?: boolean }) =>
    request<{ run_id: number; status: string; is_baseline: boolean; message: string }>("/api/admin/refresh-restaurants", {
      method: "POST", body: JSON.stringify(body), headers: { "X-Admin-Token": token },
    }),
};
