
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget =
  process.env.AGORA_BACKEND_PROXY_TARGET ||
  "http://127.0.0.1:8000";

const apiProxy = {
  "/api": {
    target: backendTarget,
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [react()],

  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    proxy: apiProxy,

    watch: {
      usePolling:
        process.env.VITE_USE_POLLING === "true",
    },
  },

  preview: {
    host: "0.0.0.0",
    port: 4173,
  },
});
