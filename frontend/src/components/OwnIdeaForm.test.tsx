import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { EvidenceChoice } from "../api/analyze";
import { EMPTY_FORM, FIELD_TEXT } from "../lib/ownIdea";
import type { FormErrors, OwnIdeaForm } from "../lib/ownIdea";
import type { Marks } from "../lib/intakeDraft";
import { OwnIdeaFormView } from "./OwnIdeaForm";
import type { IntakeUi } from "./OwnIdeaForm";

const noop = () => undefined;
const EVIDENCE: EvidenceChoice[] = [
  { id: "PUNE-001", title: "Home bakers get premium prices", source_name: "YourStory (HerStory)", direction: "supports", location: "Pune", category: "bakery" },
  { id: "PUNE-003", title: "Shop rents are high", source_name: "Housing.com", direction: "against", location: "Pune", category: "bakery" },
];

const PUNE_FORM: OwnIdeaForm = { ...EMPTY_FORM, location: "Pune", category: "home bakery" };
const IDLE_INTAKE: IntakeUi = { text: "", running: false, message: null, unavailable: false };

function render(
  over: {
    form?: OwnIdeaForm;
    errors?: FormErrors;
    running?: boolean;
    evidence?: EvidenceChoice[];
    marks?: Marks;
    intake?: Partial<IntakeUi>;
    open?: boolean;
    notice?: string | null;
  } = {},
): string {
  return renderToStaticMarkup(
    <OwnIdeaFormView
      form={over.form ?? PUNE_FORM}
      errors={over.errors ?? {}}
      marks={over.marks ?? {}}
      intake={{ ...IDLE_INTAKE, ...over.intake }}
      evidence={over.evidence ?? EVIDENCE}
      running={over.running ?? false}
      onChange={noop}
      onSubmit={noop}
      onIntakeText={noop}
      onIntakeSubmit={noop}
      open={over.open ?? false}
      onToggle={noop}
      notice={over.notice ?? null}
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
    expect(html).toContain("Home bakers get premium prices (YourStory (HerStory))");
    expect(html).toMatch(/Shop rents are high \(Housing\.com\)[^<]*argues against/);
    expect(html).toContain('value="PUNE-001"');
  });

  it("offers 'No market evidence' as the first, default choice, valid in every area", () => {
    const html = render();
    expect(html).toMatch(/<select[^>]*id="own-alt-evidenceId"[^>]*><option value="" selected="">No market evidence<\/option>|<select[^>]*id="own-alt-evidenceId"[^>]*><option value="">No market evidence<\/option>/);
    expect(html).not.toContain("No market evidence link");
  });

  it("explains that no evidence means a neutral market score", () => {
    expect(render()).toMatch(/neutral 50/);
  });

  it("hides the dropdown and says so when no entry fits the place", () => {
    for (const form of [{ ...PUNE_FORM, location: "Noida" }, EMPTY_FORM]) {
      const html = render({ form });
      expect(html).not.toContain("<select");
      expect(html).not.toContain("Market evidence it is based on");
      expect(html).toContain("No market evidence for this place yet, so the market score is a neutral 50.");
    }
    const none = render({ evidence: [] });
    expect(none).not.toContain('id="own-alt-evidenceId"');
    expect(none).toContain("a neutral 50.");
  });

  it("hides the dropdown for Khurja bakery, even with Pune entries loaded and one chosen", () => {
    const form = { ...PUNE_FORM, location: "Khurja", category: "bakery", alt: { ...EMPTY_FORM.alt, evidenceId: "PUNE-001" } };
    const html = render({ form });
    expect(html).not.toContain("<select");
    expect(html).not.toContain("PUNE-001");
    expect(html).toContain("No market evidence for this place yet, so the market score is a neutral 50.");
  });

  it("hides the dropdown when the kind of business does not fit", () => {
    const html = render({ form: { ...PUNE_FORM, category: "high-protein breakfast" } });
    expect(html).not.toContain("<select");
  });

  it("lists only the entries that fit, and no others", () => {
    const other = { id: "MUM-001", title: "Mumbai thing", source_name: "X", direction: "supports" as const, location: "Mumbai", category: "bakery" };
    const html = render({ evidence: [...EVIDENCE, other], form: { ...PUNE_FORM, location: "pune, Maharashtra" } });
    expect(html).toContain('value="PUNE-001"');
    expect(html).not.toContain("MUM-001");
  });

  it("labels the hours field with a hint and no warning when nothing is wrong", () => {
    const html = render();
    expect(html).toContain("Total for the week, e.g. 3 hours a day × 7 days = 21.");
    expect(html).not.toContain("own-hoursPerWeek-warning");
  });

  it("shows a gentle, non-blocking warning when the hours are too few", () => {
    const form = { ...PUNE_FORM, unitsPerDay: "3", daysPerWeek: "2", hoursPerWeek: "5", original: { ...EMPTY_FORM.original, minutes: "100" } };
    const html = render({ form });
    expect(html).toMatch(/id="own-hoursPerWeek-warning"[^>]*>That is less than the 10 hours a week/);
    expect(html).toContain('aria-describedby="own-hoursPerWeek-warning"');
    expect(html).not.toContain("aria-invalid");
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


describe("Describe your idea", () => {
  it("has a labelled textarea above the form, limited to 1,500 characters", () => {
    const html = render();
    expect(html).toMatch(/<label[^>]*for="own-description"/);
    expect(html).toMatch(/<textarea[^>]*id="own-description"[^>]*maxLength="1500"|<textarea[^>]*maxLength="1500"[^>]*id="own-description"/);
    expect(html.indexOf("own-description")).toBeLessThan(html.indexOf("<form"));
  });

  it("keeps the textarea outside the form, so pressing Enter in it cannot run the analysis", () => {
    const html = render();
    const form = html.slice(html.indexOf("<form"), html.indexOf("</form>"));
    expect(form).not.toContain("own-description");
  });

  it("has a 'Fill the form for me' button that only fills, and a separate 'Run analysis'", () => {
    const html = render({ intake: { text: "I have 10k" } });
    expect(html).toMatch(/<button[^>]*type="button"[^>]*>Fill the form for me</);
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*>Run analysis</);
  });

  it("disables the button for an empty description and while reading, and says so", () => {
    expect(render()).toMatch(/<button[^>]*type="button"[^>]*\sdisabled(=|\s|>)[^>]*>Fill the form for me</);
    const html = render({ intake: { text: "I have 10k", running: true } });
    expect(html).toMatch(/<button[^>]*type="button"[^>]*\sdisabled(=|\s|>)/);
    expect(html).toContain("Reading…");
  });

  it("says Claude only drafts and the owner checks every field", () => {
    expect(render()).toMatch(/only (drafts|fills)[^<]*you (check|review|edit)/i);
  });

  it("shows a character count against the limit", () => {
    expect(render({ intake: { text: "hello" } })).toContain("5 / 1,500");
  });

  it("adds the AI notice only under a message Claude's draft produced", () => {
    const notice = "Claude can make mistakes. Check the figures before you rely on them.";
    expect(render({ intake: { message: { kind: "info", text: "Filled.", ai: true } } })).toContain(notice);
    expect(render({ intake: { message: { kind: "info", text: "Filled." } } })).not.toContain(notice);
    expect(render({ intake: { message: { kind: "error", text: "No." } } })).not.toContain(notice);
    expect(render()).not.toContain(notice);
  });

  it("shows a message after filling, as a status, and an error as an alert", () => {
    const ok = render({ intake: { message: { kind: "info", text: "We filled in what you described." } } });
    expect(ok).toMatch(/role="status"[^>]*>[^<]*We filled in/);
    const bad = render({ intake: { message: { kind: "error", text: "Too many requests." } } });
    expect(bad).toMatch(/role="alert"[^>]*>[^<]*Too many requests/);
  });

  it("shows 'not available right now' and disables the button when Claude is not set up", () => {
    const html = render({
      intake: { text: "x", unavailable: true, message: { kind: "error", text: "Describing your idea is not available right now. Please fill in the form below." } },
    });
    expect(html).toContain("not available right now");
    expect(html).toMatch(/<button[^>]*type="button"[^>]*\sdisabled(=|\s|>)/);
  });

  it("shows the description as typed, escaped", () => {
    const html = render({ intake: { text: "<script>alert(1)</script>" } });
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});

describe("marks from a draft", () => {
  it("shows 'from your description' next to a filled field", () => {
    const html = render({ marks: { budget: "from_description" } });
    expect(html).toMatch(/id="own-budget-mark"[^>]*>from your description</);
    expect(html).toMatch(/aria-describedby="[^"]*own-budget-mark/);
  });

  it("highlights an empty flagged field and says 'please fill in'", () => {
    const html = render({ marks: { daysPerWeek: "please_fill" } });
    expect(html).toMatch(/id="own-daysPerWeek-mark"[^>]*>please fill in</);
    expect(html).toMatch(/id="own-daysPerWeek"[^>]*class="[^"]*border-amber-500|class="[^"]*border-amber-500[^"]*"[^>]*id="own-daysPerWeek"/);
  });

  it("marks only the fields that were marked", () => {
    const html = render({ marks: { budget: "from_description" } });
    expect(html.match(/from your description/g)).toHaveLength(1);
    expect(html).not.toContain("please fill in");
  });

  it("links both a mark and an error to the field for screen readers", () => {
    const html = render({ marks: { budget: "from_description" }, errors: { budget: "Enter your budget." } });
    expect(html).toMatch(/aria-describedby="own-budget-error own-budget-mark"|aria-describedby="own-budget-mark own-budget-error"/);
  });
});


describe("opening and the suggestion notice", () => {
  it("is closed by default and open when asked, so a suggestion can reveal the form", () => {
    expect(render()).not.toMatch(/^<details[^>]*\sopen/);
    expect(render({ open: true })).toMatch(/^<details[^>]*\sopen/);
  });

  it("shows a status message after a suggestion is copied in", () => {
    const html = render({ notice: "Filled from LaunchWise's suggestion. Edit anything, then click Run analysis." });
    expect(html).toMatch(/role="status"[^>]*>[^<]*Filled from LaunchWise/);
  });

  it("shows no notice by default", () => {
    expect(render()).not.toContain("Filled from LaunchWise");
  });
});
