import { afterEach, describe, expect, it, vi } from "vitest";
import { INTAKE_TEXT, IntakeFailure, draftFromText } from "./intake";

const FIELD = { value: "", status: "not_mentioned" };
const DRAFT = {
  budget: { value: "10000", status: "from_description" },
  alternative_mentioned: false,
};

function respond(status: number, body: unknown = {}) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("draftFromText", () => {
  it("POSTs only the text, as JSON, to /api/intake", async () => {
    respond(200, { status: "drafted", message: "m", draft: DRAFT });
    await draftFromText("I have ₹10,000");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/intake");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ text: "I have ₹10,000" });
  });

  it("returns the draft with fixed wording, not the server's message", async () => {
    respond(200, { status: "drafted", message: "server words", draft: DRAFT });
    const result = await draftFromText("x");
    expect(result.kind).toBe("drafted");
    if (result.kind === "drafted") expect(result.draft.budget.value).toBe("10000");
    expect(result.message).toBe(INTAKE_TEXT.drafted);
  });

  it("returns a fallback with the fixed text when Claude could not draft it", async () => {
    respond(200, { status: "fallback", message: "anything", draft: null });
    expect(await draftFromText("x")).toEqual({ kind: "fallback", message: INTAKE_TEXT.fallback });
  });

  it("recognises the budget fallback message and shows its own fixed text", async () => {
    respond(200, {
      status: "fallback",
      message: "The description helper has reached its limit for now. Please fill in the form yourself.",
      draft: null,
    });
    expect(await draftFromText("x")).toEqual({ kind: "fallback", message: INTAKE_TEXT.budget });
  });

  it("treats a 'drafted' answer with no draft as a fallback", async () => {
    respond(200, { status: "drafted", message: "m", draft: null });
    expect((await draftFromText("x")).kind).toBe("fallback");
  });

  it.each([
    [503, "unavailable"],
    [429, "rate_limited"],
    [422, "invalid"],
    [413, "invalid"],
    [500, "server"],
  ])("maps HTTP %i to %s", async (status, kind) => {
    respond(status, { detail: "server words that must never be shown" });
    const error = await draftFromText("x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(IntakeFailure);
    expect(error).toMatchObject({ kind });
    expect((error as IntakeFailure).message).toBe(INTAKE_TEXT[kind as keyof typeof INTAKE_TEXT]);
  });

  it("treats a network failure as 'network' and lets an abort through", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(draftFromText("x")).rejects.toMatchObject({ kind: "network" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("x", "AbortError")));
    await expect(draftFromText("x")).rejects.toMatchObject({ name: "AbortError" });
  });

  it("has fixed text for everything and never mentions Claude's setup", () => {
    for (const text of Object.values(INTAKE_TEXT)) expect(text.length).toBeGreaterThan(10);
    const all = JSON.stringify(INTAKE_TEXT).toLowerCase();
    for (const word of ["api key", "model", "anthropic", "traceback", "$"]) {
      expect(all).not.toContain(word);
    }
    expect(INTAKE_TEXT.unavailable).toBe("Describing your idea is not available right now. Please fill in the form below.");
    void FIELD;
  });
});
