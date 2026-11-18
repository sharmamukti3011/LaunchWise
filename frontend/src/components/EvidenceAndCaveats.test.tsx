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
