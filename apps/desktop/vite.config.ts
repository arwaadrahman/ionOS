import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const apiOrigin = process.env.VITE_ION_API_ORIGIN ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  define: {
    __ION_API_ORIGIN__: JSON.stringify(apiOrigin),
  },
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
  },
});
