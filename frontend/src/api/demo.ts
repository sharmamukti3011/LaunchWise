// Types mirror the backend's JSON. Decimals arrive as strings and are only ever displayed.

export type Source = "user_provided" | "derived" | "assumption" | "estimate" | "from_source";

export interface Sourced<T> {
  value: T;
  source: Source;
}

export interface Feasibility {
  /** The figures the engine was given. `price` is what the offer on a starter page starts from. */
  inputs: { price: Sourced<string> };
  startup_cost: Sourced<string>;
  contribution_margin: Sourced<string>;
  contribution_margin_pct: Sourced<string | null>;
  weekly_capacity: Sourced<number>;
  max_weekly_revenue: Sourced<string>;
  break_even_units: Sourced<number | null>;
  break_even: { medium: { weeks: Sourced<number | null> } };
  budget_check: {
    within_budget: boolean;
    working_capital: Sourced<string> | null;
    total_required: Sourced<string>;
    headroom: Sourced<string>;
    shortfall: Sourced<string>;
  };
}

export interface DimensionScore {
  dimension: "margin" | "budget" | "capacity" | "skill_equipment" | "market_signal";
  score: number;
  reason: string;
}

export interface OptionScore {
  option_id: string;
  title: string;
  is_original: boolean;
  /** True for an option LaunchWise added from market data, never the owner's own. */
  is_suggested?: boolean;
  scores: DimensionScore[];
  total: string;
  viable: boolean;
  viability_issues: string[];
}

export interface Caveat {
  kind: string;
  message: string;
  items: string[];
}

export interface Opportunity {
  id: string;
  title: string;
  location: string;
  category: string;
  signal_summary: string;
  evidence: string;
  source_name: string;
  source_url: string;
  verification_status: "verified" | "single_source" | "unverified_sample";
  signal_strength: "low" | "medium" | "high";
  direction: "supports" | "against";
  label: string;
}

export interface SuggestedFigure {
  field: "price" | "variable_cost" | "startup_cost" | "minutes_per_unit";
  label: string;
  value: string;
  basis: "from_source" | "assumption";
  quote: string | null;
}

export interface SuggestionInfo {
  evidence_id: string;
  source_name: string;
  figures: SuggestedFigure[];
}

export interface OptionAnalysis {
  option_id: string;
  title: string;
  is_original: boolean;
  opportunity_id: string | null;
  feasibility: Feasibility;
  score: OptionScore;
  is_suggested?: boolean;
  suggestion?: SuggestionInfo | null;
}

export interface Step {
  index: number;
  tool:
    | "validate_constraints"
    | "query_market_opportunities"
    | "suggest_alternatives"
    | "run_feasibility"
    | "compare_strategies";
  title: string;
  status: "ok";
}

export interface Analysis {
  analyzed_on: string;
  market_coverage: "covered" | "none";
  market_message: string;
  category: string;
  food_business: boolean;
  options: OptionAnalysis[];
  skipped_option_ids: string[];
  ranking: {
    ranked: OptionScore[];
    recommended_id: string | null;
    keep_original: boolean;
    caveats: Caveat[];
  };
  evidence: Opportunity[];
  steps: Step[];
}

export interface DemoScenario {
  id: string;
  title: string;
  summary: string;
  simulated: true;
  notice: string;
}

export interface DemoRun {
  scenario: DemoScenario;
  simulated: true;
  notice: string;
  analysis: Analysis;
}

export interface Explanation {
  summary: string;
  source: "claude" | "template";
  fallback_reason: "not_configured" | "budget" | "unavailable" | "invalid" | null;
}

export interface DemoExplain {
  scenario_id: string;
  simulated: true;
  notice: string;
  explanation: Explanation;
}

export type DemoErrorKind = "rate_limited" | "not_found" | "server" | "network";

/** A failure with a message safe to show. Server text is never passed through. */
export class DemoError extends Error {
  readonly kind: DemoErrorKind;
  constructor(kind: DemoErrorKind, message: string) {
    super(message);
    this.name = "DemoError";
    this.kind = kind;
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

async function request(url: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new DemoError("network", "Could not reach the server. Check your connection and try again.");
  }
  if (response.ok) return response;
  if (response.status === 429) {
    const wait = Number(response.headers.get("Retry-After"));
    const when = Number.isFinite(wait) && wait > 0 ? `${wait} seconds` : "a moment";
    throw new DemoError("rate_limited", `Too many requests. Please try again in ${when}.`);
  }
  if (response.status === 404) {
    throw new DemoError("not_found", "That demo scenario is no longer available. Reload the page.");
  }
  throw new DemoError("server", "Something went wrong on our side. Please try again shortly.");
}

export async function fetchScenarios(signal?: AbortSignal): Promise<DemoScenario[]> {
  const response = await request("/api/demo/scenarios", { signal });
  return ((await response.json()) as { scenarios: DemoScenario[] }).scenarios;
}

export async function runScenario(id: string, signal?: AbortSignal): Promise<DemoRun> {
  const response = await request(`/api/demo/run/${encodeURIComponent(id)}`, {
    method: "POST",
    signal,
  });
  return (await response.json()) as DemoRun;
}

export async function explainScenario(id: string, signal?: AbortSignal): Promise<DemoExplain> {
  const response = await request(`/api/demo/explain/${encodeURIComponent(id)}`, {
    method: "POST",
    signal,
  });
  return (await response.json()) as DemoExplain;
}
