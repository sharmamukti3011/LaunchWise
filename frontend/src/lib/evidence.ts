import type { Opportunity } from "../api/demo";

/** True for the TODO(verify) sample entries that ship until real, cited data replaces them. */
export function isPlaceholder(
  entry: Pick<Opportunity, "id" | "verification_status" | "label">,
): boolean {
  return (
    entry.verification_status === "unverified_sample" ||
    /^TODO-VERIFY/i.test(entry.id) ||
    /TODO\(verify\)/i.test(entry.label)
  );
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
