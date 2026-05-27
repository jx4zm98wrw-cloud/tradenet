// Ambient declaration for CSS side-effect imports (e.g. `import './globals.css'`
// in app/layout.tsx). Required under TypeScript 6.x — previous versions
// allowed un-typed side-effect imports silently, but 6.0 enforces a module
// declaration. Next.js's bundler handles the actual CSS at build time;
// this just satisfies the type checker.
declare module "*.css";
