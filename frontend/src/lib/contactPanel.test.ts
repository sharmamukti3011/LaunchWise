import { describe, expect, it, vi } from "vitest";
import {
  OPEN_CONTACT_EVENT,
  initialPanelState,
  isContactHash,
  panelReducer,
  requestContactOpen,
  revealContact,
} from "./contactPanel";

describe("isContactHash", () => {
  it("matches only #contact", () => {
    expect(isContactHash("#contact")).toBe(true);
    for (const other of ["", "#", "#contacts", "#contact-form", "#demo", "contact", "#Contact"]) {
      expect(isContactHash(other)).toBe(false);
    }
  });
});

describe("initialPanelState", () => {
  it("is collapsed by default", () => {
    expect(initialPanelState("")).toEqual({ open: false, requests: 0 });
    expect(initialPanelState("#demo")).toEqual({ open: false, requests: 0 });
  });

  it("starts expanded, with a reveal pending, when the page opens with #contact", () => {
    expect(initialPanelState("#contact")).toEqual({ open: true, requests: 1 });
  });
});

describe("panelReducer", () => {
  const closed = { open: false, requests: 0 };

  it("opens, and counts the request so the form is revealed", () => {
    expect(panelReducer(closed, { type: "open" })).toEqual({ open: true, requests: 1 });
  });

  it("counts a second open request even when already open, so a repeat click scrolls again", () => {
    const once = panelReducer(closed, { type: "open" });
    expect(panelReducer(once, { type: "open" })).toEqual({ open: true, requests: 2 });
  });

  it("closes without asking for a reveal", () => {
    const open = { open: true, requests: 3 };
    expect(panelReducer(open, { type: "close" })).toEqual({ open: false, requests: 3 });
  });

  it("opens when the hash becomes #contact and ignores any other hash", () => {
    expect(panelReducer(closed, { type: "hash", hash: "#contact" })).toEqual({
      open: true,
      requests: 1,
    });
    expect(panelReducer(closed, { type: "hash", hash: "#demo" })).toBe(closed);
    const open = { open: true, requests: 1 };
    expect(panelReducer(open, { type: "hash", hash: "" })).toBe(open); // never closes on its own
  });
});

describe("requestContactOpen", () => {
  it("tells the page to open the contact form", () => {
    const target = new EventTarget();
    const listener = vi.fn();
    target.addEventListener(OPEN_CONTACT_EVENT, listener);
    requestContactOpen(target);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe("revealContact", () => {
  it("scrolls the section into view, then moves focus to the first field", () => {
    const order: string[] = [];
    const section = { scrollIntoView: vi.fn(() => order.push("scroll")) };
    const field = { focus: vi.fn(() => order.push("focus")) };
    revealContact(section, field);
    expect(order).toEqual(["scroll", "focus"]);
    expect(section.scrollIntoView).toHaveBeenCalledWith({ block: "start" });
    // Focus must not scroll again and undo the scroll above.
    expect(field.focus).toHaveBeenCalledWith({ preventScroll: true });
  });

  it("does nothing when the elements are not there yet", () => {
    expect(() => revealContact(null, null)).not.toThrow();
  });
});
