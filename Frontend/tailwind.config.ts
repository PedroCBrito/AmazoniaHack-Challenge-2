import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F2F0E6",
        ink: "#1F2A1F",
        forest: { DEFAULT: "#2F5233", light: "#6B8F71" },
        amber: "#B8862B",
        clay: "#9C3D34",
        line: "#D8D3C4",
      },
      fontFamily: {
        serif: ["'Source Serif 4'", "Georgia", "serif"],
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;