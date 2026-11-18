import { describe, expect, it } from "vitest";
import type { Opportunity } from "../api/demo";
import { AGAINST_BADGE, EVIDENCE_LABELS, evidenceKind, isAgainst, safeHttpUrl } from "./evidence";

const entry: Pick<Opportunity, "id" | "verification_status" | "label" | "direction"> = {
  id: "X-1",
  verification_status: "verified",
  label: "ok",
  direction: "supports",
};

describe("evidenceKind", () => {
  it("calls only TODO-VERIFY entries placeholders", () => {
    expect(evidenceKind({ ...entry, id: "TODO-VERIFY-PUNE-001" })).toBe("placeholder");
    expect(evidenceKind({ ...entry, label: "TODO(verify) placeholder" })).toBe("placeholder");
    // A placeholder stays a placeholder whatever its status says.
    expect(evidenceKind({ ...entry, id: "TODO-VERIFY-X", verification_status: "verified" })).toBe(
      "placeholder",
    );
  });
  it("shows a verified entry as verified and a real unverified entry as not yet verified", () => {
    expect(evidenceKind(entry)).toBe("verified");
    expect(evidenceKind({ ...entry, verification_status: "unverified_sample" })).toBe("unverified");
    expect(evidenceKind({ ...entry, verification_status: "single_source" })).toBe("single_source");
  });
});

describe("EVIDENCE_LABELS", () => {
  it("uses the agreed wording, and 'Placeholder data' only for placeholders", () => {
    expect(EVIDENCE_LABELS.verified).toBe("Verified source");
    expect(EVIDENCE_LABELS.unverified).toBe("Source cited, not yet verified");
    expect(EVIDENCE_LABELS.placeholder).toMatch(/^Placeholder data/);
    for (const kind of ["verified", "single_source", "unverified"] as const) {
      expect(EVIDENCE_LABELS[kind]).not.toMatch(/placeholder/i);
    }
  });
});

describe("safeHttpUrl", () => {
  it("allows http and https only", () => {
    expect(safeHttpUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("data:text/html,x")).toBeNull();
    expect(safeHttpUrl("not a url")).toBeNull();
  });
  it("never links the reserved .invalid placeholder host", () => {
    expect(safeHttpUrl("https://example.invalid/todo-verify-001")).toBeNull();
  });
});

describe("isAgainst", () => {
  it("is true only for evidence that argues against its option", () => {
    expect(isAgainst({ direction: "against" })).toBe(true);
    expect(isAgainst({ direction: "supports" })).toBe(false);
    expect(AGAINST_BADGE).toBe("Evidence against this option");
  });
});
