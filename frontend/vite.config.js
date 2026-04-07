import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const isBuild = process.env.npm_lifecycle_event === "build";
const base = process.env.VITE_BASE || (isBuild ? "/ui/" : "/");

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port: 5173,
  },
});
