import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CompareProvider, useCompare } from "../hooks/useCompare";
import MenuRow from "../components/MenuRow";
import { ErrorBox, NoDataYet } from "../components/StateViews";
import SentimentBar from "../components/SentimentBar";
import AspectChart from "../components/AspectChart";
import { api, ApiError } from "../services/api";
import { cuisineText, fmtInt, pct } from "../lib/format";
import type { Restaurant } from "../types";

// NOTE: these are synthetic UI fixtures for component tests only, not restaurant data.
const base: Restaurant = {
  id: 1, name: "Fixture Bistro", address: null, neighborhood: "indiranagar", neighborhood_label: "Indiranagar", cuisines: ["north indian"],
  latitude: 12.97, longitude: 77.64, rating: null, rating_count: null, rating_source: null, price_info: null, review_count: 0, positive_share: null,
  popularity_score: null, popularity_rank: null, hidden_gem_score: null, gem_status: "insufficient_evidence", confidence: null, needs_recheck: false, first_discovered_at: null,
};
const wrap = (ui: React.ReactNode) => render(<MemoryRouter><CompareProvider><ul>{ui}</ul></CompareProvider></MemoryRouter>);

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("format helpers", () => {
  it("handles missing values without inventing data", () => {
    expect(fmtInt(null)).toBe("–"); expect(pct(undefined)).toBe("–"); expect(pct(0.256)).toBe("26%");
    expect(cuisineText([])).toBe("Cuisine not listed"); expect(cuisineText(["north indian", "chinese"])).toBe("North Indian, Chinese");
  });
});

describe("compare selection", () => {
  const w = ({ children }: { children: React.ReactNode }) => <CompareProvider>{children}</CompareProvider>;
  it("allows at most three restaurants and persists them", () => {
    const { result } = renderHook(() => useCompare(), { wrapper: w });
    act(() => { [1, 2, 3].forEach((i) => result.current.add(i)); });
    expect(result.current.ids).toEqual([1, 2, 3]); expect(result.current.full).toBe(true);
    let ok = true; act(() => { ok = result.current.add(4); });
    expect(ok).toBe(false); expect(result.current.ids).toEqual([1, 2, 3]);
    act(() => result.current.remove(2));
    expect(JSON.parse(localStorage.getItem("foodspotter.compare")!)).toEqual([1, 3]);
  });
  it("ignores corrupt storage", () => {
    localStorage.setItem("foodspotter.compare", "{not json");
    const { result } = renderHook(() => useCompare(), { wrapper: w });
    expect(result.current.ids).toEqual([]);
  });
});

describe("MenuRow", () => {
  it("shows a dash and honest text when a restaurant is unscored", () => {
    wrap(<MenuRow r={base} />);
    expect(screen.getByText("No rating on record")).toBeInTheDocument();
    expect(screen.getByText("No reviews analysed")).toBeInTheDocument();
    expect(screen.getByTitle(/Not scored/)).toHaveTextContent("–");
  });
  it("shows rating, score and badges when present, and toggles comparison", () => {
    wrap(<MenuRow r={{ ...base, rating: 4.2, rating_count: 1204, popularity_score: 71.4, review_count: 10, positive_share: 0.8, gem_status: "qualified" }} />);
    expect(screen.getByText("4.2")).toBeInTheDocument(); expect(screen.getByText("71")).toBeInTheDocument();
    expect(screen.getByText("Hidden gem")).toBeInTheDocument(); expect(screen.getByText(/80% positive/)).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: /Add Fixture Bistro to comparison/ });
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: /Remove Fixture Bistro from comparison/ })).toHaveAttribute("aria-pressed", "true");
  });
  it("calls onSelect when chosen", () => {
    const onSelect = vi.fn(); wrap(<MenuRow r={base} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /^Fixture Bistro/ }));
    expect(onSelect).toHaveBeenCalledWith(base);
  });
});

describe("state views", () => {
  it("empty state explains how to import real data", () => {
    render(<MemoryRouter><NoDataYet /></MemoryRouter>);
    expect(screen.getByText(/discover_restaurants.py/)).toBeInTheDocument(); expect(screen.getByText(/import_reviews.py/)).toBeInTheDocument();
  });
  it("error box announces and retries", () => {
    const retry = vi.fn(); render(<ErrorBox error={new Error("boom")} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("boom"); fireEvent.click(screen.getByText("Try again")); expect(retry).toHaveBeenCalled();
  });
});

describe("charts", () => {
  it("sentiment bar describes counts for assistive tech", () => {
    render(<SentimentBar counts={{ positive: 6, neutral: 2, negative: 2 }} />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", expect.stringContaining("Positive 6"));
    expect(screen.getByText("(60%)")).toBeInTheDocument();
  });
  it("aspect chart refuses to score aspects without evidence", () => {
    const a = (aspect: string, label: string, n: number, ok: boolean) => ({ aspect, label, mentions: n, positive: n, negative: 0, neutral: 0, score: 1, positive_share: 1, negative_share: 0, sufficient_evidence: ok, min_mentions_required: 5 });
    render(<AspectChart aspects={[a("food", "Food quality", 2, false)]} minMentions={5} />);
    expect(screen.getByText(/No aspect has at least 5 mentions/)).toBeInTheDocument();
  });
});

describe("api client", () => {
  it("turns FastAPI error details into readable messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: [{ msg: "bad rating" }] }) }));
    await expect(api.restaurants({})).rejects.toMatchObject({ status: 422, message: "bad rating" });
  });
  it("explains an unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.meta()).rejects.toThrow(/Can't reach the FoodSpotter server/);
  });
  it("sends the admin token only as a header", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 202, json: async () => ({ run_id: 1 }) }); vi.stubGlobal("fetch", f);
    await api.refresh("sekret", { source: "osm" });
    const [url, init] = f.mock.calls[0]; expect(url).not.toContain("sekret"); expect(init.headers["X-Admin-Token"]).toBe("sekret");
    expect(init.headers["Content-Type"]).toBe("application/json");
  });
  it("ApiError carries status", () => { expect(new ApiError(404, "x").status).toBe(404); });
});

it("api.restaurants builds a clean query string", async () => {
  const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 0 }) }); vi.stubGlobal("fetch", f);
  await api.restaurants({ q: "dosa", neighborhood: "", hidden_gems_only: false, min_rating: 4 });
  await waitFor(() => expect(f).toHaveBeenCalled());
  expect(f.mock.calls[0][0]).toBe("/api/restaurants?q=dosa&min_rating=4");
});
