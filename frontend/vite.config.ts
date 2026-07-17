import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Backend from `docker compose up` serves plain HTTP on :8000 (the app
        // no longer terminates TLS locally - that's the infra's job on GKE).
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
