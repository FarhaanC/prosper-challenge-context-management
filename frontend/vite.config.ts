// Vite builds the editor into frontend/dist, which the voice agent (bot.py) serves at /editor.
// While developing (npm run dev, on port 5173), requests to /api go to the running agent on 7860.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/editor/",
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:7860" } },
});
