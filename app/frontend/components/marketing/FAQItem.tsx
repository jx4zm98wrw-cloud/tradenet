/**
 * One FAQ row on `/pricing`. Server component built on the native
 * `<details>`/`<summary>` pair so the open/closed state lives in the DOM
 * and needs zero JS — the `+`/`−` indicator flips via the prototype's
 * `.faq-item[open] summary::after { content: "−" }` CSS rule.
 *
 * `defaultOpen` maps to the native `open` attribute; the page passes
 * `defaultOpen` on the first item so the surface lands with one answer
 * already visible (matches the prototype's `<details … open>` on the
 * first question).
 */
type Props = {
  q: string;
  a: string;
  defaultOpen?: boolean;
};

export function FAQItem({ q, a, defaultOpen = false }: Props) {
  return (
    <details className="faq-item" open={defaultOpen}>
      <summary>{q}</summary>
      <p>{a}</p>
    </details>
  );
}
