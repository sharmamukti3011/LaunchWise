import type { Analysis, Explanation } from "./demo";

/** Exactly what POST /api/analyze takes. Money travels as strings, never as floats. */
export interface AnalyzeBody {
  profile: {
    budget: string;
    units_per_day: number;
    days_per_week: number;
    /** Left out when blank, so the server assumes (and flags) a figure. */
    hours_per_week?: { value: number; source: "user_provided" };
    skills: string[];
    equipment: string[];
    location: string;
  };
  category: string;
  options: BodyOption[];
  /** Ask LaunchWise to add up to two suggested alternatives where it has market data. */
  suggest_alternatives?: boolean;
}

export interface BodyOption {
  id: string;
  title: string;
  is_original: boolean;
  price: string;
  variable_cost_per_unit: string;
  fixed_startup_costs: string;
  minutes_per_unit?: { value: number; source: "user_provided" };
  opportunity_id?: string;
}

export interface ServerFieldError {
  field: string;
  message: string;
}

export type FailureKind = "invalid" | "rate_limited" | "server" | "network";

// Fixed text only. Nothing the server says is ever shown.
export const FAILURE_TEXT: Record<FailureKind, string> = {
  invalid: "Please check the highlighted fields and try again.",
  rate_limited: "Too many requests. Please try again in a moment.",
  server: "Something went wrong on our side. Please try again shortly.",
  network: "Could not reach the server. Check your connection and try again.",
};

export class AnalyzeFailure extends Error {
  readonly kind: FailureKind;
  /** Which fields the server rejected (names only; its wording is never used). */
  readonly fields: ServerFieldError[];
  constructor(kind: FailureKind, fields: ServerFieldError[] = []) {
    super(FAILURE_TEXT[kind]);
    this.name = "AnalyzeFailure";
    this.kind = kind;
    this.fields = fields;
  }
}

function fieldErrors(body: unknown): ServerFieldError[] {
  const errors = (body as { errors?: unknown } | null)?.errors;
  if (!Array.isArray(errors)) return [];
  return errors
    .filter((e): e is ServerFieldError => typeof (e as ServerFieldError)?.field === "string")
    .map((e) => ({ field: e.field, message: "" }));
}

async function post(url: string, body: AnalyzeBody, signal?: AbortSignal): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new AnalyzeFailure("network");
  }
  if (response.ok) return response;
  if (response.status === 422) {
    throw new AnalyzeFailure("invalid", fieldErrors(await response.json().catch(() => null)));
  }
  if (response.status === 413) throw new AnalyzeFailure("invalid");
  if (response.status === 429) throw new AnalyzeFailure("rate_limited");
  throw new AnalyzeFailure("server");
}

export async function analyzeOwn(body: AnalyzeBody, signal?: AbortSignal): Promise<Analysis> {
  return (await (await post("/api/analyze", body, signal)).json()) as Analysis;
}

export async function explainOwn(body: AnalyzeBody, signal?: AbortSignal): Promise<Explanation> {
  const result = (await (await post("/api/analyze/explain", body, signal)).json()) as {
    explanation: Explanation;
  };
  return result.explanation;
}

export interface EvidenceChoice {
  id: string;
  title: string;
  source_name: string;
  direction: "supports" | "against";
  location: string;
  category: string;
}

/** The dataset entries an alternative can be based on. A failure just means no choices. */
export async function fetchEvidenceChoices(signal?: AbortSignal): Promise<EvidenceChoice[]> {
  try {
    const response = await fetch("/api/market-evidence", { signal });
    if (!response.ok) return [];
    return ((await response.json()) as { evidence: EvidenceChoice[] }).evidence;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return [];
  }
}
