export type DraftStatus = "from_description" | "not_mentioned";

export interface DraftFieldBody {
  value: string;
  status: DraftStatus;
}

/** What /api/intake returns: a value and a status for every field of the form. */
export interface IntakeDraftBody {
  budget: DraftFieldBody;
  units_per_day: DraftFieldBody;
  days_per_week: DraftFieldBody;
  hours_per_week: DraftFieldBody;
  skills: DraftFieldBody;
  equipment: DraftFieldBody;
  location: DraftFieldBody;
  category: DraftFieldBody;
  original_title: DraftFieldBody;
  original_price: DraftFieldBody;
  original_cost: DraftFieldBody;
  original_startup: DraftFieldBody;
  original_minutes: DraftFieldBody;
  alt_title: DraftFieldBody;
  alt_price: DraftFieldBody;
  alt_cost: DraftFieldBody;
  alt_startup: DraftFieldBody;
  alt_minutes: DraftFieldBody;
  alternative_mentioned: boolean;
}

// Fixed text only. Nothing the server says is ever shown.
export const INTAKE_TEXT = {
  drafted: "We filled in what you described. Check every field before you run the analysis.",
  fallback: "We could not turn that into a draft. Please fill in the form yourself.",
  budget: "The description helper has reached its limit for now. Please fill in the form yourself.",
  unavailable: "Describing your idea is not available right now. Please fill in the form below.",
  rate_limited: "Too many requests. Please try again in a moment.",
  invalid: "Please describe your idea in 1 to 1,500 characters.",
  server: "Something went wrong on our side. Please try again shortly.",
  network: "Could not reach the server. Check your connection and try again.",
} as const;

export type IntakeFailureKind = "unavailable" | "rate_limited" | "invalid" | "server" | "network";

export class IntakeFailure extends Error {
  readonly kind: IntakeFailureKind;
  constructor(kind: IntakeFailureKind) {
    super(INTAKE_TEXT[kind]);
    this.name = "IntakeFailure";
    this.kind = kind;
  }
}

export type IntakeResult =
  | { kind: "drafted"; draft: IntakeDraftBody; message: string }
  | { kind: "fallback"; message: string };

export async function draftFromText(text: string, signal?: AbortSignal): Promise<IntakeResult> {
  let response: Response;
  try {
    response = await fetch("/api/intake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new IntakeFailure("network");
  }
  if (response.status === 503) throw new IntakeFailure("unavailable");
  if (response.status === 429) throw new IntakeFailure("rate_limited");
  if (response.status === 422 || response.status === 413) throw new IntakeFailure("invalid");
  if (!response.ok) throw new IntakeFailure("server");
  const body = (await response.json()) as {
    status: string;
    message: string;
    draft: IntakeDraftBody | null;
  };
  if (body.status === "drafted" && body.draft) {
    return { kind: "drafted", draft: body.draft, message: INTAKE_TEXT.drafted };
  }
  // The server's message is fixed, but the screen uses its own copy of the two known texts.
  return {
    kind: "fallback",
    message: body.message === INTAKE_TEXT.budget ? INTAKE_TEXT.budget : INTAKE_TEXT.fallback,
  };
}
