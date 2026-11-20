import { describe, expect, it } from "vitest";
import config from "../vite.config";

// Vite matches a proxy key as a prefix, or as a regular expression when it starts with "^".
function proxied(path: string): boolean {
  const keys = Object.keys(config.server?.proxy ?? {});
  return keys.some((key) => (key.startsWith("^") ? new RegExp(key).test(path) : path.startsWith(key)));
}

describe("dev server proxy", () => {
  it.each(["/api/health", "/api/storefront/preview", "/s/example-pune-cakes", "/s/"])(
    "sends %s to the backend",
    (path) => {
      expect(proxied(path)).toBe(true);
    },
  );

  // These all start with "/s" or "/a": a bare prefix key would swallow them and blank the page.
  it.each([
    "/",
    "/src/main.tsx",
    "/src/index.css",
    "/site.webmanifest",
    "/@vite/client",
    "/@react-refresh",
    "/node_modules/.vite/deps/react.js",
    "/assets/main.js",
    "/favicon.ico",
    "/favicon-32.png",
    "/apple-touch-icon.png",
    "/icon-192.png",
    "/brand/launchwise-logo.png",
    "/404.html",
    "/sandbox",
    "/s",
  ])("serves %s itself", (path) => {
    expect(proxied(path)).toBe(false);
  });
});
