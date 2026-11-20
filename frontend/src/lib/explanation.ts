import type { Explanation } from "../api/demo";

export const ENGINE_NOTE =
  "The engine made the decision from your numbers. This text only explains it and cannot change it.";

export interface PanelCopy {
  title: string;
  badge: string;
}

/** The label always matches who wrote the text: Claude, or the built-in template. */
export function panelCopy(explanation: Explanation): PanelCopy {
  if (explanation.source === "claude") {
    return { title: "Claude's explanation", badge: "AI-generated" };
  }
  return { title: "Explanation", badge: "Standard explanation, not AI" };
}

/** Shown only under text Claude wrote, never under the standard (template) wording. */
export const AI_NOTICE = "Claude can make mistakes. Check the figures before you rely on them.";
