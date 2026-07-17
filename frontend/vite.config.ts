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
        // Backend from `docker compose up` serves HTTPS on :8443 (self-signed
        // cert by default, hence secure: false).
        target: "https://localhost:8443",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
