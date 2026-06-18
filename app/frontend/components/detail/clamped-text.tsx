"use client";

import * as React from "react";

/** Goods/services text clamped to 5 lines with a per-block Show more/less
 * toggle. The toggle only appears when the text actually overflows 5 lines
 * (measured), so short classes stay clean. */
export function ClampedText({ text }: { text: string }) {
  const [expanded, setExpanded] = React.useState(false);
  const [overflows, setOverflows] = React.useState(false);
  const ref = React.useRef<HTMLParagraphElement>(null);

  React.useEffect(() => {
    const el = ref.current;
    // Measured while clamped (collapsed): scrollHeight > clientHeight ⇒ there's
    // hidden content, so the toggle is warranted.
    if (el && !expanded) setOverflows(el.scrollHeight > el.clientHeight + 1);
  }, [text, expanded]);

  return (
    <div>
      <p
        ref={ref}
        className={`text-[13px] text-ink-2 leading-relaxed ${expanded ? "" : "line-clamp-5"}`}
      >
        {text}
      </p>
      {(overflows || expanded) && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-[12px] font-medium text-stamp hover:text-stamp-deep"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}
