import { afterEach, describe, expect, it, vi } from "vitest";
import { DemoError, explainScenario, fetchScenarios, runScenario } from "./demo";

function respond(status: number, body: unknown = {}, headers: Record<string, string> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("fetchScenarios", () => {
  it("returns the scenario list", async () => {
    respond(200, { scenarios: [{ id: "a", title: "A", summary: "s", simulated: true, notice: "n" }] });
    expect((await fetchScenarios()).map((s) => s.id)).toEqual(["a"]);
    expect(fetch).toHaveBeenCalledWith("/api/demo/scenarios", expect.anything());
  });
});

describe("runScenario", () => {
  it("POSTs to the run endpoint with the id encoded", async () => {
    respond(200, { simulated: true });
    await runScenario("pune-pivot");
    expect(fetch).toHaveBeenCalledWith(
      "/api/demo/run/pune-pivot",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("explains a rate limit with the wait time", async () => {
    respond(429, { detail: "x" }, { "Retry-After": "30" });
    await expect(runScenario("a")).rejects.toMatchObject({
      kind: "rate_limited",
      message: expect.stringContaining("30 seconds"),
    });
  });

  it("maps 404, other server errors and network failures to plain messages", async () => {
    respond(404);
    await expect(runScenario("a")).rejects.toMatchObject({ kind: "not_found" });
    respond(500);
    await expect(runScenario("a")).rejects.toMatchObject({ kind: "server" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    await expect(runScenario("a")).rejects.toMatchObject({ kind: "network" });
  });

  it("never shows raw server text to the visitor", async () => {
    respond(500, { detail: "Traceback secret" });
    const error = await runScenario("a").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(DemoError);
    expect((error as DemoError).message).not.toContain("secret");
  });

  it("lets an abort through unchanged", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("x", "AbortError")));
    await expect(runScenario("a")).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("explainScenario", () => {
  const body = {
    scenario_id: "pune-pivot",
    simulated: true,
    notice: "n",
    explanation: { summary: "s", source: "claude", fallback_reason: null },
  };

  it("POSTs to the explain endpoint and returns the explanation", async () => {
    respond(200, body);
    const result = await explainScenario("pune-pivot");
    expect(result.explanation.source).toBe("claude");
    expect(fetch).toHaveBeenCalledWith(
      "/api/demo/explain/pune-pivot",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("maps failures to the same plain messages", async () => {
    respond(429, {}, { "Retry-After": "5" });
    await expect(explainScenario("a")).rejects.toMatchObject({ kind: "rate_limited" });
    respond(500);
    await expect(explainScenario("a")).rejects.toMatchObject({ kind: "server" });
  });
});
