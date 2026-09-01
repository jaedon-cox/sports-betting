import type { Config } from "tailwindcss";

/**
 * Tokens are doc §4.2 verbatim. Nothing else is allowed into this palette:
 * the aesthetic brief is "restraint everywhere except one signature moment,"
 * and a sixth accent colour is how that erodes.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0E1A17",
        surface: "#16241F",
        // One derived step above Surface, for hover/nested panels only.
        raised: "#1C2E27",
        chalk: "#F2EEE3",
        floodlight: "#E8A33D",
        turf: "#4E9F76",
        clay: "#C15B3E",
      },
      fontFamily: {
        display: ["var(--font-display)", "Impact", "sans-serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        placard: "0.18em",
      },
      borderRadius: {
        // Scoreboards are not rounded. 2px is the whole vocabulary.
        DEFAULT: "2px",
      },
      maxWidth: {
        ledger: "78rem",
      },
    },
  },
  plugins: [],
};

export default config;
