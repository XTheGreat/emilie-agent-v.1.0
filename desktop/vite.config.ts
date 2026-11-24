import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";

// The UI is built into the Python package (emilie/desktop/web), so the local server can serve it without Node.
// `npm run dev` serves it with hot reload instead; start the server with:
//   python -m emilie.desktop --port 47321 --token dev     then open http://localhost:5173/?token=dev
const hub = process.env.EMILIE_HUB || "http://127.0.0.1:47321";

export default defineConfig({
  root: fileURLToPath(new URL("./ui", import.meta.url)),
  base: "/",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./ui/src", import.meta.url)) } },
  build: {
    outDir: fileURLToPath(new URL("../emilie/desktop/web", import.meta.url)),
    emptyOutDir: true,
    target: "chrome120",
    chunkSizeWarningLimit: 4000,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: hub, changeOrigin: true },
      "/media": { target: hub, changeOrigin: true },
    },
  },
});
