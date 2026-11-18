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

const RUPEES_WHOLE = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const RUPEES_PAISE = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Display only: the backend does all the arithmetic. Paise show only when not a whole rupee. */
export function formatRupees(amount: string): string {
  const n = Number(amount);
  if (amount.trim() === "" || !Number.isFinite(n)) return "—";
  const paise = amount.split(".")[1] ?? "";
  return /^0*$/.test(paise) ? RUPEES_WHOLE.format(n) : RUPEES_PAISE.format(n);
}

export function statusOf(score: Pick<OptionScore, "option_id" | "viable" | "viability_issues">, recommendedId: string | null): string {
  if (score.option_id === recommendedId) return "Recommended";
  if (score.viable) return "Viable";
  return `Not viable: ${score.viability_issues.join(", ")}`;
}
