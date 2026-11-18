import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Analysis, Opportunity } from "../api/demo";
import { EvidenceAndCaveats } from "./EvidenceAndCaveats";

function entry(overrides: Partial<Opportunity> = {}): Opportunity {
  return {
    id: "PUNE-001",
    title: "Home bakers get premium prices",
    location: "Pune",
    category: "bakery",
    signal_summary: "A clear premium.",
    evidence: "e",
    source_name: "YourStory",
    source_url: "https://yourstory.com/x",
    verification_status: "verified",
    signal_strength: "medium",
    direction: "supports",
    label: "Verified against the cited source on 18 Nov 2026.",
    ...overrides,
  };
}

function analysis(evidence: Opportunity[], caveats: Analysis["ranking"]["caveats"] = []): Analysis {
  return {
    market_message: "Market evidence comes from the dataset.",
    evidence,
    ranking: { ranked: [], recommended_id: null, keep_original: false, caveats },
  } as unknown as Analysis;
}

describe("EvidenceAndCaveats", () => {
  it("badges evidence that argues against an option, and only that evidence", () => {
    const html = renderToStaticMarkup(
      <EvidenceAndCaveats
        analysis={analysis([entry(), entry({ id: "PUNE-003", direction: "against" })])}
      />,
    );
    expect(html.match(/Evidence against this option/g)).toHaveLength(1);
    expect(html.indexOf("Evidence against this option")).toBeGreaterThan(html.indexOf("PUNE-001"));
  });

  it("shows the source wording for verified and unverified entries", () => {
    const html = renderToStaticMarkup(
      <EvidenceAndCaveats
        analysis={analysis([
          entry(),
          entry({ id: "PUNE-009", verification_status: "unverified_sample" }),
        ])}
      />,
    );
    expect(html).toContain("Verified source");
    expect(html).toContain("Source cited, not yet verified");
    expect(html).not.toContain("Placeholder data");
  });

  it("escapes text instead of rendering it as markup", () => {
    const html = renderToStaticMarkup(
      <EvidenceAndCaveats analysis={analysis([entry({ title: "<img src=x onerror=alert(1)>" })])} />,
    );
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});

describe("FSSAI note", () => {
  const withFood = (food: boolean) =>
    ({ ...analysis([]), food_business: food }) as unknown as Analysis;

  it("shows the fixed note with its link for a food business", () => {
    const html = renderToStaticMarkup(<EvidenceAndCaveats analysis={withFood(true)} />);
    expect(html).toContain("Selling food from home requires FSSAI registration before you start.");
    expect(html).toContain('href="https://foscos.fssai.gov.in"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("sits under 'Before you rely on this', before the market evidence", () => {
    const html = renderToStaticMarkup(<EvidenceAndCaveats analysis={withFood(true)} />);
    const heading = html.indexOf("Before you rely on this");
    const note = html.indexOf("FSSAI registration");
    expect(heading).toBeGreaterThan(-1);
    expect(note).toBeGreaterThan(heading);
    expect(note).toBeLessThan(html.indexOf("Market evidence</h2>"));
  });

  it("is absent for a business that does not sell food", () => {
    const html = renderToStaticMarkup(<EvidenceAndCaveats analysis={withFood(false)} />);
    expect(html).not.toContain("FSSAI");
  });

  it("shows even when the engine has no caveats of its own", () => {
    const html = renderToStaticMarkup(<EvidenceAndCaveats analysis={withFood(true)} />);
    expect(html).toContain("FSSAI");
    expect(html).toContain("The engine has no caveats for this result.");
  });
});
