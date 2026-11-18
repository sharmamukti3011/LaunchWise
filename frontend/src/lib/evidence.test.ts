import { describe, expect, it } from "vitest";
import type { Opportunity } from "../api/demo";
import { isPlaceholder, safeHttpUrl } from "./evidence";

const entry: Pick<Opportunity, "id" | "verification_status" | "label"> = {
  id: "X-1",
  verification_status: "verified",
  label: "ok",
};

describe("isPlaceholder", () => {
  it("flags TODO-VERIFY ids, unverified samples and TODO(verify) labels", () => {
    expect(isPlaceholder({ ...entry, id: "TODO-VERIFY-PUNE-001" })).toBe(true);
    expect(isPlaceholder({ ...entry, verification_status: "unverified_sample" })).toBe(true);
    expect(isPlaceholder({ ...entry, label: "TODO(verify) placeholder" })).toBe(true);
  });
  it("does not flag a verified entry", () => {
    expect(isPlaceholder(entry)).toBe(false);
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
