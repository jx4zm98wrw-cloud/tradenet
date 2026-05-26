"use client";

/** Tweaks panel — runtime theming knobs that the design handoff README calls out:
 *
 *   - Brand swap:  oxblood (default) · teal · ink   (body[data-theme])
 *   - Density:     cozy (default) · compact · roomy (body[data-density])
 *   - Serif heads: on (default) · off               (body[data-serifheads])
 *
 * All three are CSS-only — the tokens are already defined in globals.css.
 * State persists to localStorage so reloads keep the user's choice. Mounted
 * once from RootLayout so it appears on every page.
 *
 * Defaults render server-side from layout.tsx's <body data-…> attributes;
 * this component re-applies any localStorage overrides on mount, so the SSR
 * theme briefly flashes only if the user has picked something different.
 */

import * as React from "react";
import { Icon } from "./icons";

type Theme = "oxblood" | "teal" | "ink";
type Density = "cozy" | "compact" | "roomy";

const STORAGE_KEY = "tm:tweaks";

type Tweaks = { theme: Theme; density: Density; serifHeads: boolean };

const DEFAULTS: Tweaks = { theme: "oxblood", density: "cozy", serifHeads: true };

function readStored(): Tweaks {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Tweaks>;
    return {
      theme: ["oxblood", "teal", "ink"].includes(parsed.theme as string)
        ? (parsed.theme as Theme)
        : DEFAULTS.theme,
      density: ["cozy", "compact", "roomy"].includes(parsed.density as string)
        ? (parsed.density as Density)
        : DEFAULTS.density,
      serifHeads: typeof parsed.serifHeads === "boolean" ? parsed.serifHeads : DEFAULTS.serifHeads,
    };
  } catch {
    return DEFAULTS;
  }
}

function applyToBody(t: Tweaks) {
  const b = document.body;
  b.setAttribute("data-theme", t.theme);
  b.setAttribute("data-density", t.density);
  b.setAttribute("data-serifheads", t.serifHeads ? "1" : "0");
}

export function TweaksPanel() {
  const [open, setOpen] = React.useState(false);
  const [tweaks, setTweaks] = React.useState<Tweaks>(DEFAULTS);

  // On mount: restore any saved preferences and apply to body.
  React.useEffect(() => {
    const stored = readStored();
    setTweaks(stored);
    applyToBody(stored);
  }, []);

  function update(patch: Partial<Tweaks>) {
    const next = { ...tweaks, ...patch };
    setTweaks(next);
    applyToBody(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // private mode / quota / disabled — silently fall back to in-memory
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        aria-label="Tweaks panel"
        title="Theme, density, typography"
        className="fixed bottom-4 right-4 z-40 w-9 h-9 grid place-items-center rounded-full bg-ink text-white shadow-md hover:bg-stamp transition"
      >
        <Icon.Sliders className="w-4 h-4" />
      </button>

      {open && (
        <div
          className="fixed bottom-16 right-4 z-50 w-64 bg-surface border border-line rounded-lg shadow-md overflow-hidden"
          role="dialog"
          aria-label="Tweaks"
        >
          <header className="px-4 py-2.5 border-b border-line flex items-center justify-between">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-mute">Tweaks</h3>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="w-6 h-6 grid place-items-center rounded hover:bg-paper-2"
            >
              <Icon.X className="w-3.5 h-3.5 text-mute" />
            </button>
          </header>

          <div className="px-4 py-3 space-y-3">
            <Section label="Brand">
              <Segmented<Theme>
                value={tweaks.theme}
                onChange={(v) => update({ theme: v })}
                options={[
                  { v: "oxblood", label: "Oxblood" },
                  { v: "teal", label: "Teal" },
                  { v: "ink", label: "Ink" },
                ]}
              />
            </Section>

            <Section label="Density">
              <Segmented<Density>
                value={tweaks.density}
                onChange={(v) => update({ density: v })}
                options={[
                  { v: "compact", label: "Compact" },
                  { v: "cozy", label: "Cozy" },
                  { v: "roomy", label: "Roomy" },
                ]}
              />
            </Section>

            <Section label="Headings">
              <label className="flex items-center justify-between text-[12.5px]">
                <span className="text-ink-2">Serif (Source Serif 4)</span>
                <input
                  type="checkbox"
                  checked={tweaks.serifHeads}
                  onChange={(e) => update({ serifHeads: e.target.checked })}
                  className="accent-stamp w-4 h-4"
                />
              </label>
            </Section>

            <button
              type="button"
              onClick={() => update(DEFAULTS)}
              className="w-full mt-1 text-[11.5px] text-mute hover:text-stamp text-center underline-offset-2 hover:underline"
            >
              Reset to defaults
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10.5px] font-mono uppercase tracking-[0.06em] text-mute mb-1">{label}</div>
      {children}
    </div>
  );
}

function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { v: T; label: string }[];
}) {
  return (
    <div className="inline-flex items-center gap-0.5 bg-paper-2 border border-line rounded p-0.5 w-full">
      {options.map((o) => (
        <button
          key={o.v}
          type="button"
          onClick={() => onChange(o.v)}
          className={`flex-1 text-[11.5px] font-medium h-6 px-2 rounded transition ${
            value === o.v ? "bg-surface text-stamp shadow-sm" : "text-ink-2 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
