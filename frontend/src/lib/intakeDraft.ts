import type { IntakeDraftBody } from "../api/intake";
import { hasControlOrLineBreak } from "./text";
import type { FieldKey, OwnIdeaForm } from "./ownIdea";

export const MAX_DESCRIPTION = 1500;

/** "from_description": filled from the owner's words. "please_fill": a needed field still empty. */
export type Mark = "from_description" | "please_fill";
export type Marks = Partial<Record<FieldKey, Mark>>;

export function validateDescription(text: string): "invalid" | null {
  const trimmed = text.trim();
  if (trimmed.length < 1 || trimmed.length > MAX_DESCRIPTION) return "invalid";
  // Line breaks and tabs are fine in a description; other control characters are not.
  return hasControlOrLineBreak(trimmed.replace(/[\r\n\t]/g, "")) ? "invalid" : null;
}

type DraftKey = Exclude<keyof IntakeDraftBody, "alternative_mentioned">;

const FIELD_FOR: Record<DraftKey, FieldKey> = {
  budget: "budget",
  units_per_day: "unitsPerDay",
  days_per_week: "daysPerWeek",
  hours_per_week: "hoursPerWeek",
  skills: "skills",
  equipment: "equipment",
  location: "location",
  category: "category",
  original_title: "original.title",
  original_price: "original.price",
  original_cost: "original.cost",
  original_startup: "original.startup",
  original_minutes: "original.minutes",
  alt_title: "alt.title",
  alt_price: "alt.price",
  alt_cost: "alt.cost",
  alt_startup: "alt.startup",
  alt_minutes: "alt.minutes",
};

// Fields the form needs. The others (hours, minutes, skills, equipment) may stay blank: the
// engine assumes the figures and says so, so they are not flagged.
const REQUIRED: FieldKey[] = [
  "budget",
  "unitsPerDay",
  "daysPerWeek",
  "location",
  "category",
  "original.title",
  "original.price",
  "original.cost",
  "original.startup",
];
const REQUIRED_FOR_ALTERNATIVE: FieldKey[] = ["alt.title", "alt.price", "alt.cost", "alt.startup"];

function valueOf(form: OwnIdeaForm, key: FieldKey): string {
  if (key.startsWith("original.")) return form.original[key.slice(9) as keyof OwnIdeaForm["original"]];
  if (key.startsWith("alt.")) return form.alt[key.slice(4) as keyof OwnIdeaForm["alt"]];
  return form[key as keyof Omit<OwnIdeaForm, "original" | "alt">];
}

function withValue(form: OwnIdeaForm, key: FieldKey, value: string): OwnIdeaForm {
  if (key.startsWith("original.")) return { ...form, original: { ...form.original, [key.slice(9)]: value } };
  if (key.startsWith("alt.")) return { ...form, alt: { ...form.alt, [key.slice(4)]: value } };
  return { ...form, [key]: value };
}

/**
 * Put a draft into the form. Fields taken from the description are filled and marked. A field the
 * description did not mention keeps whatever the owner already typed. A needed field that is still
 * empty is flagged. It never runs the analysis: it only returns the form to show.
 */
export function applyDraft(form: OwnIdeaForm, draft: IntakeDraftBody): { form: OwnIdeaForm; marks: Marks } {
  let next = form;
  const marks: Marks = {};
  for (const [draftKey, key] of Object.entries(FIELD_FOR) as [DraftKey, FieldKey][]) {
    const field = draft[draftKey];
    if (field.status === "from_description") {
      next = withValue(next, key, field.value);
      marks[key] = "from_description";
    }
  }
  // A described alternative starts with 'No market evidence'; the owner can pick an entry.
  if (draft.alternative_mentioned) next = withValue(next, "alt.evidenceId", "");
  const needed = draft.alternative_mentioned ? [...REQUIRED, ...REQUIRED_FOR_ALTERNATIVE] : REQUIRED;
  for (const key of needed) {
    if (marks[key] === undefined && valueOf(next, key).trim() === "") marks[key] = "please_fill";
  }
  return { form: next, marks };
}

export function clearMark(marks: Marks, key: FieldKey): Marks {
  if (!(key in marks)) return marks;
  const next = { ...marks };
  delete next[key];
  return next;
}
