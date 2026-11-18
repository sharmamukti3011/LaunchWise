import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Analysis } from "../api/demo";
import { RunView } from "./RunView";

const analysis = {
  steps: [{ index: 1, tool: "validate_constraints", title: "Checked constraints", status: "ok" }],
} as unknown as Analysis;

describe("RunView", () => {
  it("shows the result's own title and note above the replay, for a demo or for your own idea", () => {
    const html = renderToStaticMarkup(
      <RunView
        result={{ title: "Your idea", notice: "Anything left blank was assumed.", analysis, loadExplanation: vi.fn() }}
      />,
    );
    expect(html).toContain("<strong>Your idea.</strong> Anything left blank was assumed.");
    expect(html).toContain("replay of recorded steps");
  });

  it("shows no note line when there is none", () => {
    const html = renderToStaticMarkup(
      <RunView result={{ title: "Your idea", notice: null, analysis, loadExplanation: vi.fn() }} />,
    );
    expect(html).not.toContain("role=\"note\"");
  });
});
