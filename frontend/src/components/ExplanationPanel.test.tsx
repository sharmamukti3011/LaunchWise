import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Explanation } from "../api/demo";
import { ExplanationPanel } from "./ExplanationPanel";

const NOTICE = "Claude can make mistakes. Check the figures before you rely on them.";
const base = { summary: "Custom cakes look best.", fallback_reason: null } as const;

const html = (explanation: Explanation) =>
  renderToStaticMarkup(<ExplanationPanel state={{ status: "ready", explanation }} />);

describe("ExplanationPanel AI notice", () => {
  it("shows the notice under an explanation written by Claude", () => {
    expect(html({ ...base, source: "claude" })).toContain(NOTICE);
  });

  it("does not show it under the standard (template) explanation", () => {
    expect(html({ ...base, source: "template", fallback_reason: "not_configured" })).not.toContain(NOTICE);
  });

  it("does not show it while loading or on error", () => {
    for (const state of [{ status: "loading" }, { status: "error" }] as const) {
      expect(renderToStaticMarkup(<ExplanationPanel state={state} />)).not.toContain(NOTICE);
    }
  });
});
