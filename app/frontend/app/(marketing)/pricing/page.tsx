"use client";

/**
 * Marketing pricing page (`/pricing`).
 *
 * Client component because the price toggle state (period + currency)
 * lives in `useState` — the rest of the page (tier cards, comparison
 * table, FAQ) is pure derivation off that state plus typed content from
 * `_content/pricing.ts`. No fetch, no effects, no client storage; reload
 * resets to USD/Annual the same way the prototype does.
 *
 * Section order mirrors the prototype (`/tmp/pricing.html` ←
 * `design_handoff_tradenet_marketing/Tradenet - Marketing.html`):
 *   1. Hero (centered eyebrow + serif h1 + sub + two segmented controls)
 *   2. Three tier cards (Solo / Firm featured / Enterprise)
 *   3. Comparison table
 *   4. FAQ — left intro, right accordion (first item open)
 *
 * Why client-side state instead of URL params:
 *   - The prototype JS uses module-local state with no hash sync.
 *   - We'd lose SSR pricing for the default (USD annual) if we forced
 *     params before any interaction. A future PR can add `?period=` /
 *     `?currency=` via `useSearchParams` if marketing wants shareable
 *     deep-links — for now the in-page toggles are enough.
 */
import { useState } from "react";
import Link from "next/link";
import { PricingSeg } from "@/components/marketing/PricingSeg";
import { PricingTierCard } from "@/components/marketing/PricingTierCard";
import { ComparisonTable } from "@/components/marketing/ComparisonTable";
import { FAQItem } from "@/components/marketing/FAQItem";
import {
  COMPARISON_SECTIONS,
  FAQ,
  PRICES,
  TIERS,
  compareSection,
  currencyOptions,
  currencySymbol,
  faqSection,
  formatAmount,
  periodOptions,
  pricingHero,
  type Currency,
  type Period,
  type Tier,
} from "../_content/pricing";

/**
 * Build the bill-note string for a given tier under the current
 * period/currency. Mirrors the prototype's `updatePrices()` in
 * `marketing.js`:
 *
 *   Annual Solo  — "Billed annually · $588 / yr · 1 seat"
 *   Monthly Solo — "Billed monthly · $59 / mo · 1 seat"
 *   Annual Firm  — "Billed annually · from $6,444 / yr · 3 seats min"
 *   Monthly Firm — "Billed monthly · from $657 / mo · 3 seats min"
 *                                          ^^ firm * 3
 *
 * Enterprise's bill-note is static ("Volume pricing · annual contract · SLA-backed").
 */
function buildBillNote(
  tier: Tier,
  period: Period,
  currency: Currency,
): string {
  if (tier.id === "enterprise") {
    return "Volume pricing · annual contract · SLA-backed";
  }
  const sym = currencySymbol(currency);
  const prices = PRICES[currency][period];
  const isAnnual = period === "annual";

  if (tier.id === "solo") {
    if (isAnnual) {
      // soloYr non-null on annual rows
      return `Billed annually · ${sym}${formatAmount(prices.soloYr as number | string)} / yr · 1 seat`;
    }
    return `Billed monthly · ${sym}${formatAmount(prices.solo)} / mo · 1 seat`;
  }

  // firm
  if (isAnnual) {
    return `Billed annually · from ${sym}${formatAmount(prices.firmYr as number | string)} / yr · 3 seats min`;
  }
  // For monthly, prototype computes `firm * 3`. Only USD monthly is a
  // number; VND monthly is a pre-formatted string and the multiplication
  // doesn't apply cleanly — fall back to "from <firm> / seat / mo · 3 seats min".
  const firmVal = prices.firm;
  if (typeof firmVal === "number") {
    return `Billed monthly · from ${sym}${formatAmount(firmVal * 3)} / mo · 3 seats min`;
  }
  // VND monthly: keep the per-seat phrasing since we can't safely multiply
  // a locale-formatted string. Marketing reviewed the prototype JS, which
  // would have produced "NaN" in this branch, so this is also a quiet bug
  // fix.
  return `Billed monthly · from ${sym}${formatAmount(firmVal)} / seat / mo · 3 seats min`;
}

/** Compute the price amount + currency symbol props for one tier card. */
function buildPriceProps(
  tier: Tier,
  period: Period,
  currency: Currency,
): { priceAmount: string; priceCurrencySymbol?: string } {
  if (tier.customPrice) {
    return { priceAmount: "Custom" };
  }
  const prices = PRICES[currency][period];
  // tier.id is "solo" | "firm" here (enterprise is the only customPrice tier)
  const raw = tier.id === "solo" ? prices.solo : prices.firm;
  return {
    priceCurrencySymbol: currencySymbol(currency),
    priceAmount: formatAmount(raw),
  };
}

export default function PricingPage() {
  const [period, setPeriod] = useState<Period>("annual");
  const [currency, setCurrency] = useState<Currency>("USD");

  return (
    <>
      {/* Hero */}
      <section className="container pricing-head">
        <span className="eyebrow">{pricingHero.eyebrow}</span>
        <h1
          className="section-h2"
          style={{ marginTop: 12, fontSize: 48 }}
        >
          {pricingHero.h1}
        </h1>
        <p className="section-sub">{pricingHero.sub}</p>

        <div className="pricing-toggles">
          <PricingSeg
            options={periodOptions}
            value={period}
            onChange={setPeriod}
            ariaLabel="Billing period"
          />
          <PricingSeg
            options={currencyOptions}
            value={currency}
            onChange={setCurrency}
            ariaLabel="Currency"
          />
        </div>
      </section>

      {/* Tier cards */}
      <section className="container pricing-tiers">
        {TIERS.map((tier) => {
          const priceProps = buildPriceProps(tier, period, currency);
          const billNote = buildBillNote(tier, period, currency);
          return (
            <PricingTierCard
              key={tier.id}
              tier={tier}
              priceAmount={priceProps.priceAmount}
              priceCurrencySymbol={priceProps.priceCurrencySymbol}
              billNote={billNote}
            />
          );
        })}
      </section>

      {/* Comparison table */}
      <section className="container">
        <h2
          className="section-h2 text-center"
          style={{ fontSize: 28, marginTop: 32, marginBottom: 24 }}
        >
          {compareSection.h2}
        </h2>
        <ComparisonTable sections={COMPARISON_SECTIONS} />
      </section>

      {/* FAQ */}
      <section className="container faq">
        <div className="faq-grid">
          <div>
            <h2 className="faq-h2">{faqSection.h2}</h2>
            <p style={{ color: "var(--mute)", fontSize: 14 }}>
              {faqSection.sub.lead}
              <Link href="/login" style={{ color: "var(--stamp)" }}>
                {faqSection.sub.talkToSales}
              </Link>
              {faqSection.sub.middle}
              <a
                href={`mailto:${faqSection.sub.email}`}
                style={{ color: "var(--stamp)" }}
              >
                {faqSection.sub.email}
              </a>
              .
            </p>
          </div>
          <div className="faq-list">
            {FAQ.map((item, i) => (
              <FAQItem
                key={item.q}
                q={item.q}
                a={item.a}
                defaultOpen={i === 0}
              />
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
