import { describe, expect, it } from "vitest";
import { formatRupees, sourceLabel, statusOf } from "./labels";

describe("sourceLabel", () => {
  it("shows derived figures as calculated from your inputs", () => {
    expect(sourceLabel("derived")).toBe("calculated from your inputs");
  });
  it("keeps the other tags distinct and readable", () => {
    expect(sourceLabel("user_provided")).toBe("you provided");
    expect(sourceLabel("assumption")).toBe("assumption");
    expect(sourceLabel("estimate")).toBe("estimate (uses an assumption)");
  });
});

describe("formatRupees", () => {
  it("shows whole rupees without .00, in the Indian grouping", () => {
    expect(formatRupees("10000.00")).toBe("₹10,000");
    expect(formatRupees("125000")).toBe("₹1,25,000");
    expect(formatRupees("0.00")).toBe("₹0");
    expect(formatRupees("1234567")).toBe("₹12,34,567");
  });
  it("keeps paise only when the value is not whole", () => {
    expect(formatRupees("899.50")).toBe("₹899.50");
    expect(formatRupees("0.5")).toBe("₹0.50");
    expect(formatRupees("1000.05")).toBe("₹1,000.05");
  });
  it("never uses a dollar sign", () => {
    expect(formatRupees("500")).not.toContain("$");
  });
  it("never shows NaN for odd input", () => {
    expect(formatRupees("oops")).toBe("—");
  });
});

describe("statusOf", () => {
  const base = { viable: true, viability_issues: [] as string[] };
  it("marks the recommended option", () => {
    expect(statusOf({ ...base, option_id: "a" }, "a")).toBe("Recommended");
  });
  it("marks other viable options and non-viable ones", () => {
    expect(statusOf({ ...base, option_id: "b" }, "a")).toBe("Viable");
    expect(statusOf({ viable: false, viability_issues: ["over budget"], option_id: "c" }, "a")).toBe(
      "Not viable: over budget",
    );
  });
});
