import { afterEach, describe, expect, it, vi } from "vitest";
import type { Analysis, DemoRun } from "../api/demo";
import type { AnalyzeBody } from "../api/analyze";
import { demoResult, ownResult } from "./results";

const ANALYSIS = { steps: [] } as unknown as Analysis;
const EXPLANATION = { summary: "s", source: "template", fallback_reason: "not_configured" };

function respond(body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 })));
}

afterEach(() => vi.unstubAllGlobals());

describe("demoResult", () => {
  const run = {
    scenario: { id: "pune-pivot", title: "Pune bakery" },
    notice: "Simulated demo data: made up for this walkthrough.",
    analysis: ANALYSIS,
  } as unknown as DemoRun;

  it("keeps the scenario's title and its simulated-data notice", () => {
    const result = demoResult(run);
    expect(result.title).toBe("Pune bakery");
    expect(result.notice).toContain("Simulated demo data");
    expect(result.analysis).toBe(ANALYSIS);
  });

  it("loads the explanation from the demo endpoint", async () => {
    respond({ scenario_id: "pune-pivot", explanation: EXPLANATION });
    const explanation = await demoResult(run).loadExplanation(new AbortController().signal);
    expect(explanation.source).toBe("template");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/demo/explain/pune-pivot");
  });
});

describe("ownResult", () => {
  const body = { category: "x" } as unknown as AnalyzeBody;

  it("is the owner's own idea, and is never labelled as simulated", () => {
    const result = ownResult(body, ANALYSIS);
    expect(result.title).toBe("Your idea");
    expect(result.notice).toMatch(/left blank/i);
    expect(result.notice).not.toMatch(/simulated/i);
  });

  it("loads the explanation by sending the same request to the explain endpoint", async () => {
    respond({ explanation: EXPLANATION });
    const explanation = await ownResult(body, ANALYSIS).loadExplanation(new AbortController().signal);
    expect(explanation.summary).toBe("s");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/analyze/explain");
    expect(JSON.parse(String(init?.body))).toEqual(body);
  });
});
