import { describe, expect, it } from "vitest";
import { keyFigures } from "./figures";
import type { Feasibility } from "../api/demo";

const s = <T,>(value: T, source: string) => ({ value, source });

function feasibility(overrides: Partial<Feasibility> = {}): Feasibility {
  return {
    startup_cost: s("4000.00", "user_provided"),
    contribution_margin: s("900.00", "derived"),
    contribution_margin_pct: s("64.29", "derived"),
    weekly_capacity: s(6, "derived"),
    max_weekly_revenue: s("8400.00", "derived"),
    break_even_units: s(5, "derived"),
    break_even: { medium: { weeks: s(2, "estimate") } },
    budget_check: {
      within_budget: true,
      working_capital: s("3000.00", "assumption"),
      total_required: s("7000.00", "assumption"),
      headroom: s("3000.00", "assumption"),
      shortfall: s("0.00", "assumption"),
    },
    ...overrides,
  } as Feasibility;
}

describe("keyFigures", () => {
  it("lists each figure with the source tag the engine gave it", () => {
    const rows = keyFigures(feasibility());
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r]));
    expect(byLabel["Startup cost"]).toMatchObject({ value: "₹4,000.00", source: "user_provided" });
    expect(byLabel["Margin per unit"]).toMatchObject({ value: "₹900.00", source: "derived" });
    expect(byLabel["Margin"]).toMatchObject({ value: "64.29%", source: "derived" });
    expect(byLabel["Weekly capacity"]).toMatchObject({ value: "6 units", source: "derived" });
    expect(byLabel["Break-even sales"]).toMatchObject({ value: "5 units", source: "derived" });
    expect(byLabel["Weeks to break even (50% demand)"]).toMatchObject({
      value: "2 weeks",
      source: "estimate",
    });
    expect(byLabel["Working capital reserve"]).toMatchObject({ source: "assumption" });
  });

  it("omits working capital when not requested and shows 'never' when break-even is unreachable", () => {
    const rows = keyFigures(
      feasibility({
        break_even_units: s(null, "derived"),
        break_even: { medium: { weeks: s(null, "estimate") } },
        budget_check: {
          within_budget: false,
          working_capital: null,
          total_required: s("9000.00", "derived"),
          headroom: s("0.00", "derived"),
          shortfall: s("500.00", "derived"),
        },
      } as Partial<Feasibility>),
    );
    const labels = rows.map((r) => r.label);
    expect(labels).not.toContain("Working capital reserve");
    expect(rows.find((r) => r.label === "Break-even sales")?.value).toBe("not reached");
    expect(rows.find((r) => r.label === "Short of budget by")?.value).toBe("₹500.00");
  });
});
