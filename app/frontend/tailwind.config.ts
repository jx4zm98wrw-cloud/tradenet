import type { Config } from "tailwindcss";

const tokenColor = (name: string) => `var(--${name})`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans:  ["var(--font-sans)", "system-ui", "sans-serif"],
        mono:  ["var(--font-mono)", "ui-monospace", "monospace"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
      },
      colors: {
        // Surfaces & ink
        paper:        tokenColor("paper"),
        "paper-2":    tokenColor("paper-2"),
        "paper-3":    tokenColor("paper-3"),
        surface:      tokenColor("surface"),
        line:         tokenColor("line"),
        "line-strong": tokenColor("line-strong"),
        ink:          tokenColor("ink"),
        "ink-2":      tokenColor("ink-2"),
        mute:         tokenColor("mute"),
        fade:         tokenColor("fade"),

        // Brand (themable via body[data-theme])
        stamp:        tokenColor("stamp"),
        "stamp-2":    tokenColor("stamp-2"),
        "stamp-line": tokenColor("stamp-line"),
        "stamp-deep": tokenColor("stamp-deep"),

        // Semantic
        ok:           tokenColor("ok"),
        "ok-2":       tokenColor("ok-2"),
        warn:         tokenColor("warn"),
        "warn-2":     tokenColor("warn-2"),

        // Backward-compat — existing pages still use `bg-brand-600` etc.
        // Aliases to oxblood tokens; will be removed once PRs #1-6 migrate pages.
        brand: {
          50:  "var(--stamp-2)",
          100: "var(--stamp-line)",
          200: "var(--stamp-line)",
          500: "var(--stamp)",
          600: "var(--stamp)",
          700: "var(--stamp-deep)",
          900: "var(--stamp-deep)",
        },
      },
      maxWidth: {
        container: "var(--container)",
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
    },
  },
  plugins: [],
};
export default config;
