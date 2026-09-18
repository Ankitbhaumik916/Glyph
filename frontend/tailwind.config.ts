import type { Config } from "tailwindcss";

/** Colours sampled from the hero video: storm greys with a warm amber shaft. */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#07090d",
        "ink-soft": "#0d1117",
        haze: "#161c25",
        mist: "#232c38",
        amber: {
          200: "#ffe2b0",
          300: "#ffcf85",
          400: "#f8b55c",
          500: "#e79a3c",
          600: "#c47a28",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "Helvetica", "Arial", "sans-serif"],
        display: ["Georgia", "Cambria", "Times New Roman", "serif"],
      },
      boxShadow: {
        glow: "0 0 60px -12px rgba(248, 181, 92, 0.45)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "none" },
        },
      },
      animation: {
        "fade-up": "fade-up 700ms ease both",
      },
    },
  },
  plugins: [],
};

export default config;
