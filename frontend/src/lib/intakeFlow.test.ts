import { afterEach, describe, expect, it, vi } from "vitest";
import { INTAKE_TEXT } from "../api/intake";
import { fillFromDescription } from "./intakeFlow";
import { EMPTY_FORM, setField } from "./ownIdea";

const NOT = { value: "", status: "not_mentioned" };
function draftBody() {
  const keys = ["budget","units_per_day","days_per_week","hours_per_week","skills","equipment","location","category","original_title","original_price","original_cost","original_startup","original_minutes","alt_title","alt_price","alt_cost","alt_startup","alt_minutes"];
  return Object.fromEntries(keys.map((k) => [k, k === "budget" ? { value: "10000", status: "from_description" } : NOT])) as Record<string, unknown>;
}

function respond(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("fillFromDescription", () => {
  it("fills the form, marks the fields, and tells the owner to check everything", async () => {
    respond(200, { status: "drafted", message: "m", draft: { ...draftBody(), alternative_mentioned: false } });
    const result = await fillFromDescription("I have ₹10,000", EMPTY_FORM);
    expect(result.kind).toBe("drafted");
    expect(result.form.budget).toBe("10000");
    expect(result.marks.budget).toBe("from_description");
    expect(result.message).toBe(INTAKE_TEXT.drafted);
  });

  it("only ever calls /api/intake: it never runs the analysis or asks for an explanation", async () => {
    respond(200, { status: "drafted", message: "m", draft: { ...draftBody(), alternative_mentioned: true } });
    await fillFromDescription("text", EMPTY_FORM);
    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    expect(urls).toEqual(["/api/intake"]);
  });

  it("leaves the form exactly as it was after a fallback, with the fixed message", async () => {
    respond(200, { status: "fallback", message: "x", draft: null });
    const typed = setField(EMPTY_FORM, "location", "Pune");
    const result = await fillFromDescription("text", typed);
    expect(result.kind).toBe("fallback");
    expect(result.form).toBe(typed);
    expect(result.marks).toEqual({});
    expect(result.message).toBe(INTAKE_TEXT.fallback);
  });

  it("returns the fixed 'not available' text and a flag when Claude is not set up", async () => {
    respond(503, { detail: "Describing your idea is not available right now." });
    const result = await fillFromDescription("text", EMPTY_FORM);
    expect(result).toMatchObject({ kind: "error", unavailable: true, message: INTAKE_TEXT.unavailable });
    expect(result.form).toBe(EMPTY_FORM);
  });

  it.each([[429, "rate_limited"], [422, "invalid"], [500, "server"]] as const)(
    "turns HTTP %i into the fixed '%s' message and leaves the form alone",
    async (status, kind) => {
      respond(status, {});
      const result = await fillFromDescription("text", EMPTY_FORM);
      expect(result).toMatchObject({ kind: "error", unavailable: false, message: INTAKE_TEXT[kind] });
      expect(result.form).toBe(EMPTY_FORM);
    },
  );

  it("does not call the server at all for an empty or oversized description", async () => {
    respond(200, {});
    for (const text of ["", "   ", "x".repeat(1501)]) {
      const result = await fillFromDescription(text, EMPTY_FORM);
      expect(result).toMatchObject({ kind: "error", message: INTAKE_TEXT.invalid });
    }
    expect(fetch).not.toHaveBeenCalled();
  });
});
