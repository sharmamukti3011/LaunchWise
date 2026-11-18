import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("page layout", () => {
  const html = renderToStaticMarkup(<App />);

  it("is a full-height flex column, with the main area growing and the footer last", () => {
    const wrapper = /^<div class="([^"]*)"/.exec(html)?.[1].split(" ") ?? [];
    expect(wrapper).toEqual(expect.arrayContaining(["flex", "flex-col", "min-h-screen"]));
    expect(html).toMatch(/<main class="[^"]*\bflex-1\b/);
    expect(html.indexOf("<main")).toBeLessThan(html.indexOf("<footer"));
    expect(html.endsWith("</footer></div>")).toBe(true);
  });

  it("keeps the footer full width so it does not shrink to its text", () => {
    expect(html).toMatch(/<footer class="[^"]*\bw-full\b/);
  });

  it("does not pin the footer with fixed or sticky positioning", () => {
    expect(html).not.toMatch(/\b(fixed|sticky|absolute)\b/);
  });
});
