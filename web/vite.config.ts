import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In sviluppo (npm run dev) le chiamate /api vanno al backend FastAPI su :8765.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: true } },
  },
  build: { outDir: "dist", chunkSizeWarningLimit: 1200 },
});
