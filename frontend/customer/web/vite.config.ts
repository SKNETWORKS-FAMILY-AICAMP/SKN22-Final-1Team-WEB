import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  root: ".",
  base: "./",
  plugins: [react()],
  resolve: {
    alias: {
      "@/components": path.resolve(__dirname, "components"),
      "@/pages": path.resolve(__dirname, "pages")
    }
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, "src/main.tsx"),
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]"
      }
    }
  }
});
