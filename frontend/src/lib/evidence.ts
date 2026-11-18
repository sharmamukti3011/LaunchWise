import type { Opportunity } from "../api/demo";

export type EvidenceKind = "placeholder" | "verified" | "single_source" | "unverified";

export const EVIDENCE_LABELS: Record<EvidenceKind, string> = {
  placeholder: "Placeholder data: not a real market finding. Do not rely on it.",
  verified: "Verified source",
  single_source: "Single source cited",
  unverified: "Source cited, not yet verified",
};

/**
 * "Placeholder" is only for the old TODO-VERIFY stand-ins. A real, cited entry is either
 * verified or "not yet verified": never a placeholder.
 */
export function evidenceKind(
  entry: Pick<Opportunity, "id" | "verification_status" | "label">,
): EvidenceKind {
  if (/^TODO-VERIFY/i.test(entry.id) || /TODO\(verify\)/i.test(entry.label)) return "placeholder";
  if (entry.verification_status === "verified") return "verified";
  if (entry.verification_status === "single_source") return "single_source";
  return "unverified";
}

export const AGAINST_BADGE = "Evidence against this option";

export function isAgainst(entry: Pick<Opportunity, "direction">): boolean {
  return entry.direction === "against";
}

/** Only real http(s) links are clickable. `.invalid` is reserved and never resolves. */
export function safeHttpUrl(raw: string): string | null {
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (url.hostname.endsWith(".invalid")) return null;
    return url.href;
  } catch {
    return null;
  }
}
