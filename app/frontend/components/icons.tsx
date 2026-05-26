/** Inline-SVG icon set, sized via Tailwind on the wrapper.
 * Stroke-based, currentColor — same conventions as Lucide. */

type IP = React.SVGProps<SVGSVGElement>;
const base = "currentColor";

const Stroke = ({ children, ...p }: IP & { children: React.ReactNode }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke={base} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}>
    {children}
  </svg>
);

export const Icon = {
  Search:    (p: IP) => <Stroke {...p}><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></Stroke>,
  Plus:      (p: IP) => <Stroke {...p}><path d="M12 5v14M5 12h14" /></Stroke>,
  Upload:    (p: IP) => <Stroke {...p}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" /></Stroke>,
  Download:  (p: IP) => <Stroke {...p}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" /></Stroke>,
  TrendUp:   (p: IP) => <Stroke {...p} strokeWidth="2.5"><path d="M7 17l5-5 5 5M7 7l5 5 5-5" /></Stroke>,
  ArrowLeft: (p: IP) => <Stroke {...p}><path d="M19 12H5M12 19l-7-7 7-7" /></Stroke>,
  X:         (p: IP) => <Stroke {...p}><path d="M18 6 6 18M6 6l12 12" /></Stroke>,
  Check:     (p: IP) => <Stroke {...p} strokeWidth="3"><path d="M5 12l5 5 9-11" /></Stroke>,
  Bell:      (p: IP) => <Stroke {...p}><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21a2 2 0 0 0 4 0" /></Stroke>,
  Help:      (p: IP) => <Stroke {...p}><circle cx="12" cy="12" r="10" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.8.4-1 .9-1 1.7M12 17h.01" /></Stroke>,
  Image:     (p: IP) => <Stroke {...p}><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-5-5L5 21" /></Stroke>,
  Filter:    (p: IP) => <Stroke {...p}><path d="M3 6h18M6 12h12M10 18h4" /></Stroke>,
  Sliders:   (p: IP) => <Stroke {...p}><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" /></Stroke>,
  Grid:      (p: IP) => <Stroke {...p}><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></Stroke>,
  Rows:      (p: IP) => <Stroke {...p}><path d="M3 6h18M3 12h18M3 18h18" /></Stroke>,
  Clock:     (p: IP) => <Stroke {...p}><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></Stroke>,
  Folder:    (p: IP) => <Stroke {...p}><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /></Stroke>,
  Wave:      (p: IP) => <Stroke {...p}><path d="M3 12h2l3 8 4-16 3 8h6" /></Stroke>,
  Target:    (p: IP) => <Stroke {...p}><circle cx="12" cy="12" r="9" /><path d="M12 3v18M3 12h18" /></Stroke>,
  Brand:     (p: IP) => (
    <svg viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M5 4 H19 V8 L12 9.5 L5 8 Z" fill="currentColor" opacity="0.95" />
      <path d="M11 9 H13 V20 H11 Z" fill="currentColor" opacity="0.95" />
    </svg>
  ),
};
