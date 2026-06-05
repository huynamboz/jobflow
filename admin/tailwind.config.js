import { heroui } from "@heroui/theme";

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/layouts/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./node_modules/@heroui/theme/dist/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  darkMode: "class",
  plugins: [
    heroui({
      // Radii match NODE's --r-* scale (see admin/src/styles/node-tokens.css):
      //   small=10px (asset card), medium=12px (default button/input), large=20px (card outer)
      layout: {
        radius: {
          small: "10px",
          medium: "12px",
          large: "16px",
        },
      },
      // Map HeroUI semantic colors to NODE accents.
      // Spec 004 — values mirror node-tokens.css.
      themes: {
        light: {
          colors: {
            background: "#f8fafc",                          // slate-50 page bg
            foreground: "#0f172a",                          // slate-900 ink
            primary: {
              DEFAULT: "#167a7a",                           // howard brand teal
              foreground: "#ffffff",
            },
            success: {
              DEFAULT: "#15803d",                           // emerald-700
              foreground: "#ffffff",
            },
            warning: {
              DEFAULT: "#efbe2c",                           // howard accent yellow
              foreground: "#0f172a",
            },
            danger: {
              DEFAULT: "#dc2626",                           // red-600
              foreground: "#ffffff",
            },
            secondary: {
              DEFAULT: "#0f172a",                           // slate-900 dark CTA
              foreground: "#f8fafc",
            },
            default: {
              DEFAULT: "#f1f5f9",                           // slate-100
              foreground: "#0f172a",
            },
          },
        },
      },
    }),
  ],
};
