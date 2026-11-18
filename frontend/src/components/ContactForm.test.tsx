import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CONTACT_TEXT } from "../api/contact";
import { EMPTY_VALUES, initialState } from "../lib/contactForm";
import type { ContactState } from "../lib/contactForm";
import { ContactFormView } from "./ContactForm";

const noop = () => undefined;
// The attribute, not the Tailwind class "disabled:opacity-60".
const DISABLED_BUTTON = /<button[^>]*\sdisabled(=|\s|>)/;

function render(state: ContactState = initialState, open = true): string {
  return renderToStaticMarkup(
    <ContactFormView state={state} open={open} onToggle={noop} onChange={noop} onSubmit={noop} />,
  );
}

describe("ContactFormView", () => {
  it("is a section with id='contact' so the footer link works", () => {
    expect(render()).toMatch(/<section[^>]*id="contact"/);
  });

  it("has name, email and message fields with labels, and the right limits", () => {
    const html = render();
    expect(html).toMatch(/<label[^>]*for="contact-name"/);
    expect(html).toMatch(/<input[^>]*id="contact-name"[^>]*maxLength="100"|<input[^>]*maxLength="100"[^>]*id="contact-name"/);
    expect(html).toMatch(/<input[^>]*type="email"/);
    expect(html).toMatch(/<textarea[^>]*maxLength="2000"/);
    expect(html).toContain('maxLength="254"');
    expect(html).toContain("required");
  });

  it("hides the honeypot from sighted users and screen readers and keeps it out of the tab order", () => {
    const html = render();
    const wrapper = /<div[^>]*aria-hidden="true"[^>]*>(.*?)<\/div>/s.exec(html);
    expect(wrapper).not.toBeNull();
    const trap = wrapper?.[0] ?? "";
    expect(trap).toContain('name="website"');
    expect(trap).toContain('tabindex="-1"');
    expect(trap).toContain('autoComplete="off"');
    expect(trap).toMatch(/class="[^"]*-left-\[9999px\]/); // off-screen, not display:none
    expect(trap).not.toContain("required");
  });

  it("enables the button when idle", () => {
    const html = render();
    expect(html).toMatch(/<button[^>]*type="submit"/);
    expect(html).not.toMatch(DISABLED_BUTTON);
    expect(html).toContain("Send message");
  });

  it("disables the button and says so while sending", () => {
    const html = render({ values: EMPTY_VALUES, status: "sending", outcome: null });
    expect(html).toMatch(DISABLED_BUTTON);
    expect(html).toContain("Sending…");
    expect(html).toContain('aria-busy="true"');
  });

  it("shows the fixed success message as a status", () => {
    const html = render({ values: EMPTY_VALUES, status: "sent", outcome: "sent" });
    expect(html).toContain(CONTACT_TEXT.sent);
    expect(html).toMatch(/role="status"/);
  });

  it.each(["invalid", "rate_limited", "send_failed", "unavailable", "failed"] as const)(
    "shows the fixed error message for '%s' as an alert",
    (outcome) => {
      const html = render({ values: EMPTY_VALUES, status: "error", outcome });
      expect(html).toContain(CONTACT_TEXT[outcome]);
      expect(html).toMatch(/role="alert"/);
      expect(html).not.toMatch(DISABLED_BUTTON);
    },
  );

  it("shows what the visitor typed, escaped, and never as markup", () => {
    const values = { ...EMPTY_VALUES, name: "<img src=x onerror=alert(1)>", message: "<b>hi</b>" };
    const html = render({ values, status: "error", outcome: "failed" });
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<b>hi</b>");
    expect(html).toContain("&lt;img");
  });
});


describe("collapsed by default", () => {
  const collapsed = render(initialState, false);
  const expanded = render(initialState, true);

  it("keeps id='contact' on the section so the footer link has a target", () => {
    expect(collapsed).toMatch(/<section[^>]*id="contact"/);
  });

  it("shows a small 'Contact us' section with one line of text and a 'Write to us' button", () => {
    expect(collapsed).toContain("Contact us");
    expect(collapsed).toContain("Write to us");
    expect(collapsed.match(/<p\b/g)).toHaveLength(1);
  });

  it("has a real toggle button: type=button, aria-expanded=false, controlling the form", () => {
    const button = /<button[^>]*aria-expanded="false"[^>]*>/.exec(collapsed)?.[0] ?? "";
    expect(button).toContain('type="button"');
    expect(button).toContain('aria-controls="contact-form-panel"');
    expect(collapsed).toMatch(/<div[^>]*id="contact-form-panel"[^>]*\shidden(=|\s|>)/);
  });

  it("expands: aria-expanded=true and the form is no longer hidden", () => {
    expect(expanded).toMatch(/<button[^>]*aria-expanded="true"/);
    expect(expanded).not.toMatch(/<div[^>]*id="contact-form-panel"[^>]*\shidden(=|\s|>)/);
    expect(expanded).toContain("Hide form");
  });

  it("keeps the honeypot in the form, hidden from sighted users and screen readers", () => {
    for (const html of [collapsed, expanded]) {
      expect(html).toMatch(/aria-hidden="true"[^>]*>\s*<label[^>]*>Leave this field empty/);
      expect(html).toContain('tabindex="-1"');
    }
  });

  it("keeps the success message visible after a send, even when the form is collapsed", () => {
    const sent = { values: EMPTY_VALUES, status: "sent" as const, outcome: "sent" as const };
    const html = render(sent, false);
    expect(html).toContain(CONTACT_TEXT.sent);
    expect(html).toMatch(/role="status"/);
    // Outside the hidden form, so collapsing does not hide it.
    expect(html.indexOf(CONTACT_TEXT.sent)).toBeLessThan(html.indexOf('id="contact-form-panel"'));
  });

  it("keeps a draft in the form while it is collapsed", () => {
    const draft = { ...EMPTY_VALUES, name: "Asha" };
    const html = render({ values: draft, status: "idle", outcome: null }, false);
    expect(html).toContain('value="Asha"');
  });
});
