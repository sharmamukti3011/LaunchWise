import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { EvidenceChoice } from "../api/analyze";
import { EMPTY_FORM, FIELD_TEXT } from "../lib/ownIdea";
import type { FormErrors, OwnIdeaForm } from "../lib/ownIdea";
import { OwnIdeaFormView } from "./OwnIdeaForm";

const noop = () => undefined;
const EVIDENCE: EvidenceChoice[] = [
  { id: "PUNE-001", title: "Home bakers get premium prices", source_name: "YourStory (HerStory)", direction: "supports" },
  { id: "PUNE-003", title: "Shop rents are high", source_name: "Housing.com", direction: "against" },
];

function render(
  over: { form?: OwnIdeaForm; errors?: FormErrors; running?: boolean; evidence?: EvidenceChoice[] } = {},
): string {
  return renderToStaticMarkup(
    <OwnIdeaFormView
      form={over.form ?? EMPTY_FORM}
      errors={over.errors ?? {}}
      evidence={over.evidence ?? EVIDENCE}
      running={over.running ?? false}
      onChange={noop}
      onSubmit={noop}
    />,
  );
}

describe("Try your own idea", () => {
  it("is a section below the scenarios that is collapsed by default", () => {
    const html = render();
    expect(html).toMatch(/^<details(?![^>]*\sopen)/);
    expect(html).toContain("Try your own idea");
  });

  it("has a labelled input for every field in the spec", () => {
    const html = render();
    for (const id of [
      "own-budget", "own-unitsPerDay", "own-daysPerWeek", "own-hoursPerWeek", "own-skills",
      "own-equipment", "own-location", "own-category", "own-original-title", "own-original-price",
      "own-original-cost", "own-original-startup", "own-original-minutes", "own-alt-title",
      "own-alt-price", "own-alt-cost", "own-alt-startup", "own-alt-minutes", "own-alt-evidenceId",
    ]) {
      expect(html).toMatch(new RegExp(`<label[^>]*for="${id}"`));
      expect(html).toMatch(new RegExp(`id="${id}"`));
    }
  });

  it("marks the two figures the engine can assume as optional, and rupee fields as rupees", () => {
    const html = render();
    expect(html).toMatch(/Hours per week[^<]*\(optional\)/);
    expect(html).toMatch(/minutes per (unit|item)[^<]*\(optional\)/i);
    expect(html).toContain("₹");
    expect(html).not.toContain("$");
  });

  it("uses text inputs with a numeric keypad rather than number inputs, so money stays exact", () => {
    const html = render();
    expect(html).not.toMatch(/type="number"/);
    expect(html).toMatch(/id="own-budget"[^>]*inputMode="decimal"|inputMode="decimal"[^>]*id="own-budget"/);
  });

  it("offers the dataset entries for the alternative, and says which argue against", () => {
    const html = render();
    expect(html).toContain("No market evidence link");
    expect(html).toContain("Home bakers get premium prices (YourStory (HerStory))");
    expect(html).toMatch(/Shop rents are high \(Housing\.com\)[^<]*argues against/);
    expect(html).toContain('value="PUNE-001"');
  });

  it("works with no evidence choices at all", () => {
    expect(render({ evidence: [] })).toContain("No market evidence link");
  });

  it("shows a fixed message under a field with an error, and links it for screen readers", () => {
    const html = render({ errors: { budget: FIELD_TEXT.budget } });
    expect(html).toContain(FIELD_TEXT.budget);
    expect(html).toMatch(/id="own-budget"[^>]*aria-invalid="true"|aria-invalid="true"[^>]*id="own-budget"/);
    expect(html).toContain('aria-describedby="own-budget-error"');
    expect(html).toContain('id="own-budget-error"');
  });

  it("marks only the fields that have errors", () => {
    const html = render({ errors: { budget: "x" } });
    expect(html.match(/aria-invalid="true"/g)).toHaveLength(1);
  });

  it("shows a general error as an alert", () => {
    const html = render({ errors: { form: "Please check the highlighted fields and try again." } });
    expect(html).toMatch(/role="alert"[^>]*>[^<]*Please check/);
  });

  it("has a Run analysis button that is disabled, and says so, while running", () => {
    expect(render()).toMatch(/<button[^>]*type="submit"[^>]*>Run analysis</);
    const html = render({ running: true });
    expect(html).toMatch(/<button[^>]*\sdisabled(=|\s|>)/);
    expect(html).toContain("Analysing…");
  });

  it("shows what was typed, escaped", () => {
    const form = { ...EMPTY_FORM, location: "<img src=x onerror=alert(1)>" };
    const html = render({ form });
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("limits the text fields like the server does", () => {
    const html = render();
    expect(html).toMatch(/id="own-location"[^>]*maxLength="80"|maxLength="80"[^>]*id="own-location"/);
    expect(html).toMatch(/id="own-category"[^>]*maxLength="60"|maxLength="60"[^>]*id="own-category"/);
  });
});
