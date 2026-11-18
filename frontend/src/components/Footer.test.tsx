import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Footer } from "./Footer";

describe("Footer", () => {
  const html = renderToStaticMarkup(<Footer />);

  it("says where it is hosted and what it is built with", () => {
    expect(html).toContain("Hosted on GoDaddy · Built with Claude");
  });

  it("has a contact link to #contact (the form comes next)", () => {
    expect(html).toMatch(/<a[^>]*href="#contact"[^>]*>Contact<\/a>/);
  });

  it("still points at #contact, which the page turns into 'expand and scroll'", () => {
    expect(html).toContain('href="#contact"');
  });

  it("is a landmark footer and opens no external pages", () => {
    expect(html.startsWith("<footer")).toBe(true);
    expect(html).not.toContain("target=");
  });
});
