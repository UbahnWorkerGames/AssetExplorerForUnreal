import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const isBuild = process.env.npm_lifecycle_event === "build";
const base = process.env.VITE_BASE || (isBuild ? "/ui/" : "/");
const backendTarget = (process.env.VITE_API_BASE || process.env.ASSET_API_BASE || "http://127.0.0.1:7985").replace(/\/$/, "");
const proxyPaths = ["/events", "/logs", "/settings", "/tasks", "/queue", "/projects", "/assets", "/llm", "/server", "/admin", "/tags", "/openai"];

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxyPaths.map((path) => [
        path,
        {
          target: backendTarget,
          changeOrigin: true,
          secure: false,
        },
      ]),
    ),
  },
});
