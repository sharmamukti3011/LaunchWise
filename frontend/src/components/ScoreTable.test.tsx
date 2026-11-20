import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Analysis, OptionAnalysis, OptionScore, Source, Sourced, SuggestionInfo } from "../api/demo";
import { ScoreTable } from "./ScoreTable";

const sourced = <T,>(value: T, source: Source): Sourced<T> => ({ value, source });

function feasibility(startupSource: Source = "user_provided"): OptionAnalysis["feasibility"] {
  return {
    inputs: { price: sourced("1200.00", "user_provided") },
    startup_cost: sourced("4000.00", startupSource),
    contribution_margin: sourced("700.00", "derived"),
    contribution_margin_pct: sourced("58.33", "derived"),
    weekly_capacity: sourced(6, "derived"),
    max_weekly_revenue: sourced("7200.00", "derived"),
    break_even_units: sourced(6, "derived"),
    break_even: { medium: { weeks: sourced(2, "estimate") } },
    budget_check: {
      within_budget: true,
      working_capital: sourced("3000.00", "assumption"),
      total_required: sourced("7000.00", "assumption"),
      headroom: sourced("3000.00", "assumption"),
      shortfall: sourced("0.00", "assumption"),
    },
  };
}

const SUGGESTION: SuggestionInfo = {
  evidence_id: "PUNE-001",
  source_name: "YourStory (HerStory)",
  figures: [
    { field: "price", label: "price", value: "1200", basis: "from_source", quote: "up to Rs 1,200 for occasion cakes" },
    { field: "variable_cost", label: "variable cost", value: "500", basis: "assumption", quote: null },
    { field: "startup_cost", label: "startup cost", value: "4000", basis: "assumption", quote: null },
    { field: "minutes_per_unit", label: "time per item", value: "100", basis: "assumption", quote: null },
  ],
};

function score(id: string, title: string, suggested: boolean, total: string): OptionScore {
  return {
    option_id: id,
    title,
    is_original: !suggested,
    is_suggested: suggested,
    scores: [{ dimension: "margin", score: 100, reason: "margin reason" }],
    total,
    viable: true,
    viability_issues: [],
  };
}

function analysis(): Analysis {
  const ranked = [score("suggested-pune-001", "Custom celebration cakes", true, "90.00"), score("original", "Everyday cakes", false, "48.50")];
  return {
    options: [
      { option_id: "suggested-pune-001", title: "Custom celebration cakes", is_original: false, opportunity_id: "PUNE-001", feasibility: feasibility("assumption"), score: ranked[0], is_suggested: true, suggestion: SUGGESTION },
      { option_id: "original", title: "Everyday cakes", is_original: true, opportunity_id: null, feasibility: feasibility(), score: ranked[1], is_suggested: false, suggestion: null },
    ],
    ranking: { ranked, recommended_id: "suggested-pune-001", keep_original: false, caveats: [] },
  } as unknown as Analysis;
}

describe("ScoreTable and suggestions", () => {
  const html = renderToStaticMarkup(<ScoreTable analysis={analysis()} onUseSuggestion={vi.fn()} />);

  it("badges a suggested row 'Suggested by LaunchWise' and no other row", () => {
    expect(html.match(/Suggested by LaunchWise/g)).toHaveLength(1);
    expect(html.indexOf("Suggested by LaunchWise")).toBeLessThan(html.indexOf("Everyday cakes"));
  });

  it("calls the budget column 'Budget fit' so it is not read as the amount", () => {
    expect(html).toContain(">Budget fit<");
    expect(html).not.toContain(">Budget<");
  });

  it("still marks the owner's own idea as theirs", () => {
    expect(html).toContain("(your idea)");
  });

  it("lists the suggested figures and says which are from the source and which are assumed", () => {
    expect(html).toContain("Suggested figures");
    expect(html).toContain("₹1,200");
    expect(html).toContain("from the cited source");
    expect(html).toContain("YourStory (HerStory)");
    expect((html.match(/>assumed</g) ?? []).length).toBe(3);
    expect(html).toContain("₹500");
    expect(html).toContain("100 minutes");
  });

  it("quotes the source for the figure it states", () => {
    expect(html).toContain("up to Rs 1,200 for occasion cakes");
  });

  it("does not call a suggestion's startup cost 'you provided'", () => {
    const panel = html.slice(html.indexOf("Custom celebration cakes", html.indexOf("Figures and reasons")));
    const suggestedPanel = panel.slice(0, panel.indexOf("Figures and reasons: Everyday cakes"));
    expect(suggestedPanel).not.toContain("you provided");
  });

  it("offers 'Use this as my alternative' for a suggestion only", () => {
    expect(html.match(/Use this as my alternative/g)).toHaveLength(1);
  });

  it("hides the button when there is nowhere to copy the suggestion to", () => {
    const plain = renderToStaticMarkup(<ScoreTable analysis={analysis()} />);
    expect(plain).not.toContain("Use this as my alternative");
    expect(plain).toContain("Suggested by LaunchWise");
  });

  it("says the option is not the owner's idea", () => {
    expect(html).toMatch(/not your (own )?idea/i);
  });

  it("escapes text from the analysis", () => {
    const a = analysis();
    a.options[0].suggestion!.source_name = "<img src=x onerror=alert(1)>";
    const out = renderToStaticMarkup(<ScoreTable analysis={a} onUseSuggestion={vi.fn()} />);
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img");
  });
});
