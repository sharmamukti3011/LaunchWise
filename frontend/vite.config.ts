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
    // /s/<slug> pages are served by the backend, like /api.
    proxy: { "/api": "http://localhost:8000", "/s": "http://localhost:8000" },
  },
});
