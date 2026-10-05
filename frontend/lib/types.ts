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

export type DecisionKind = "lending" | "cross_sell" | "retention" | "none";

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
}

export interface Dashboard {
  flagged_count: number;
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
    suggested_pct: number;
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
