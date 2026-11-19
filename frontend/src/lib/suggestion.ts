import type { SuggestionInfo } from "../api/demo";
import type { OwnIdeaForm } from "./ownIdea";

/** Copy a suggestion into the alternative's fields, so the owner can edit it and run it as theirs. */
export function applySuggestion(form: OwnIdeaForm, title: string, suggestion: SuggestionInfo): OwnIdeaForm {
  const value = (field: SuggestionInfo["figures"][number]["field"]): string =>
    suggestion.figures.find((figure) => figure.field === field)?.value ?? "";
  return {
    ...form,
    alt: {
      title,
      price: value("price"),
      cost: value("variable_cost"),
      startup: value("startup_cost"),
      minutes: value("minutes_per_unit"),
      // Linked to the entry it came from, so it keeps that entry's market signal.
      evidenceId: suggestion.evidence_id,
    },
  };
}
