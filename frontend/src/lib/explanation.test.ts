import { describe, expect, it } from "vitest";
import { ENGINE_NOTE, panelCopy } from "./explanation";

describe("panelCopy", () => {
  it("labels Claude's text as AI-generated", () => {
    const copy = panelCopy({ summary: "s", source: "claude", fallback_reason: null });
    expect(copy.title).toBe("Claude's explanation");
    expect(copy.badge).toBe("AI-generated");
  });

  it("never calls the template's text AI-generated or Claude's", () => {
    for (const reason of ["not_configured", "budget", "unavailable", "invalid"] as const) {
      const copy = panelCopy({ summary: "s", source: "template", fallback_reason: reason });
      expect(copy.title).not.toMatch(/claude/i);
      expect(copy.badge).toMatch(/not AI/i);
      expect(copy.badge).not.toBe("AI-generated");
    }
  });

  it("always says the engine made the decision", () => {
    expect(ENGINE_NOTE).toMatch(/engine made the decision/i);
  });

  it("uses rupees and never dollars in its copy", () => {
    const all = JSON.stringify([
      panelCopy({ summary: "s", source: "claude", fallback_reason: null }),
      panelCopy({ summary: "s", source: "template", fallback_reason: "budget" }),
      ENGINE_NOTE,
    ]);
    expect(all).not.toContain("$");
  });
});
