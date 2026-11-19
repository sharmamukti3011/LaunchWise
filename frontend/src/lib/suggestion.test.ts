import { describe, expect, it } from "vitest";
import type { SuggestionInfo } from "../api/demo";
import { applySuggestion } from "./suggestion";
import { EMPTY_FORM, setField } from "./ownIdea";

const SUGGESTION: SuggestionInfo = {
  evidence_id: "PUNE-001",
  source_name: "YourStory (HerStory)",
  figures: [
    { field: "price", label: "price", value: "1200", basis: "from_source", quote: "q" },
    { field: "variable_cost", label: "variable cost", value: "500", basis: "assumption", quote: null },
    { field: "startup_cost", label: "startup cost", value: "4000", basis: "assumption", quote: null },
    { field: "minutes_per_unit", label: "time per item", value: "100", basis: "assumption", quote: null },
  ],
};

describe("applySuggestion", () => {
  it("copies the suggestion into the alternative's fields, ready to edit", () => {
    const form = applySuggestion(EMPTY_FORM, "Custom celebration cakes", SUGGESTION);
    expect(form.alt).toEqual({
      title: "Custom celebration cakes",
      price: "1200",
      cost: "500",
      startup: "4000",
      minutes: "100",
      evidenceId: "PUNE-001", // linked to its entry, so it keeps that entry's market signal
    });
  });

  it("leaves the rest of the form, including the owner's own idea, untouched", () => {
    const typed = setField(setField(EMPTY_FORM, "budget", "10000"), "original.title", "Everyday cakes");
    const form = applySuggestion(typed, "Custom celebration cakes", SUGGESTION);
    expect(form.budget).toBe("10000");
    expect(form.original.title).toBe("Everyday cakes");
  });

  it("replaces whatever alternative was there before", () => {
    const typed = setField(EMPTY_FORM, "alt.title", "My own alternative");
    expect(applySuggestion(typed, "Custom celebration cakes", SUGGESTION).alt.title).toBe("Custom celebration cakes");
  });

  it("never changes the old form", () => {
    applySuggestion(EMPTY_FORM, "x", SUGGESTION);
    expect(EMPTY_FORM.alt.title).toBe("");
  });

  it("copes with a missing figure by leaving that field blank", () => {
    const partial = { ...SUGGESTION, figures: SUGGESTION.figures.slice(0, 1) };
    const alt = applySuggestion(EMPTY_FORM, "T", partial).alt;
    expect(alt.price).toBe("1200");
    expect(alt.cost).toBe("");
  });
});
