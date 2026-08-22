import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        obsidian: {
          950: "#05070a", // Deepest background
          900: "#0a0e16", // Panel base
          850: "#0f1523", // Card surface
          800: "#172133", // Elevated border
          750: "#1e2b42", // Hover highlight
          700: "#273854", // Active border
          600: "#3b5278", // Subdued text
        },
        hud: {
          cyan: "#00f5d4",
          "cyan-dim": "rgba(0, 245, 212, 0.15)",
          emerald: "#10b981",
          "emerald-dim": "rgba(16, 185, 129, 0.15)",
          amber: "#f59e0b",
          "amber-dim": "rgba(245, 158, 11, 0.15)",
          violet: "#a855f7",
          "violet-dim": "rgba(168, 85, 247, 0.15)",
          ruby: "#f43f5e",
          "ruby-dim": "rgba(244, 63, 94, 0.15)",
          blue: "#3b82f6",
          "blue-dim": "rgba(59, 130, 246, 0.15)",
        },
      },
      fontFamily: {
        sans: ["var(--font-outfit)", "system-ui", "sans-serif"],
        display: ["var(--font-space-grotesk)", "var(--font-outfit)", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
      boxShadow: {
        "glow-cyan": "0 0 20px -3px rgba(0, 245, 212, 0.4)",
        "glow-emerald": "0 0 20px -3px rgba(16, 185, 129, 0.4)",
        "glow-amber": "0 0 20px -3px rgba(245, 158, 11, 0.4)",
        "glow-violet": "0 0 20px -3px rgba(168, 85, 247, 0.4)",
        "glow-ruby": "0 0 20px -3px rgba(244, 63, 94, 0.4)",
      },
      animation: {
        "radar-sweep": "radar-sweep 4s linear infinite",
        "radar-pulse": "radar-pulse 2s cubic-bezier(0, 0, 0.2, 1) infinite",
        "scanline-sweep": "scanline-sweep 8s linear infinite",
        "pulse-subtle": "pulse-subtle 2s ease-in-out infinite",
        "glow-cycle": "glow-cycle 3s ease-in-out infinite",
      },
      keyframes: {
        "radar-sweep": {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        "radar-pulse": {
          "0%": { transform: "scale(0.8)", opacity: "0.9" },
          "70%": { transform: "scale(2.2)", opacity: "0" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
        "scanline-sweep": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(1000%)" },
        },
        "pulse-subtle": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        "glow-cycle": {
          "0%, 100%": { filter: "drop-shadow(0 0 8px rgba(0,245,212,0.6))" },
          "50%": { filter: "drop-shadow(0 0 16px rgba(0,245,212,0.9))" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
