import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Analysis } from "../api/demo";
import { Recommendation, recommendationTone } from "./Recommendation";

function run(recommendedId: string | null, keepOriginal: boolean): Analysis {
  return {
    options: [
      { option_id: "orig", title: "Everyday cakes" },
      { option_id: "alt", title: "Custom cakes" },
    ],
    ranking: { recommended_id: recommendedId, keep_original: keepOriginal },
  } as unknown as Analysis;
}

describe("recommendationTone", () => {
  it("is green for a switch or a keep, and amber when nothing is viable", () => {
    expect(recommendationTone(run("alt", false))).toBe("switch");
    expect(recommendationTone(run("orig", true))).toBe("keep");
    expect(recommendationTone(run(null, false))).toBe("none");
  });
});

describe("Recommendation banner", () => {
  it("is green for 'Switch to'", () => {
    const html = renderToStaticMarkup(<Recommendation analysis={run("alt", false)} />);
    expect(html).toContain("Switch to: Custom cakes.");
    expect(html).toContain("emerald");
    expect(html).not.toContain("amber");
  });

  it("is green for 'Keep your original idea'", () => {
    const html = renderToStaticMarkup(<Recommendation analysis={run("orig", true)} />);
    expect(html).toContain("Keep your original idea: Everyday cakes.");
    expect(html).toContain("emerald");
    expect(html).not.toContain("amber");
  });

  it("is amber, not green, when nothing is viable", () => {
    const html = renderToStaticMarkup(<Recommendation analysis={run(null, false)} />);
    expect(html).toContain("None of these options is viable");
    expect(html).toContain("amber");
    expect(html).not.toContain("emerald");
  });

  it("still says it is a suggestion, not a promise of profit", () => {
    const html = renderToStaticMarkup(<Recommendation analysis={run(null, false)} />);
    expect(html).toContain("not a promise of profit");
  });
});
