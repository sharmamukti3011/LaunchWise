import { describe, expect, it } from "vitest";
import type { IntakeDraftBody } from "../api/intake";
import { MAX_DESCRIPTION, applyDraft, clearMark, validateDescription } from "./intakeDraft";
import { EMPTY_FORM, setField } from "./ownIdea";
import type { OwnIdeaForm } from "./ownIdea";

const NOT: { value: string; status: "not_mentioned" } = { value: "", status: "not_mentioned" };
const from = (value: string) => ({ value, status: "from_description" as const });

function draft(over: Partial<Record<string, { value: string; status: "from_description" | "not_mentioned" }>> = {}, alt = false): IntakeDraftBody {
  const base: Record<string, typeof NOT> = {};
  for (const key of [
    "budget", "units_per_day", "days_per_week", "hours_per_week", "skills", "equipment", "location",
    "category", "original_title", "original_price", "original_cost", "original_startup",
    "original_minutes", "alt_title", "alt_price", "alt_cost", "alt_startup", "alt_minutes",
  ]) {
    base[key] = NOT;
  }
  return { ...base, ...over, alternative_mentioned: alt } as unknown as IntakeDraftBody;
}

const DEMO = draft(
  {
    budget: from("10000"),
    units_per_day: from("3"),
    location: from("Pune"),
    category: from("home bakery"),
    original_title: from("Everyday cakes"),
    original_price: from("500"),
    original_cost: from("450"),
    original_startup: from("3000"),
    alt_title: from("Custom celebration cakes"),
    alt_price: from("1400"),
    alt_cost: from("500"),
    alt_startup: from("4000"),
  },
  true,
);

describe("validateDescription", () => {
  it("accepts 1 to 1,500 characters and nothing else", () => {
    expect(MAX_DESCRIPTION).toBe(1500);
    expect(validateDescription("x")).toBeNull();
    expect(validateDescription("x".repeat(1500))).toBeNull();
    expect(validateDescription("x".repeat(1501))).toBe("invalid");
    expect(validateDescription("   ")).toBe("invalid");
    expect(validateDescription("")).toBe("invalid");
  });

  it("allows line breaks and tabs but not other control characters", () => {
    expect(validateDescription("one\ntwo\tthree")).toBeNull();
    expect(validateDescription("a\u0000b")).toBe("invalid");
    expect(validateDescription("a b")).toBe("invalid");
  });
});

describe("applyDraft", () => {
  it("fills the form from the fields taken from the description", () => {
    const { form } = applyDraft(EMPTY_FORM, DEMO);
    expect(form).toMatchObject({
      budget: "10000",
      unitsPerDay: "3",
      location: "Pune",
      category: "home bakery",
      original: { title: "Everyday cakes", price: "500", cost: "450", startup: "3000", minutes: "" },
      alt: { title: "Custom celebration cakes", price: "1400", cost: "500", startup: "4000" },
    });
  });

  it("marks every filled field 'from your description'", () => {
    const { marks } = applyDraft(EMPTY_FORM, DEMO);
    for (const key of ["budget", "unitsPerDay", "location", "original.price", "alt.title"] as const) {
      expect(marks[key]).toBe("from_description");
    }
  });

  it("highlights required fields that were not mentioned and are still empty", () => {
    const { marks } = applyDraft(EMPTY_FORM, DEMO);
    expect(marks.daysPerWeek).toBe("please_fill"); // 'weekends only' is not a number
  });

  it("does not highlight optional fields, which the engine can assume", () => {
    const { marks } = applyDraft(EMPTY_FORM, DEMO);
    for (const key of ["hoursPerWeek", "skills", "equipment", "original.minutes", "alt.minutes"] as const) {
      expect(marks[key]).toBeUndefined();
    }
  });

  it("sets the alternative's evidence to 'No market evidence' when an alternative is described", () => {
    const picked = setField(EMPTY_FORM, "alt.evidenceId", "PUNE-001");
    expect(applyDraft(picked, DEMO).form.alt.evidenceId).toBe("");
  });

  it("leaves the alternative alone, and does not flag it, when none was described", () => {
    const { form, marks } = applyDraft(EMPTY_FORM, draft({ budget: from("5000") }, false));
    expect(form.alt).toEqual(EMPTY_FORM.alt);
    for (const key of ["alt.title", "alt.price", "alt.cost", "alt.startup"] as const) {
      expect(marks[key]).toBeUndefined();
    }
  });

  it("flags the alternative's missing required fields when one was described", () => {
    const { marks } = applyDraft(EMPTY_FORM, draft({ alt_title: from("Custom cakes") }, true));
    expect(marks["alt.price"]).toBe("please_fill");
    expect(marks["alt.title"]).toBe("from_description");
  });

  it("never wipes what the owner already typed into a field the description did not mention", () => {
    const typed: OwnIdeaForm = { ...EMPTY_FORM, daysPerWeek: "2", hoursPerWeek: "10" };
    const { form, marks } = applyDraft(typed, DEMO);
    expect(form.daysPerWeek).toBe("2");
    expect(marks.daysPerWeek).toBeUndefined(); // filled, so nothing to ask for
  });

  it("overwrites a field the description did state", () => {
    const typed = setField(EMPTY_FORM, "budget", "999");
    expect(applyDraft(typed, DEMO).form.budget).toBe("10000");
  });

  it("keeps skills and equipment as the comma-separated text the form uses", () => {
    const { form } = applyDraft(EMPTY_FORM, draft({ skills: from("baking, decorating") }));
    expect(form.skills).toBe("baking, decorating");
  });

  it("returns a new form and never changes the old one", () => {
    applyDraft(EMPTY_FORM, DEMO);
    expect(EMPTY_FORM.budget).toBe("");
  });
});

describe("clearMark", () => {
  it("removes only the edited field's mark", () => {
    const { marks } = applyDraft(EMPTY_FORM, DEMO);
    const next = clearMark(marks, "budget");
    expect(next.budget).toBeUndefined();
    expect(next.location).toBe("from_description");
    expect(marks.budget).toBe("from_description"); // the old marks are untouched
  });

  it("returns the same object when there was nothing to clear", () => {
    const marks = {};
    expect(clearMark(marks, "budget")).toBe(marks);
  });
});
