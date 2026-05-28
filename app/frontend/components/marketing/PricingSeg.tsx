"use client";

/**
 * Segmented control used twice on the pricing page (period + currency).
 *
 * Pure presentational client component: receives a controlled value + an
 * `onChange` from the parent, renders one `<button>` per option, and toggles
 * the prototype's `.active` class on the selected one. The parent owns the
 * state so a future ?period= / ?currency= URL-sync hook only has to touch
 * one place.
 *
 * Buttons are `type="button"` to be safe inside any future <form> wrapper
 * (e.g., once we A/B test trial signups). Accessibility: each button gets
 * `aria-pressed` so screen readers can announce the active option without
 * relying on the visual treatment.
 */
type Option<T extends string> = { value: T; label: string };

type Props<T extends string> = {
  /** Labelled options in display order. */
  options: ReadonlyArray<Option<T>>;
  /** Currently selected option's `value`. */
  value: T;
  /** Called with the clicked option's `value` (never re-fires on re-click). */
  onChange: (v: T) => void;
  /** Visible label for screen readers (`aria-label` on the group). */
  ariaLabel: string;
};

export function PricingSeg<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: Props<T>) {
  return (
    <div className="pricing-seg" role="group" aria-label={ariaLabel}>
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            className={active ? "active" : undefined}
            aria-pressed={active}
            onClick={() => {
              if (!active) onChange(opt.value);
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
