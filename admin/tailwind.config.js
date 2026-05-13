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
          large: "20px",
        },
      },
      // Map HeroUI semantic colors to NODE accents.
      // Spec 004 — values mirror node-tokens.css.
      themes: {
        light: {
          colors: {
            background: "#fcfcfc",                          // --bg / --c1
            foreground: "#121212",                          // --ink / --c9
            primary: {
              DEFAULT: "#3582ff",                           // --blue
              foreground: "#ffffff",
            },
            success: {
              DEFAULT: "#49ba61",                           // --green
              foreground: "#ffffff",
            },
            warning: {
              DEFAULT: "#ffb73a",                           // --yellow
              foreground: "#121212",
            },
            danger: {
              DEFAULT: "#fe5938",                           // --red
              foreground: "#ffffff",
            },
            secondary: {
              DEFAULT: "#8755e9",                           // --purple
              foreground: "#ffffff",
            },
            default: {
              DEFAULT: "#f1f1f1",                           // --c3 / --sunken
              foreground: "#121212",
            },
          },
        },
      },
    }),
  ],
};
