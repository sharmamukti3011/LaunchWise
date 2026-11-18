import { describe, expect, it } from "vitest";
import {
  EMPTY_FORM,
  FIELD_TEXT,
  GENERAL_ERROR,
  buildAnalyzeBody,
  mapServerErrors,
  parseMoney,
  setField,
  serverFieldToKey,
  validateOwnIdea,
} from "./ownIdea";
import type { OwnIdeaForm } from "./ownIdea";

const FILLED: OwnIdeaForm = {
  ...EMPTY_FORM,
  budget: "10000",
  unitsPerDay: "3",
  daysPerWeek: "2",
  skills: "baking, decorating",
  equipment: "oven, mixer",
  location: "Pune",
  category: "home bakery",
  original: { title: "Everyday cakes", price: "500", cost: "450", startup: "3000", minutes: "" },
};

const withAlt = (alt: Partial<OwnIdeaForm["alt"]>): OwnIdeaForm => ({
  ...FILLED,
  alt: { ...EMPTY_FORM.alt, ...alt },
});

describe("parseMoney", () => {
  it.each([
    ["10000", "10000"],
    ["10,000", "10000"],
    ["₹10,000", "10000"],
    ["₹ 1,25,000", "125000"],
    ["899.5", "899.5"],
    ["899.50", "899.50"],
    ["0", "0"],
    ["10000000", "10000000"],
  ])("accepts %s as %s", (input, expected) => {
    expect(parseMoney(input)).toBe(expected);
  });

  it.each(["", "  ", "abc", "-5", "1e5", "1.234", "10000001", "₹", "1,,0", "5.", ".5", "12 34"])(
    "rejects %j",
    (input) => {
      expect(parseMoney(input)).toBeNull();
    },
  );
});

describe("validateOwnIdea", () => {
  it("accepts a complete form with the optional figures left blank", () => {
    expect(validateOwnIdea(FILLED)).toEqual({});
  });

  it("requires the core fields", () => {
    const errors = validateOwnIdea(EMPTY_FORM);
    for (const key of [
      "budget",
      "unitsPerDay",
      "daysPerWeek",
      "location",
      "category",
      "original.title",
      "original.price",
      "original.cost",
      "original.startup",
    ]) {
      expect(errors[key as keyof typeof errors]).toBe(FIELD_TEXT[key as keyof typeof FIELD_TEXT]);
    }
    expect(errors.hoursPerWeek).toBeUndefined(); // optional
    expect(errors["original.minutes"]).toBeUndefined(); // optional
  });

  it.each([
    ["unitsPerDay", "10001"],
    ["unitsPerDay", "2.5"],
    ["unitsPerDay", "-1"],
    ["daysPerWeek", "8"],
    ["hoursPerWeek", "169"],
    ["hoursPerWeek", "abc"],
  ] as const)("rejects %s = %s", (field, value) => {
    expect(validateOwnIdea({ ...FILLED, [field]: value })[field]).toBe(FIELD_TEXT[field]);
  });

  it.each([
    ["unitsPerDay", "10000"],
    ["unitsPerDay", "0"],
    ["daysPerWeek", "7"],
    ["daysPerWeek", "0"],
    ["hoursPerWeek", "168"],
    ["hoursPerWeek", "0"],
  ] as const)("accepts the limit %s = %s", (field, value) => {
    expect(validateOwnIdea({ ...FILLED, [field]: value })[field]).toBeUndefined();
  });

  it("matches the server's text limits", () => {
    expect(validateOwnIdea({ ...FILLED, location: "l".repeat(80) }).location).toBeUndefined();
    expect(validateOwnIdea({ ...FILLED, location: "l".repeat(81) }).location).toBeDefined();
    expect(validateOwnIdea({ ...FILLED, category: "c".repeat(60) }).category).toBeUndefined();
    expect(validateOwnIdea({ ...FILLED, category: "c".repeat(61) }).category).toBeDefined();
    const title = (n: number) => ({ ...FILLED.original, title: "t".repeat(n) });
    expect(validateOwnIdea({ ...FILLED, original: title(80) })["original.title"]).toBeUndefined();
    expect(validateOwnIdea({ ...FILLED, original: title(81) })["original.title"]).toBeDefined();
  });

  it("limits skills and equipment to 20 items of up to 60 characters", () => {
    const items = (n: number) => Array.from({ length: n }, (_, i) => `s${i}`).join(",");
    expect(validateOwnIdea({ ...FILLED, skills: items(20) }).skills).toBeUndefined();
    expect(validateOwnIdea({ ...FILLED, skills: items(21) }).skills).toBeDefined();
    expect(validateOwnIdea({ ...FILLED, equipment: "e".repeat(61) }).equipment).toBeDefined();
    expect(validateOwnIdea({ ...FILLED, skills: "" }).skills).toBeUndefined(); // may be empty
  });

  it("rejects control characters and line breaks in single-line fields", () => {
    expect(validateOwnIdea({ ...FILLED, location: "Pune\nBcc" }).location).toBeDefined();
    expect(validateOwnIdea({ ...FILLED, category: "bakery\u0000" }).category).toBeDefined();
  });

  it("ignores a completely blank alternative", () => {
    expect(validateOwnIdea(withAlt({}))).toEqual({});
  });

  it("requires the alternative's core fields once any of them is filled", () => {
    const errors = validateOwnIdea(withAlt({ title: "Custom cakes" }));
    for (const key of ["alt.price", "alt.cost", "alt.startup"] as const) {
      expect(errors[key]).toBe(FIELD_TEXT[key]);
    }
    expect(errors["alt.title"]).toBeUndefined();
    expect(errors["alt.evidenceId"]).toBeUndefined(); // the server says when it is needed
  });
});

describe("buildAnalyzeBody", () => {
  it("sends blank optional figures as missing, so the engine assumes them", () => {
    const body = buildAnalyzeBody(FILLED);
    expect("hours_per_week" in body.profile).toBe(false);
    expect("minutes_per_unit" in body.options[0]).toBe(false);
  });

  it("sends the figures the owner gave, tagged user_provided", () => {
    const form = { ...FILLED, hoursPerWeek: "12", original: { ...FILLED.original, minutes: "60" } };
    const body = buildAnalyzeBody(form);
    expect(body.profile.hours_per_week).toEqual({ value: 12, source: "user_provided" });
    expect(body.options[0].minutes_per_unit).toEqual({ value: 60, source: "user_provided" });
  });

  it("sends money as exact strings, never floats", () => {
    const body = buildAnalyzeBody({ ...FILLED, budget: "₹10,000", original: { ...FILLED.original, price: "899.50" } });
    expect(body.profile.budget).toBe("10000");
    expect(body.options[0].price).toBe("899.50");
    expect(typeof body.options[0].variable_cost_per_unit).toBe("string");
  });

  it("builds the profile and the original idea", () => {
    const body = buildAnalyzeBody(FILLED);
    expect(body.profile).toMatchObject({
      units_per_day: 3,
      days_per_week: 2,
      skills: ["baking", "decorating"],
      equipment: ["oven", "mixer"],
      location: "Pune",
    });
    expect(body.category).toBe("home bakery");
    expect(body.options).toHaveLength(1);
    expect(body.options[0]).toMatchObject({ id: "original", is_original: true, title: "Everyday cakes" });
  });

  it("trims text and drops empty list items", () => {
    const body = buildAnalyzeBody({ ...FILLED, skills: " baking ,, decorating ,", location: "  Pune " });
    expect(body.profile.skills).toEqual(["baking", "decorating"]);
    expect(body.profile.location).toBe("Pune");
  });

  it("adds the alternative, with its evidence link, as the second option", () => {
    const body = buildAnalyzeBody(
      withAlt({ title: "Custom cakes", price: "1400", cost: "500", startup: "4000", minutes: "100", evidenceId: "PUNE-001" }),
    );
    expect(body.options).toHaveLength(2);
    expect(body.options[1]).toMatchObject({
      id: "alternative",
      is_original: false,
      opportunity_id: "PUNE-001",
      minutes_per_unit: { value: 100, source: "user_provided" },
    });
  });

  it("leaves the link out when none was chosen, and sends no alternative when it is blank", () => {
    const withoutLink = buildAnalyzeBody(withAlt({ title: "X", price: "1", cost: "1", startup: "1" }));
    expect("opportunity_id" in withoutLink.options[1]).toBe(false);
    expect(buildAnalyzeBody(FILLED).options).toHaveLength(1);
  });
});

describe("serverFieldToKey", () => {
  it.each([
    ["profile.budget", "budget"],
    ["profile.units_per_day", "unitsPerDay"],
    ["profile.days_per_week", "daysPerWeek"],
    ["profile.hours_per_week", "hoursPerWeek"],
    ["profile.hours_per_week.value", "hoursPerWeek"],
    ["profile.skills", "skills"],
    ["profile.skills.3", "skills"],
    ["profile.equipment.0", "equipment"],
    ["profile.location", "location"],
    ["category", "category"],
    ["options.0.title", "original.title"],
    ["options.0.price", "original.price"],
    ["options.0.variable_cost_per_unit", "original.cost"],
    ["options.0.fixed_startup_costs", "original.startup"],
    ["options.0.minutes_per_unit.value", "original.minutes"],
    ["options.1.title", "alt.title"],
    ["options.1.opportunity_id", "alt.evidenceId"],
    ["options.1.fixed_startup_costs", "alt.startup"],
  ])("maps %s to %s", (field, key) => {
    expect(serverFieldToKey(field)).toBe(key);
  });

  it.each(["options", "request", "options.2.title", "options.0.opportunity_id", "profile", ""])(
    "does not map %j to a field",
    (field) => {
      expect(serverFieldToKey(field)).toBeNull();
    },
  );
});

describe("mapServerErrors", () => {
  it("shows the field's own fixed text, never the server's words", () => {
    const errors = mapServerErrors([
      { field: "profile.budget", message: "Input should be greater than or equal to 0" },
      { field: "options.1.opportunity_id", message: "Each alternative must link to a market evidence entry from the dataset." },
    ]);
    expect(errors.budget).toBe(FIELD_TEXT.budget);
    expect(errors["alt.evidenceId"]).toBe(FIELD_TEXT["alt.evidenceId"]);
    expect(JSON.stringify(errors)).not.toContain("Input should");
  });

  it("falls back to a general message when no field can be named", () => {
    expect(mapServerErrors([{ field: "options", message: "x" }])).toEqual({ form: GENERAL_ERROR });
    expect(mapServerErrors([])).toEqual({ form: GENERAL_ERROR });
  });

  it("describes the evidence choice with 'No market evidence' as an option", () => {
    expect(FIELD_TEXT["alt.evidenceId"]).toContain("No market evidence");
  });

  it("keeps the general message alongside mapped fields only when something was unmapped", () => {
    const errors = mapServerErrors([
      { field: "category", message: "x" },
      { field: "request", message: "y" },
    ]);
    expect(errors.category).toBe(FIELD_TEXT.category);
    expect(errors.form).toBe(GENERAL_ERROR);
  });
});

describe("wording", () => {
  it("uses rupees and never a dollar sign", () => {
    expect(JSON.stringify(FIELD_TEXT)).not.toContain("$");
  });
});

describe("setField", () => {
  it("sets a top-level field and leaves everything else alone", () => {
    const next = setField(EMPTY_FORM, "budget", "5000");
    expect(next.budget).toBe("5000");
    expect(next.original).toBe(EMPTY_FORM.original);
    expect(EMPTY_FORM.budget).toBe(""); // never mutates the old form
  });

  it("sets a nested field of the original idea or of the alternative", () => {
    expect(setField(EMPTY_FORM, "original.price", "500").original.price).toBe("500");
    const alt = setField(EMPTY_FORM, "alt.evidenceId", "PUNE-001").alt;
    expect(alt.evidenceId).toBe("PUNE-001");
    expect(setField(EMPTY_FORM, "alt.title", "X").original.title).toBe("");
  });
});
