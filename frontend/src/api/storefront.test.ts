import { afterEach, describe, expect, it, vi } from "vitest";
import { PREVIEW_FAILURE_TEXT, StorefrontFailure, previewStarterPage } from "./storefront";
import type { StarterBody } from "./storefront";

const BODY: StarterBody = {
  business_name: "Aarti's",
  description: "",
  offer_title: "Cake",
  offer_price: "500",
  food_business: true,
};

const PREVIEW = {
  draft_id: "d1",
  slug: "aarti-s-a1b2c3",
  public_path: "/s/aarti-s-a1b2c3",
  config_hash: "f".repeat(64),
  expires_in_minutes: 30,
  preview_html: "<!doctype html><p>x</p>",
};

function respond(status: number, body: unknown = {}) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("previewStarterPage", () => {
  it("POSTs the body as JSON to /api/storefront/preview and returns the preview", async () => {
    respond(200, PREVIEW);
    const result = await previewStarterPage(BODY);
    expect(result.draft_id).toBe("d1");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/storefront/preview");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(BODY);
  });

  it("turns a 422 into field errors carrying only a fixed code", async () => {
    respond(422, {
      detail: "The request was not valid.",
      errors: [
        { field: "business_name", message: "Value error, not_allowed" },
        { field: "description", message: "Value error, no_links_or_markup" },
        { field: "offer_price", message: "Input should be greater than 0" },
      ],
    });
    const error = await previewStarterPage(BODY).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(StorefrontFailure);
    expect((error as StorefrontFailure).fields).toEqual([
      { field: "business_name", code: "not_allowed" },
      { field: "description", code: "no_links_or_markup" },
      { field: "offer_price", code: "invalid" },
    ]);
  });

  it("copes with a 422 that has no errors list", async () => {
    respond(422, { detail: "x" });
    await expect(previewStarterPage(BODY)).rejects.toMatchObject({ kind: "invalid", fields: [] });
  });

  it.each([
    [429, "rate_limited"],
    [413, "invalid"],
    [500, "server"],
    [503, "server"],
  ])("maps HTTP %i to %s with fixed text", async (status, kind) => {
    respond(status, { detail: "server words that must never be shown" });
    const error = await previewStarterPage(BODY).catch((e: unknown) => e);
    expect(error).toMatchObject({ kind });
    expect((error as StorefrontFailure).message).toBe(PREVIEW_FAILURE_TEXT[kind as keyof typeof PREVIEW_FAILURE_TEXT]);
  });

  it("treats a network failure as 'network' and lets an abort through", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(previewStarterPage(BODY)).rejects.toMatchObject({ kind: "network" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("x", "AbortError")));
    await expect(previewStarterPage(BODY)).rejects.toMatchObject({ name: "AbortError" });
  });

  it("has fixed text for every failure", () => {
    for (const text of Object.values(PREVIEW_FAILURE_TEXT)) expect(text.length).toBeGreaterThan(10);
  });
});
