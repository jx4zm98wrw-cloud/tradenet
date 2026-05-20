"use client";
import * as React from "react";

export type SegOption<T extends string> = { value: T; label: React.ReactNode; title?: string };

type SegmentedProps<T extends string> = {
  value: T;
  onChange: (v: T) => void;
  options: SegOption<T>[];
  size?: "sm" | "md";
  className?: string;
};

export function SegmentedControl<T extends string>({
  value, onChange, options, size = "md", className = "",
}: SegmentedProps<T>) {
  const padY = size === "sm" ? "py-1" : "py-1.5";
  return (
    <div className={`inline-flex border border-line rounded-md bg-paper-2 p-0.5 gap-0.5 ${className}`}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            title={o.title}
            onClick={() => onChange(o.value)}
            className={`inline-flex items-center gap-1.5 px-2.5 ${padY} text-xs font-medium rounded transition ${
              active
                ? "bg-surface text-ink shadow-sm border border-line"
                : "text-mute hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
