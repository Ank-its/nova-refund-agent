import type { Config } from "tailwindcss";

// Palette mirrors Worknoon's design language: minimalist black/white,
// near-black ink (#0a0a0a), soft neutral greys, generous rounding.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0a0a0a",
        canvas: "#ffffff",
        muted: "#6b7280",
        line: "#e5e7eb",
        soft: "#f7f7f8",
        approve: "#16a34a",
        reject: "#dc2626",
        review: "#d97706",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      borderRadius: {
        xl: "14px",
        "2xl": "16px",
      },
    },
  },
  plugins: [],
};

export default config;
