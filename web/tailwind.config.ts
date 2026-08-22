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
          950: "#060c07", // Deepest background
          900: "#0a140b", // Panel base
          850: "#0f1d10", // Card surface
          800: "#1a2e18", // Elevated border
          750: "#24401f", // Hover highlight
          700: "#2f5227", // Active border
          600: "#4a7040", // Subdued text
        },
        hud: {
          cyan: "#a8d5e2",
          "cyan-dim": "rgba(168, 213, 226, 0.15)",
          emerald: "#7cb851",
          "emerald-dim": "rgba(124, 184, 81, 0.15)",
          amber: "#f9a620",
          "amber-dim": "rgba(249, 166, 32, 0.15)",
          violet: "#ffd449",
          "violet-dim": "rgba(255, 212, 73, 0.15)",
          ruby: "#ef5b38",
          "ruby-dim": "rgba(239, 91, 56, 0.15)",
          blue: "#7fbdd0",
          "blue-dim": "rgba(127, 189, 208, 0.15)",
        },
        // Default Tailwind families remapped onto the palette so existing
        // slate/sky/purple/emerald/amber/rose classes stay on-theme.
        slate: {
          50: "#f2f7f3", 100: "#e3ede4", 200: "#c6d8c8", 300: "#a3bda6",
          400: "#7d9a81", 500: "#5d7a61", 600: "#46604a", 700: "#35503a",
          800: "#24382a", 900: "#16261b", 950: "#0c170f",
        },
        sky: {
          50: "#f0f8fb", 100: "#ddeff5", 200: "#c3e2ec", 300: "#a8d5e2",
          400: "#7fbdd0", 500: "#57a1b8", 600: "#3f8298", 700: "#34687a",
          800: "#2d5563", 900: "#284754", 950: "#172e38",
        },
        emerald: {
          50: "#f2f9ec", 100: "#e2f2d5", 200: "#c6e5ae", 300: "#a1d27d",
          400: "#7cb851", 500: "#548c2f", 600: "#427024", 700: "#34571f",
          800: "#2c461d", 900: "#263c1c", 950: "#10240a",
        },
        green: {
          50: "#f2f9ec", 100: "#e2f2d5", 200: "#c6e5ae", 300: "#a1d27d",
          400: "#7cb851", 500: "#548c2f", 600: "#427024", 700: "#34571f",
          800: "#2c461d", 900: "#263c1c", 950: "#104911",
        },
        amber: {
          50: "#fffaeb", 100: "#fff2c6", 200: "#ffe488", 300: "#ffd449",
          400: "#fdbe24", 500: "#f9a620", 600: "#dd7d0a", 700: "#b7580c",
          800: "#944511", 900: "#7a3a11", 950: "#461c04",
        },
        yellow: {
          50: "#fffaeb", 100: "#fff2c6", 200: "#ffe488", 300: "#ffd449",
          400: "#fdbe24", 500: "#f9a620", 600: "#dd7d0a", 700: "#b7580c",
          800: "#944511", 900: "#7a3a11", 950: "#461c04",
        },
        purple: {
          50: "#fefbe8", 100: "#fff8c2", 200: "#ffee87", 300: "#ffd449",
          400: "#fdc116", 500: "#eda703", 600: "#cc7f01", 700: "#a35a05",
          800: "#86470c", 900: "#723a10", 950: "#431d02",
        },
        violet: {
          50: "#fefbe8", 100: "#fff8c2", 200: "#ffee87", 300: "#ffd449",
          400: "#fdc116", 500: "#eda703", 600: "#cc7f01", 700: "#a35a05",
          800: "#86470c", 900: "#723a10", 950: "#431d02",
        },
        rose: {
          50: "#fef4f2", 100: "#fee5df", 200: "#fecfc4", 300: "#fcae9c",
          400: "#f88163", 500: "#ef5b38", 600: "#dc3e1c", 700: "#b92f14",
          800: "#992a15", 900: "#7f2818", 950: "#451007",
        },
        red: {
          50: "#fef4f2", 100: "#fee5df", 200: "#fecfc4", 300: "#fcae9c",
          400: "#f88163", 500: "#ef5b38", 600: "#dc3e1c", 700: "#b92f14",
          800: "#992a15", 900: "#7f2818", 950: "#451007",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter-tight)", "system-ui", "sans-serif"],
        display: ["var(--font-bricolage)", "var(--font-inter-tight)", "sans-serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        "glow-cyan": "0 0 20px -3px rgba(168, 213, 226, 0.4)",
        "glow-emerald": "0 0 20px -3px rgba(124, 184, 81, 0.4)",
        "glow-amber": "0 0 20px -3px rgba(249, 166, 32, 0.4)",
        "glow-violet": "0 0 20px -3px rgba(255, 212, 73, 0.4)",
        "glow-ruby": "0 0 20px -3px rgba(239, 91, 56, 0.4)",
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
          "0%, 100%": { filter: "drop-shadow(0 0 8px rgba(168,213,226,0.6))" },
          "50%": { filter: "drop-shadow(0 0 16px rgba(168,213,226,0.9))" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
