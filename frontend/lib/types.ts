export type View = "dashboard" | "profile" | "suggestions" | "copilot";
export type CopilotMode = "general" | "merchant";
export type ChatMode = "llm" | "data" | "guard";

export interface DataStatus {
  loaded: boolean;
  as_of_date?: string;
  clients: number;
  flagged: number;
  synthetic: boolean;
  disclaimer: string;
  llm_configured?: boolean;
  llm_model?: string | null;
}

export type DecisionKind = "lending" | "cross_sell" | "retention" | "engage" | "none";

/** The suggestion engine's decision for a client (the AI's, or the rule fallback when source is "rules"). */
export interface ClientDecision {
  kind: DecisionKind;
  product: string | null;
  amount_aed: number | null;
  next_action: string | null;
  priority: number | null;
  source: "llm" | "rules";
  model: string | null;
}

/** An RM's rating of the suggestion currently shown for a client. */
export interface Feedback { verdict: "useful" | "not_useful"; reason: string | null }

export interface RatingSplit { useful: number; not_useful: number; rated: number; useful_share: number | null }

export interface FeedbackSummary {
  overall: RatingSplit;
  by_source: { llm: RatingSplit; rules: RatingSplit };
  by_product: Record<string, RatingSplit>;
  not_useful_reasons: Record<string, number>;
}

/** The data behind a client's current suggestion ("Why this?"). Everything but the explanation text is computed from the client's data. */
export interface Evidence {
  merchant_id: string;
  name: string;
  as_of_date: string;
  suggestion: null | {
    kind: DecisionKind; kind_label: string; product: string | null; amount_aed: number | null; source: "llm" | "rules"; model: string | null;
    priority: number | null; why: string; next_action: string | null; note: string | null; how_decided: string;
  };
  message?: string;
  explanation_check?: { unverified: string[]; summary: string };
  facts?: { label: string; value: string; key: boolean }[];
  signals?: { text: string; points: number; kind: string }[];
  checks?: { text: string; ok: boolean; kind: "check" | "caution" }[];
  track_record?: { same_suggestion: RatingSplit; same_source: RatingSplit };
  feedback?: Feedback | null;
}

/** A merchant segment the RM watches. Value is an estimate: average monthly turnover times the current merchant rate. */
export type SegmentCode = "churn_risk" | "top_performer" | "dormant";

export interface SegmentSummary { label: string; clients: number; monthly_revenue_aed: number; revenue_change_vs_prior_30d_aed: number }

export interface ClientValue {
  monthly_revenue_aed: number;
  value_tier: "High" | "Medium" | "Low";
  revenue_change_vs_prior_30d_aed: number;
  turnover_rank: number;
  portfolio_share_pct: number;
}

export interface DashboardClient {
  rank: number;
  merchant_id: string;
  name: string;
  city: string;
  industry: string;
  reason: string;
  score: number;
  flagged: boolean;
  risk: string;
  is_dormant_now: boolean;
  decision: ClientDecision | null;
  feedback?: Feedback | null;
  segments?: SegmentCode[];
  value?: ClientValue;
}

/** One merchant on the dashboard's "Act now" list (step 1: the high-value churn risks). Rules choose and rank it; `action` is the AI
 *  engine's retention decision where it made one, otherwise the rule-based wording. */
export interface ActNowItem {
  rank: number;
  merchant_id: string;
  name: string;
  city: string;
  industry: string;
  value_tier: "High" | "Medium" | "Low";
  monthly_revenue_aed: number;               // estimated: average monthly turnover times the current rate
  revenue_gap_vs_baseline_aed: number;       // estimated monthly revenue lost against the merchant's own earlier average
  revenue_change_vs_prior_30d_aed: number;
  volume_change_vs_prior_30d_pct: number | null;
  volume_vs_baseline_pct: number | null;
  baseline_months: number;
  dormant_days: number;
  reasons: string[];
  action: { kind: DecisionKind; why: string; next_action: string | null; source: "llm" | "rules"; model: string | null };
}

export interface ActNowData {
  segment: string;
  label: string;
  definition: string;
  at_risk: number;
  high_value_at_risk: number;
  items: ActNowItem[];
}

/** One merchant on the dashboard's cross-sell list (step 2): it does not yet hold a product the bank can offer it. A loan it also qualifies for is a second line. */
export interface CrossSellItem {
  rank: number;
  merchant_id: string;
  name: string;
  city: string;
  industry: string;
  value_tier: "High" | "Medium" | "Low";
  reasons: string[];                       // the product gap first, then any growth figures
  growth_reasons: string[];
  offer: { kind: string; product: string; why: string; next_action: string | null; source: "llm" | "rules"; model: string | null };
  also_lending: { product: string; amount_aed: number | null } | null;
}

export interface CrossSellData {
  segment: string;
  label: string;
  definition: string;
  candidates: number;                      // merchants that do not yet hold a product we can offer
  growth_ready: number;                    // of those, how many are also growing or near their POS limit
  also_lending: number;                    // of those, how many also qualify for a working-capital facility
  items: CrossSellItem[];
}

/** One merchant on the dashboard's top performers list (step 3): among the merchants driving the bulk of the portfolio's card volume. */
export interface TopPerformerItem {
  rank: number;
  merchant_id: string;
  name: string;
  city: string;
  industry: string;
  value_tier: "High" | "Medium" | "Low";
  volume_rank: number;
  volume_share_pct: number;
  city_volume_share_pct: number;
  volume_change_vs_prior_30d_pct: number | null;
  churn_risk: boolean;
  reasons: string[];
  action: { kind: DecisionKind; why: string; next_action: string | null; source: "llm" | "rules"; model: string | null };
}

export interface TopPerformersData {
  segment: string;
  label: string;
  definition: string;
  top_performers: number;          // how many merchants are top performers
  share_of_volume_pct: number;     // their combined share of the portfolio's card volume
  items: TopPerformerItem[];
}

export interface DormantItem {
  rank: number; merchant_id: string; name: string; city: string; industry: string; value_tier: string;
  dormant_days: number; earlier_monthly_volume_aed: number; volume_change_vs_prior_30d_pct: number | null;
  reasons: string[];
  action: { kind: DecisionKind; why: string; next_action: string | null; source: "llm" | "rules"; model: string | null };
}

export interface DormantData {
  segment: string; label: string; definition: string;
  inactive: number;                // merchants with inactive terminals now
  items: DormantItem[];
}

export interface Dashboard {
  flagged_count: number;
  segment_summary?: Record<SegmentCode, SegmentSummary>;
  decisions_source: "llm" | "rules";
  clients: DashboardClient[];
}

export interface DirectoryClient {
  merchant_id: string;
  name: string;
  industry: string;
  city: string;
  rank: number;
}

export interface DirectoryFilters {
  balanceMin: string;
  balanceMax: string;
  segment: string;
  cardType: string;
  product: string;
}

export interface FilterOption { value: string; count: number }

export interface FilterOptions {
  balance: { min: number; max: number };
  segment: FilterOption[];
  card_type: FilterOption[];
  product: FilterOption[];
}

export interface Suggestion {
  rank: number;
  merchant_id: string;
  name: string;
  industry: string;
  city: string;
  category: string;
  product: string;
  amount_aed: number | null;
  explanation: string;
  opportunity_label: string;
  next_action: string | null;
  priority: number | null;
  source: "llm" | "rules";
  model: string | null;
  feedback?: Feedback | null;
}

export interface ClientDetail {
  merchant_id: string;
  name: string;
  city: string;
  industry: string;
  card_pos: {
    card_no: string;
    card_type: string;
    dominant_tier_t30: string | null;
    monthly_pos_limit_aed: number;
    daily_pos_limit_aed: number;
    volume_t30: number | null;
    txn_t30: number | null;
    num_pos_terminals: number;
    monthly_limit_utilisation: number | null;
  };
  profile: {
    balance_aed: number;
    risk_segment: string;
    segment: string;
    existing_products: string[];
    synthetic_credit_score: number;
  };
  rate: {
    available: boolean;
    tier: number;
    current_pct: number;
    /** The suggested rate as a range: the model's estimate plus or minus band_pp, rounded to 0.05. The exact figure is not sent. */
    suggested_low_pct: number;
    suggested_high_pct: number;
    band_pp: number;
    change_recommended: boolean;
    rationale: string;
  };
  volume_bars: { month: string; month_key: string; volume_aed: number; height_pct: number }[];
  card_mix: { type: string; pct: number; txns: number; volume_aed: number }[];
  behaviour: {
    is_dormant_now: boolean;
    dormant_streak_days: number;
    volume_change_t30_vs_p30: number | null;
  };
  priority: { rank: number; score: number; flagged: boolean; reason: string };
  recommendation: { category: string; title: string; why: string } | null;
  as_of_date: string;
}

export interface GuardrailInfo {
  stage: "input" | "output";
  rail: string | null;
  blocked: boolean;
  engine: string;
  violations: string[];
}

export interface ChatMsg {
  role: "user" | "bot";
  text: string;
  mode?: ChatMode;
  guardrail?: GuardrailInfo;
}
