import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/Malifaux4E_GAME356/", // repo name
  build: {
    outDir: "../docs",
    emptyOutDir: true,
  },
});
