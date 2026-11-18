import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalyzeFailure, FAILURE_TEXT, analyzeOwn, explainOwn, fetchEvidenceChoices } from "./analyze";
import type { AnalyzeBody } from "./analyze";

const BODY = { profile: {}, category: "x", options: [] } as unknown as AnalyzeBody;

function respond(status: number, body: unknown = {}, headers: Record<string, string> = {}) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers })));
}

afterEach(() => vi.unstubAllGlobals());

describe("analyzeOwn", () => {
  it("POSTs the body as JSON to /api/analyze and returns the analysis", async () => {
    respond(200, { market_coverage: "covered" });
    const result = await analyzeOwn(BODY);
    expect(result.market_coverage).toBe("covered");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/analyze");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(BODY);
  });

  it("turns a 422 into field errors, without the server's detail", async () => {
    respond(422, {
      detail: "The request was not valid.",
      errors: [{ field: "profile.budget", message: "fixed library text" }],
    });
    const error = await analyzeOwn(BODY).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(AnalyzeFailure);
    expect(error).toMatchObject({ kind: "invalid", fields: [{ field: "profile.budget" }] });
  });

  it("copes with a 422 that has no usable errors list", async () => {
    respond(422, { detail: "x" });
    await expect(analyzeOwn(BODY)).rejects.toMatchObject({ kind: "invalid", fields: [] });
  });

  it.each([
    [429, "rate_limited"],
    [413, "invalid"],
    [500, "server"],
    [503, "server"],
  ])("maps HTTP %i to %s", async (status, kind) => {
    respond(status, { detail: "server words that must never be shown" });
    await expect(analyzeOwn(BODY)).rejects.toMatchObject({ kind });
  });

  it("treats a network failure as 'network' and lets an abort through", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(analyzeOwn(BODY)).rejects.toMatchObject({ kind: "network" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("x", "AbortError")));
    await expect(analyzeOwn(BODY)).rejects.toMatchObject({ name: "AbortError" });
  });

  it("has fixed text for every failure and none of it mentions the server", () => {
    for (const kind of ["invalid", "rate_limited", "server", "network"] as const) {
      expect(FAILURE_TEXT[kind].length).toBeGreaterThan(10);
    }
    expect(JSON.stringify(FAILURE_TEXT).toLowerCase()).not.toContain("traceback");
  });
});

describe("explainOwn", () => {
  it("POSTs the same body to /api/analyze/explain and returns the explanation", async () => {
    respond(200, { explanation: { summary: "s", source: "template", fallback_reason: "not_configured" } });
    const explanation = await explainOwn(BODY);
    expect(explanation.source).toBe("template");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/analyze/explain");
  });

  it("fails with the same kinds", async () => {
    respond(429);
    await expect(explainOwn(BODY)).rejects.toMatchObject({ kind: "rate_limited" });
  });
});

describe("fetchEvidenceChoices", () => {
  it("returns the choices", async () => {
    respond(200, { evidence: [{ id: "PUNE-001", title: "t", source_name: "s", direction: "supports" }] });
    expect((await fetchEvidenceChoices()).map((e) => e.id)).toEqual(["PUNE-001"]);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/market-evidence");
  });

  it("returns an empty list rather than failing the form if the request fails", async () => {
    respond(500);
    expect(await fetchEvidenceChoices()).toEqual([]);
  });
});
