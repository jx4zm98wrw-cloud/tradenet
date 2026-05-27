/**
 * ESLint 9 flat config — replaces .eslintrc.json (legacy format).
 *
 * Next.js's bundled `eslint-config-next` is still authored in legacy
 * (`extends:` style) shape as of 15.x. `FlatCompat` from `@eslint/eslintrc`
 * bridges legacy configs into flat-config arrays — the migration path
 * documented in both the ESLint 9 release notes and the Next.js
 * upgrade guide.
 *
 * Once eslint-config-next ships first-class flat config (likely 16.x),
 * the FlatCompat indirection can be removed in favor of direct imports.
 */
import { FlatCompat } from "@eslint/eslintrc";
import { dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: __dirname });

export default [
  {
    // Flat config uses gitignore-style globs (trailing /** is required for
    // directory matching; the legacy "tests/e2e/" implicit-dir match doesn't
    // carry over).
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "tests/e2e/**",
      "playwright.config.ts",
    ],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Next.js' <Image> is preferred, but our app renders user-supplied
      // logo PNGs by absolute path — <img> is the right tool for that case.
      "@next/next/no-img-element": "off",
      // Allow `_arg` and `_var` to silence unused-var warnings (matches
      // the `_`-prefix convention codified in worker/ingest.py).
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/no-explicit-any": "warn",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
];
