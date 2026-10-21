import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompareProvider } from "../hooks/useCompare";
import { toApiFilters } from "../hooks/useFilters";
import { AspectBars, EnginePanel, NeighbourhoodBars, TimeTrend } from "../components/InsightCharts";
import GemList from "../components/GemList";
import { sentimentPin, SENTIMENT_PIN } from "../components/RestaurantMap";
import OverviewPage from "../pages/OverviewPage";
import type { EngineInfo, GemItem, Insights } from "../types";

vi.mock("../components/RestaurantMap", async (orig) => {
  const real = await orig<typeof import("../components/RestaurantMap")>();
  return { ...real, default: ({ restaurants }: { restaurants: unknown[] }) => <div data-testid="map">{restaurants.length} pins</div> };
});

// Synthetic UI fixtures for component tests only. Not restaurant data.
const engine = (active: "bert" | "vader"): EngineInfo => ({
  active, active_label: active === "bert" ? "BERT label" : "VADER lexicon (baseline) + restaurant-domain word list", requested: "auto", reason: "reason text",
  coverage: { matched_reviews: 10, vader: 10, bert: active === "bert" ? 10 : 0, bert_share: active === "bert" ? 1 : 0 }, job: { running: false, last: null },
  bert: { model: { id: "m", architecture: "a", output: "o", languages: ["English"], licence: "MIT", card_url: "https://x", mapping: "m", limitations: ["l"], authors_reported_accuracy_note: "n" }, model_id_configured: "m", revision: null, packages_installed: false, unavailable_reason: null, max_tokens: 512, predictions_stored: 0, run_in_this_database: false },
  vader: { model: "vader+domain", label: "VADER", predictions_stored: 10 },
});
const aspect = (aspect: string, label: string, mentions: number) => ({ aspect, label, mentions, positive: mentions, neutral: 0, negative: 0, positive_share: mentions ? 1 : null, negative_share: 0, net_score: 1, review_coverage: 0.5, restaurants_with_mentions: 1, restaurants_with_evidence: 1, min_mentions_required: 5 });
const insights = (n: number, inDb = n): Insights => ({
  filters_applied: {}, engine: engine("vader"),
  scope: { restaurants: n, restaurants_with_reviews: n, reviews_analysed: n * 10, restaurants_in_database: inDb },
  sentiment: { n: n * 10, positive: n * 6, neutral: n * 1, negative: n * 3, positive_share: 0.6, neutral_share: 0.1, negative_share: 0.3 },
  engine_comparison: null, aspects: [aspect("food", "Food quality", 20), aspect("service", "Service", 2)], aspect_method: "Rule-based (not BERT).",
  neighborhoods: [], cuisines: [], hidden_gems: { items: [], status_counts: { qualified: 0 }, criteria: { min_analysed_reviews: 8, min_positive_confidence_bound: 0.55, max_visibility_percentile: 0.5, min_adjusted_rating: 3.8 } },
  time_trend: { available: false, dated_reviews: 0, months: 0, reason: "These reviews have no dates, so no time trend is shown." },
  pipeline: { restaurants_discovered: inDb, restaurants_total: inDb, restaurants_with_matched_reviews: n, reviews_stored: n * 10, reviews_matched: n * 10, reviews_by_match_status: {}, reviews_unresolved_stored: 0, reviews_analysed: n * 10, dated_reviews: 0, engine: engine("vader"), import: null },
});

function mockApi(ins: Insights, restaurants = 0) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = url.startsWith("/api/insights") ? ins : url.startsWith("/api/meta") ? { neighborhoods: [], cuisines: [], features: {}, totals: { restaurants: ins.scope.restaurants_in_database, reviews: 0 }, map_attribution: "", min_aspect_mentions: 5 }
      : url.startsWith("/api/restaurants") ? { total: restaurants, items: [], limit: 1, offset: 0 } : { points: [], n_points: 0, max_weight: 1 };
    return { ok: true, status: 200, json: async () => body };
  }));
}
afterEach(() => vi.restoreAllMocks());

describe("filters", () => {
  it("maps URL params to API filters and drops invalid values", () => {
    const f = toApiFilters(new URLSearchParams("q=dosa&neighborhood=indiranagar&price=500-1000&min_rating=4&sentiment=positive&aspect=food&min_reviews=10"));
    expect(f).toEqual({ q: "dosa", neighborhood: "indiranagar", price_min: 500, price_max: 1000, min_rating: 4, sentiment: "positive", aspect: "food", min_reviews: 10 });
    expect(toApiFilters(new URLSearchParams("sentiment=sideways&aspect=nonsense&min_reviews=-3&price=2000-"))).toEqual({ price_min: 2000 });
  });
});

describe("map colouring", () => {
  it("colours by positive share only with enough reviews", () => {
    expect(sentimentPin({ positive_share: 0.9, review_count: 2 })).toBe(SENTIMENT_PIN.few);
    expect(sentimentPin({ positive_share: null, review_count: 50 })).toBe(SENTIMENT_PIN.few);
    expect(sentimentPin({ positive_share: 0.7, review_count: 3 })).toBe(SENTIMENT_PIN.good);
    expect(sentimentPin({ positive_share: 0.55, review_count: 9 })).toBe(SENTIMENT_PIN.mixed);
    expect(sentimentPin({ positive_share: 0.2, review_count: 9 })).toBe(SENTIMENT_PIN.poor);
  });
});

describe("insight charts", () => {
  it("scores an aspect only with enough mentions", () => {
    render(<AspectBars aspects={[aspect("food", "Food quality", 20), aspect("service", "Service", 2), aspect("hygiene", "Hygiene", 0)]} minMentions={5} />);
    expect(screen.getByText(/20 mentions/)).toBeInTheDocument();
    expect(screen.getByText(/Only 2 mentions \(needs 5\)/)).toBeInTheDocument();
    expect(screen.getByText(/No mentions in this scope/)).toBeInTheDocument();
    expect(screen.getAllByText("–").length).toBe(2);
  });
  it("labels the VADER baseline as VADER and never as BERT", () => {
    const { rerender } = render(<MemoryRouter><EnginePanel e={engine("vader")} comparison={null} /></MemoryRouter>);
    expect(screen.getByText("VADER baseline")).toBeInTheDocument(); expect(screen.queryByText("BERT")).toBeNull();
    rerender(<MemoryRouter><EnginePanel e={engine("bert")} comparison={{ other_engine: "vader", reviews_with_both: 10, agreement: 0.8, matrix: {} }} /></MemoryRouter>);
    expect(screen.getByText("BERT")).toBeInTheDocument(); expect(screen.getByText(/not accuracy/)).toBeInTheDocument();
  });
  it("shows no time trend without dates, and says why", () => {
    render(<TimeTrend t={{ available: false, dated_reviews: 0, months: 0, reason: "These reviews have no dates, so no time trend is shown." }} />);
    expect(screen.getByText(/No time trend is shown/)).toBeInTheDocument(); expect(screen.getByText(/does not guess dates/)).toBeInTheDocument();
  });
  it("neighbourhood bars hide the share when evidence is thin", () => {
    const h = (label: string, reviews: number) => ({ neighborhood: label.toLowerCase(), label, selected: false, restaurants: 3, restaurants_with_reviews: 2, reviews, positive: reviews, neutral: 0, negative: 0, positive_share: 1, negative_share: 0, mean_popularity: null });
    render(<NeighbourhoodBars items={[h("Alpha", 40), h("Beta", 4)]} />);
    expect(screen.getByText(/under 10, so no share shown/)).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: /Alpha/ })).getByText("100%")).toBeInTheDocument();
  });
});

describe("GemList", () => {
  it("renders the stored evidence, not derived claims", () => {
    const g = { id: 5, name: "Fixture Gem", cuisines: ["cafe"], neighborhood_label: "Indiranagar", rating: 4.5, rating_count: 30,
      evidence: { analysed_reviews: 12, positive_reviews: 11, positive_share: 0.9, positive_lower_bound: 0.65, adjusted_rating: 4.1, ratings_on_record: 30, visibility_percentile: 0.2, praised_aspects: ["Food quality"] }, explanation: "Because evidence." } as unknown as GemItem;
    render(<MemoryRouter><GemList items={[g]} /></MemoryRouter>);
    expect(screen.getByText("11/12 reviews positive")).toBeInTheDocument(); expect(screen.getByText(/≥65%/)).toBeInTheDocument();
    expect(screen.getByText("Praised: Food quality")).toBeInTheDocument(); expect(screen.getByText("Because evidence.")).toBeInTheDocument();
  });
});

describe("OverviewPage", () => {
  const renderPage = () => render(<MemoryRouter><CompareProvider><OverviewPage /></CompareProvider></MemoryRouter>);
  it("shows a polished empty state, with no KPI numbers, when the database is empty", async () => {
    mockApi(insights(0, 0));
    renderPage();
    expect(await screen.findByText("No restaurants loaded yet")).toBeInTheDocument();
    expect(screen.queryByText("Restaurants discovered")).toBeNull(); expect(screen.queryByTestId("map")).toBeNull();
  });
  it("shows only API-provided figures, including the no-dates note", async () => {
    mockApi(insights(7, 9), 7);
    renderPage();
    expect(await screen.findByText("Restaurants discovered")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("70").length).toBeGreaterThan(0));           // 7 restaurants × 10 reviews, from the API response
    expect(screen.getAllByText("7").length).toBeGreaterThan(0);
    expect(screen.getByText("sentiment: VADER baseline")).toBeInTheDocument();
    expect(screen.getByText(/No time trend is shown/)).toBeInTheDocument();
    expect(screen.getByText("No hidden gems in this selection.")).toBeInTheDocument();
  });
  it("explains zero matches when filters exclude everything", async () => {
    mockApi(insights(0, 9));
    renderPage();
    expect(await screen.findByText("No restaurants match these filters")).toBeInTheDocument();
  });
});
