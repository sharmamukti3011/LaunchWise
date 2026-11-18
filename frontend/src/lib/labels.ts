import type { OptionScore, Source } from "../api/demo";

const SOURCE_LABELS: Record<Source, string> = {
  user_provided: "you provided",
  derived: "calculated from your inputs",
  assumption: "assumption",
  estimate: "estimate (uses an assumption)",
};

export function sourceLabel(source: Source): string {
  return SOURCE_LABELS[source];
}

const RUPEES = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Display only: the backend does all the arithmetic. */
export function formatRupees(amount: string): string {
  const n = Number(amount);
  return amount.trim() !== "" && Number.isFinite(n) ? RUPEES.format(n) : "—";
}

export function statusOf(score: Pick<OptionScore, "option_id" | "viable" | "viability_issues">, recommendedId: string | null): string {
  if (score.option_id === recommendedId) return "Recommended";
  if (score.viable) return "Viable";
  return `Not viable: ${score.viability_issues.join(", ")}`;
}
