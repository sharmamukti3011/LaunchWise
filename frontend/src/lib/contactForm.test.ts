import { describe, expect, it } from "vitest";
import {
  EMPTY_VALUES,
  LIMITS,
  contactReducer,
  initialState,
  validateContact,
} from "./contactForm";

const GOOD = { name: "Asha", email: "asha@example.com", message: "Hello there", website: "" };

describe("validateContact", () => {
  it("accepts a normal message", () => {
    expect(validateContact(GOOD)).toBeNull();
  });

  it("matches the server's limits", () => {
    expect(LIMITS).toEqual({ name: 100, email: 254, message: 2000 });
    expect(validateContact({ ...GOOD, name: "n".repeat(100) })).toBeNull();
    expect(validateContact({ ...GOOD, name: "n".repeat(101) })).toBe("invalid");
    expect(validateContact({ ...GOOD, message: "m".repeat(2000) })).toBeNull();
    expect(validateContact({ ...GOOD, message: "m".repeat(2001) })).toBe("invalid");
    expect(validateContact({ ...GOOD, message: "x" })).toBeNull();
  });

  it("rejects empty or blank fields and an obviously bad email", () => {
    expect(validateContact({ ...GOOD, name: "   " })).toBe("invalid");
    expect(validateContact({ ...GOOD, message: "" })).toBe("invalid");
    expect(validateContact({ ...GOOD, email: "not-an-email" })).toBe("invalid");
    expect(validateContact({ ...GOOD, email: "a@b" })).toBe("invalid");
  });

  it("rejects line breaks in the single-line fields", () => {
    expect(validateContact({ ...GOOD, name: "Asha\\nBcc: x" })).toBeNull(); // a literal backslash-n
    expect(validateContact({ ...GOOD, name: "Asha\nBcc: x" })).toBe("invalid");
    expect(validateContact({ ...GOOD, email: "a@b.com\r\nBcc: x" })).toBe("invalid");
  });

  it("rejects other control characters and the Unicode line separators", () => {
    expect(validateContact({ ...GOOD, name: "Asha\u0000" })).toBe("invalid");
    expect(validateContact({ ...GOOD, name: "Asha\u2028Bcc" })).toBe("invalid");
    // A separator at the very end is trimmed like whitespace; one in the middle is rejected.
    expect(validateContact({ ...GOOD, email: "a\u2029@b.com" })).toBe("invalid");
    expect(validateContact({ ...GOOD, name: "आशा पाटिल" })).toBeNull(); // ordinary names are fine
  });

  it("allows line breaks in the message body", () => {
    expect(validateContact({ ...GOOD, message: "Line one\nLine two" })).toBeNull();
  });
});

describe("contactReducer", () => {
  it("starts empty and idle", () => {
    expect(initialState).toEqual({ values: EMPTY_VALUES, status: "idle", outcome: null });
  });

  it("updates one field at a time", () => {
    const next = contactReducer(initialState, { type: "change", field: "name", value: "Asha" });
    expect(next.values).toEqual({ ...EMPTY_VALUES, name: "Asha" });
  });

  it("goes to 'sending' on submit and clears any earlier message", () => {
    const failed = { ...initialState, status: "error" as const, outcome: "failed" as const };
    const next = contactReducer(failed, { type: "submit" });
    expect(next.status).toBe("sending");
    expect(next.outcome).toBeNull();
  });

  it("clears the form on success and keeps the success outcome", () => {
    const filled = { values: GOOD, status: "sending" as const, outcome: null };
    const next = contactReducer(filled, { type: "result", outcome: "sent" });
    expect(next).toEqual({ values: EMPTY_VALUES, status: "sent", outcome: "sent" });
  });

  it.each(["invalid", "rate_limited", "send_failed", "unavailable", "failed"] as const)(
    "keeps what the visitor typed after '%s', so they can try again",
    (outcome) => {
      const filled = { values: GOOD, status: "sending" as const, outcome: null };
      const next = contactReducer(filled, { type: "result", outcome });
      expect(next.values).toEqual(GOOD);
      expect(next.status).toBe("error");
      expect(next.outcome).toBe(outcome);
    },
  );

  it("ignores a second submit while one is already sending", () => {
    const sending = { values: GOOD, status: "sending" as const, outcome: null };
    expect(contactReducer(sending, { type: "submit" })).toBe(sending);
  });
});
