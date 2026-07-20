import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        canvas:  "rgb(var(--canvas)  / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        raised:  "rgb(var(--raised)  / <alpha-value>)",
        rim:     "rgb(var(--rim)     / <alpha-value>)",
        seam:    "rgb(var(--seam)    / <alpha-value>)",
        ink:     "rgb(var(--ink)     / <alpha-value>)",
        sub:     "rgb(var(--sub)     / <alpha-value>)",
        muted:   "rgb(var(--muted)   / <alpha-value>)",
        hint:    "rgb(var(--hint)    / <alpha-value>)",
        accent:  "rgb(var(--accent)  / <alpha-value>)",
      },
    },
  },
  plugins: [],
} satisfies Config;
