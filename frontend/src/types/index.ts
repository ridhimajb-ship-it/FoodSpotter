export type GemStatus = "qualified" | "insufficient_evidence" | "not_positive_enough" | "not_low_visibility";

export interface Restaurant {
  id: number;
  name: string;
  address: string | null;
  neighborhood: string | null;
  neighborhood_label: string | null;
  cuisines: string[];
  latitude: number | null;
  longitude: number | null;
  rating: number | null;
  rating_count: number | null;
  rating_source: string | null;
  price_info: string | null;
  review_count: number;
  positive_share: number | null;
  popularity_score: number | null;
  popularity_rank: number | null;
  hidden_gem_score: number | null;
  gem_status: GemStatus;
  confidence: number | null;
  needs_recheck: boolean;
  first_discovered_at: string | null;
  gem_explanation?: string | null;
  visibility_percentile?: number | null;
}

export interface RestaurantDetail extends Restaurant {
  source: string | null;
  source_url: string | null;
  source_attribution: string | null;
  rating_note: string | null;
  price_source: string | null;
  last_verified_at: string | null;
  recheck_reason: string | null;
  opening_date: string | null;
  ranking_explanation: string[];
  ranking_components: Record<string, { value: number; weight: number; raw?: number; adjusted?: number }>;
  gem_explanation: string | null;
  visibility_percentile: number | null;
  directions_url: string | null;
  has_google_place_id: boolean;
}

export interface Page<T> { total: number; limit: number; offset: number; items: T[] }

export interface Neighborhood { key: string; label: string; restaurants: number; center: [number, number] }
export interface Meta {
  neighborhoods: Neighborhood[];
  cuisines: { value: string; label: string; restaurants: number }[];
  features: { google_live_reviews: boolean; admin_enabled: boolean };
  totals: { restaurants: number; reviews: number };
  map_attribution: string;
  min_aspect_mentions: number;
}

export type SentimentLabel = "positive" | "negative" | "neutral";

export interface ReviewItem {
  id: number;
  text: string;
  rating: number | null;
  reviewed_at: string | null;
  date_note: string | null;
  source: string;
  source_label: string;
  match_status: string;
  match_confidence?: number | null;
  sentiment: { engine: SentimentEngine; label: SentimentLabel; confidence: number | null; compound: number } | null;
  bert: BertResult | null;
  vader: { label: SentimentLabel; compound: number } | null;
  aspects: { aspect: string; label: SentimentLabel; evidence: string | null }[];
}
export type SentimentEngine = "bert" | "vader";
export interface BertResult {
  label: SentimentLabel; confidence: number; probabilities: Record<SentimentLabel, number>; star_probabilities: number[];
  predicted_stars: number | null; expected_stars: number | null; truncated: boolean | null; model_id: string; model_revision: string | null;
}
export interface ReviewPage extends Page<ReviewItem> { engine: SentimentEngine }

export interface SentimentInfo {
  restaurant_id: number;
  available: boolean;
  analysed_reviews: number;
  message?: string;
  distribution?: Record<SentimentLabel, number>;
  share?: Record<SentimentLabel, number>;
  mean_compound?: number;
  mean_confidence?: number | null;
  engine?: EngineInfo;
  comparison?: { other_engine: SentimentEngine; other_distribution: Record<SentimentLabel, number> | null; reviews_with_both: number; agreement: number | null; note: string };
  histogram?: { range: string; count: number }[];
  note?: string;
  star_rating?: number | null;
  themes?: { positive: { term: string; count: number }[]; negative: { term: string; count: number }[]; basis: { positive_reviews: number; negative_reviews: number } };
}

export interface AspectStat {
  aspect: string; label: string; mentions: number; positive: number; negative: number; neutral: number;
  score: number | null; positive_share: number | null; negative_share: number | null;
  sufficient_evidence: boolean; min_mentions_required: number;
}
export interface AspectInfo {
  restaurant_id: number;
  aspects: AspectStat[];
  summary: { text: string | null; reason: string | null; basis_reviews: number; praised: string[]; criticized: string[] };
  analysed_reviews: number;
  min_mentions_required: number;
}

export interface LiveReviews {
  configured: boolean; stored: boolean; reviews: { rating: number | null; text: string; relative_time?: string; author?: string; author_url?: string; sentiment: { label: SentimentLabel } | null }[];
  message?: string; attribution?: string; google_rating?: number; google_rating_count?: number; google_maps_uri?: string;
}

export interface PopularResponse { label: string; trending_available: boolean; basis_note: string; dated_reviews: number; time_trend: { month: string; reviews: number }[]; items: Restaurant[] }
export interface GemsResponse {
  criteria: { min_analysed_reviews: number; min_positive_confidence_bound: number; max_visibility_percentile: number; min_adjusted_rating: number };
  status_counts: Record<string, number>; insufficient_evidence_count: number; items: GemItem[];
}
export interface RunInfo { id: number; source: string; status: string; started_at: string; finished_at: string | null; new: number; found: number; flagged: number; errors: string[] }
export interface NewResponse { baseline_established: boolean; baseline_at: string | null; refresh_running: boolean; last_run: RunInfo | null; note: string; items: Restaurant[] }

export interface CompareItem extends Restaurant {
  sentiment: { n: number; positive: number; negative: number; neutral: number; mean_compound: number; distribution_share: Record<SentimentLabel, number> } | null;
  aspects: Record<string, AspectStat>;
  ranking_explanation: string[];
}

export interface Overview {
  empty: boolean;
  restaurants: { total: number; by_source: Record<string, number>; with_rating: number; with_analysed_reviews: number; with_min_aspect_evidence: number; needing_recheck: number };
  reviews: { analysed: number; by_source: Record<string, number>; by_match_status: Record<string, number>; excluded_from_analytics: number; dated_reviews: number; mean_per_restaurant: number };
  sentiment_distribution: Record<SentimentLabel, number>;
  gem_status_counts: Record<string, number>;
  last_import: { filename: string; status: string; finished_at: string | null; valid_reviews_imported: number | null } | null;
  last_discovery: { source: string; status: string; finished_at: string | null; found: number; new: number; is_baseline: boolean } | null;
  data_notes: string[];
}

export type HotspotMetric = "density" | "reviews" | "popularity";
export interface Hotspots { metric: HotspotMetric; description: string; n_points: number; max_weight: number; points: [number, number, number][] }
export interface CuisineStats { distribution: { cuisine: string; value: string; restaurants: number }[]; popularity: { cuisine: string; mean_popularity: number; rated_restaurants: number }[]; unspecified_cuisine: number; min_restaurants_for_popularity: number }
export interface HoodStats { items: { neighborhood: string; label: string; restaurants: number; analysed_reviews: number; rated_restaurants: number; mean_popularity: number | null }[] }
export interface Keywords { overall: { term: string; count: number }[]; distinctive: { positive: { term: string; count: number }[]; negative: { term: string; count: number }[] }; basis: { reviews: number; positive: number; negative: number } }
export interface Suggestion { type: "restaurant" | "neighborhood" | "cuisine"; label: string; value: string; restaurant_id?: number; neighborhood_label?: string }
export interface EvaluationResults { available: boolean; message?: string; [k: string]: unknown }

export interface ModelCard { id: string; architecture: string; output: string; languages: string[]; licence: string; card_url: string; mapping: string; limitations: string[]; authors_reported_accuracy_note: string }
export interface EngineInfo {
  active: SentimentEngine; active_label: string; requested: string; reason: string;
  coverage: { matched_reviews: number; vader: number; bert: number; bert_share: number };
  job: { running: boolean; last: { status: string; reason: string | null; reviews_analysed: number; truncated_reviews: number } | null };
  bert: { model: ModelCard; model_id_configured: string; revision: string | null; packages_installed: boolean; unavailable_reason: string | null; max_tokens: number; predictions_stored: number; run_in_this_database: boolean };
  vader: { model: string; label: string; predictions_stored: number };
}
export interface Filters {
  q?: string; neighborhood?: string; cuisine?: string; min_rating?: number; price_min?: number; price_max?: number;
  sentiment?: SentimentLabel; aspect?: string; min_reviews?: number;
}
export interface GemEvidence { analysed_reviews: number; positive_reviews: number; positive_share: number; positive_lower_bound: number; adjusted_rating: number | null; ratings_on_record: number | null; visibility_percentile: number | null; praised_aspects: string[] }
export interface GemItem extends Restaurant { evidence: GemEvidence; explanation: string | null }
export interface AspectInsight { aspect: string; label: string; mentions: number; positive: number; neutral: number; negative: number; positive_share: number | null; negative_share: number | null; net_score: number | null; review_coverage: number | null; restaurants_with_mentions: number; restaurants_with_evidence: number; min_mentions_required: number }
export interface HoodInsight { neighborhood: string; label: string; selected: boolean; restaurants: number; restaurants_with_reviews: number; reviews: number; positive: number; neutral: number; negative: number; positive_share: number | null; negative_share: number | null; mean_popularity: number | null }
export interface CuisineInsight { cuisine: string; value: string; selected: boolean; restaurants: number; restaurants_with_reviews: number; reviews: number; positive_share: number | null; negative_share: number | null }
export interface ImportReport {
  filename: string; status: string; finished_at: string | null; rows_read: number | null; duplicate_listing_rows_removed: number | null; rows_in_focus_areas: number | null; rows_outside_focus_areas: number | null;
  listings_matched: number | null; listings_needs_review: number | null; listings_ambiguous: number | null; listings_without_osm_record: number | null;
  review_entries_parsed: number | null; malformed_review_entries: number | null; duplicate_reviews_skipped: number | null; reviews_unmatched_no_osm_record: number | null;
  valid_reviews_imported: number | null; restaurants_with_verified_reviews: number | null; dataset_note: string | null;
}
export interface PipelineSummary {
  restaurants_discovered: number; restaurants_total: number; restaurants_with_matched_reviews: number; reviews_stored: number; reviews_matched: number;
  reviews_by_match_status: Record<string, number>; reviews_unresolved_stored: number; reviews_analysed: number; dated_reviews: number;
  engine: EngineInfo; import: ImportReport | null;
}
export interface Insights {
  filters_applied: Record<string, string | number>;
  engine: EngineInfo;
  scope: { restaurants: number; restaurants_with_reviews: number; reviews_analysed: number; restaurants_in_database: number };
  sentiment: { n: number; positive: number; neutral: number; negative: number; positive_share: number | null; neutral_share: number | null; negative_share: number | null };
  engine_comparison: { other_engine: SentimentEngine; reviews_with_both: number; agreement: number | null; matrix: Record<string, Record<string, number>>; note?: string } | null;
  aspects: AspectInsight[];
  aspect_method: string;
  neighborhoods: HoodInsight[];
  cuisines: CuisineInsight[];
  hidden_gems: { items: GemItem[]; status_counts: Record<string, number>; criteria: GemsResponse["criteria"] };
  time_trend: { available: boolean; dated_reviews: number; months: number; reason?: string; series?: { month: string; reviews: number; positive_share: number }[] };
  pipeline: PipelineSummary;
}
