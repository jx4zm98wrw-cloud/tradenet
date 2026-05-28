/**
 * One tier card on the pricing page (Solo / Firm / Enterprise).
 *
 * Server component — the live price/billnote text gets computed by the
 * parent (`pricing/page.tsx`) and passed in as fully-resolved strings, so
 * this component never re-renders on currency/period toggle and stays
 * server-rendered for the initial paint. Only the parent re-renders, and
 * only the inner `<PricingSeg>` controls flip client.
 *
 * Bullet copy comes from `_content/pricing.ts`. The prototype's HTML had
 * inline `<strong>` and `&amp;` mixed into bullet text — to avoid
 * `dangerouslySetInnerHTML` we render the markup structurally via
 * `renderBulletText` (which handles the small finite set of inline tokens
 * the prototype uses).
 */
import Link from "next/link";
import type { ReactNode } from "react";
import type { Bullet, Tier } from "@/app/(marketing)/_content/pricing";

type Props = {
  tier: Tier;
  /**
   * Pre-formatted display strings — already includes the `$`/`₫` currency
   * symbol for the amount line, and the full "Billed annually · …" sentence
   * for the bill note. Falsy `priceAmount` ⇒ render the literal "Custom"
   * (used for the Enterprise tier).
   */
  priceCurrencySymbol?: string;
  priceAmount: string;
  billNote: string;
};

/**
 * Render a bullet's `text` field, preserving the prototype's two inline
 * tokens:
 *   - `<strong>…</strong>` ⇒ wrap in a real <strong>
 *   - `&amp;`              ⇒ unescape to literal `&`
 * Everything else passes through as plain text.
 *
 * Kept here (not in `_content/pricing.ts`) because the content module
 * stays string-shaped for easy translation / copy edits; only the renderer
 * knows how to interpret the inline markup.
 */
function renderBulletText(text: string): ReactNode {
  // 1. unescape the only HTML entity the prototype uses
  const unescaped = text.replace(/&amp;/g, "&");
  // 2. split on the <strong>…</strong> token, preserving the captured inner text
  const parts = unescaped.split(/(<strong>[^<]*<\/strong>)/g);
  return parts.map((part, i) => {
    const m = part.match(/^<strong>([^<]*)<\/strong>$/);
    if (m) return <strong key={i}>{m[1]}</strong>;
    return <span key={i}>{part}</span>;
  });
}

export function PricingTierCard({
  tier,
  priceCurrencySymbol,
  priceAmount,
  billNote,
}: Props) {
  const isCustom = tier.customPrice === true;
  const articleClass = tier.featured ? "tier featured" : "tier";
  const btnClass =
    tier.cta.variant === "primary" ? "btn btn-primary btn-lg" : "btn btn-ghost btn-lg";

  return (
    <article className={articleClass}>
      {tier.badge ? <span className="tier-badge">{tier.badge}</span> : null}
      <div>
        <div className="tier-name">{tier.name}</div>
        <div className="tier-tagline">{tier.tagline}</div>
      </div>
      <div>
        <div className="tier-price">
          {isCustom ? (
            // Prototype renders "Custom" at 36px (inline style on the
            // prototype HTML) instead of the 52px serif numeral.
            <span className="tier-amount" style={{ fontSize: 36 }}>
              {priceAmount}
            </span>
          ) : (
            <>
              <span className="tier-currency">{priceCurrencySymbol}</span>
              <span className="tier-amount">{priceAmount}</span>
              <span className="tier-period">{tier.perPeriodLabel}</span>
            </>
          )}
        </div>
        <div className="tier-billnote">{billNote}</div>
      </div>
      <div className="tier-cta">
        <Link href={tier.cta.href} className={btnClass}>
          {tier.cta.label}
        </Link>
      </div>
      <div className="tier-divider" />
      <div className="tier-includes-label">{tier.includesLabel}</div>
      <ul className="tier-list">
        {tier.bullets.map((b: Bullet, i: number) => (
          <li key={i} className={b.included ? undefined : "muted"}>
            {renderBulletText(b.text)}
          </li>
        ))}
      </ul>
    </article>
  );
}
