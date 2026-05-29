/// <reference types="mdx" />

// `@types/mdx` ships ambient `declare module "*.mdx"` types, but our
// tsconfig only includes `**/*.ts` / `**/*.tsx`, so the package's
// declarations aren't auto-picked up. This triple-slash reference pulls
// them into the project so the `import GettingStarted from "...mdx"`
// statements in `app/(marketing)/docs/[slug]/page.tsx` type-check.
//
// Mirrors the pattern in `types/css.d.ts` (which does the same for
// side-effect CSS imports).
export {};
