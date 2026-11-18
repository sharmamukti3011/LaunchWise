import { INTAKE_TEXT, IntakeFailure, draftFromText } from "../api/intake";
import type { IntakeResult } from "../api/intake";
import { applyDraft, validateDescription } from "./intakeDraft";
import type { Marks } from "./intakeDraft";
import type { OwnIdeaForm } from "./ownIdea";

export type FillOutcome =
  | { kind: "drafted"; form: OwnIdeaForm; marks: Marks; message: string; unavailable: false }
  | { kind: "fallback"; form: OwnIdeaForm; marks: Marks; message: string; unavailable: false }
  | { kind: "error"; form: OwnIdeaForm; marks: Marks; message: string; unavailable: boolean };

/**
 * "Fill the form for me": send the description to /api/intake and fill the form from the draft.
 * It only drafts. It never runs the analysis, and a failure leaves the form exactly as it was.
 */
export async function fillFromDescription(
  text: string,
  form: OwnIdeaForm,
  send: (text: string, signal?: AbortSignal) => Promise<IntakeResult> = draftFromText,
  signal?: AbortSignal,
): Promise<FillOutcome> {
  if (validateDescription(text) !== null) {
    return { kind: "error", form, marks: {}, message: INTAKE_TEXT.invalid, unavailable: false };
  }
  try {
    const result = await send(text, signal);
    if (result.kind === "fallback") {
      return { kind: "fallback", form, marks: {}, message: result.message, unavailable: false };
    }
    const applied = applyDraft(form, result.draft);
    return { kind: "drafted", ...applied, message: result.message, unavailable: false };
  } catch (error) {
    if (error instanceof IntakeFailure) {
      return {
        kind: "error",
        form,
        marks: {},
        message: error.message,
        unavailable: error.kind === "unavailable",
      };
    }
    throw error; // an abort: the caller ignores it
  }
}
