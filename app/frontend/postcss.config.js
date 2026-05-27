// Tailwind v4 moved its PostCSS plugin to a separate package. Also ships
// vendor-prefix handling built-in, so autoprefixer is redundant under v4
// and removed here (one fewer dep, one fewer thing to keep current).
module.exports = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
