import { afterEach, describe, expect, it, vi } from "vitest";
import { CONTACT_TEXT, sendContact } from "./contact";

const VALUES = { name: "Asha", email: "asha@example.com", message: "Hello there", website: "" };

function respond(status: number, body: unknown = {}) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("sendContact", () => {
  it("POSTs the four fields as JSON to /api/contact", async () => {
    respond(200, { status: "sent" });
    await sendContact(VALUES);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/contact");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(VALUES);
  });

  it.each([
    [200, "sent"],
    [422, "invalid"],
    [429, "rate_limited"],
    [502, "send_failed"],
    [503, "unavailable"],
    [500, "failed"],
    [404, "failed"],
  ])("maps HTTP %i to %s", async (status, outcome) => {
    respond(status, { detail: "server words that must never be shown" });
    expect(await sendContact(VALUES)).toBe(outcome);
  });

  it("treats a network failure as 'failed'", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    expect(await sendContact(VALUES)).toBe("failed");
  });

  it("lets an abort through", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("x", "AbortError")));
    await expect(sendContact(VALUES)).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("CONTACT_TEXT", () => {
  it("has a fixed plain-language message for every outcome", () => {
    for (const outcome of ["sent", "invalid", "rate_limited", "send_failed", "unavailable", "failed"] as const) {
      expect(CONTACT_TEXT[outcome].length).toBeGreaterThan(10);
    }
    expect(CONTACT_TEXT.sent).toBe("Thanks, your message has been sent.");
  });

  it("never mentions SMTP, servers or configuration", () => {
    const all = JSON.stringify(CONTACT_TEXT).toLowerCase();
    for (const word of ["smtp", "password", "titan", "configur", "mailbox", "env"]) {
      expect(all).not.toContain(word);
    }
  });
});
