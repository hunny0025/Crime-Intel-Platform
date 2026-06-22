import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // BACKGROUND LAYERS (layered depth system)
        obsidian: "#080A0D",
        base: "#0D0F13",
        surface: "#12151A",
        elevated: "#171B22",
        overlay: "#1E222B",
        border: "#252A34",
        "border-subtle": "#1A1E26",

        // ACCENT COLORS (intelligence-semantic only)
        "intel-blue": "#4A9EFF",
        "intel-blue-dim": "#1E3A5F",
        "intel-green": "#2DD4BF",
        "intel-green-dim": "#0D3330",
        "intel-amber": "#F59E0B",
        "intel-amber-dim": "#3D2800",
        "intel-red": "#F43F5E",
        "intel-red-dim": "#3D0A14",
        "intel-purple": "#A78BFA",
        "intel-purple-dim": "#2D1B5E",
        "intel-cyan": "#22D3EE",
        "intel-cyan-dim": "#0A2D36",
        "intel-magenta": "#E879F9",
        "intel-magenta-dim": "#3D0A44",

        // TEXT HIERARCHY
        "text-primary": "#E8EAF0",
        "text-secondary": "#8B9AB8",
        "text-muted": "#4A5568",
        "text-accent": "#4A9EFF",

        // shadcn/ui mapping
        background: "#0D0F13", // base
        foreground: "#E8EAF0", // text-primary
        card: {
          DEFAULT: "#12151A", // surface
          foreground: "#E8EAF0", // text-primary
        },
        popover: {
          DEFAULT: "#1E222B", // overlay
          foreground: "#E8EAF0", // text-primary
        },
        primary: {
          DEFAULT: "#4A9EFF", // intel-blue
          foreground: "#080A0D", // obsidian
        },
        secondary: {
          DEFAULT: "#171B22", // elevated
          foreground: "#E8EAF0",
        },
        muted: {
          DEFAULT: "#171B22",
          foreground: "#8B9AB8", // text-secondary
        },
        accent: {
          DEFAULT: "#1E222B",
          foreground: "#4A9EFF", // text-accent
        },
        destructive: {
          DEFAULT: "#F43F5E", // intel-red
          foreground: "#E8EAF0",
        },
        ring: "#4A9EFF",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;

