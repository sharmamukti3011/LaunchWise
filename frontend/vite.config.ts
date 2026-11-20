import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // Two pages: the app, and the 404 page that Caddy shows for any other address.
    rollupOptions: { input: { main: "index.html", notFound: "404.html" } },
  },
  server: {
    // /api and the /s/<slug> starter pages are served by the backend. A key that starts with "^"
    // is a regular expression; a plain "/s" would be a prefix and swallow /src/main.tsx,
    // /site.webmanifest and every other path that starts with "/s", which blanks the page.
    proxy: { "^/(api|s)/": "http://localhost:8000" },
  },
});
