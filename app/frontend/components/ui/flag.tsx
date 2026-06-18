/** ISO-2 country code → flag emoji. Built from Unicode regional-indicator
 * symbols so every valid country renders without a hand-maintained map (the
 * old ~27-entry map left the other ~190 codes blank). For the full name use
 * `countryDisplay()` from `lib/api`.
 *
 * A few WIPO Madrid designation codes are organisations, not countries, and
 * have no national flag (OA=OAPI, AP=ARIPO, BX=Benelux, WO/IB=WIPO, GC=GCC);
 * EM (the EU, EUIPO) is overridden to the EU flag, the rest fall back to a
 * neutral marker. */

const OVERRIDES: Record<string, string> = {
  EM: "🇪🇺", // EUIPO — WIPO designates the European Union as "EM"
};

/** Convert a 2-letter ISO code to its flag emoji (regional indicators). Returns
 * null for anything that isn't two ASCII letters. */
function isoToEmoji(code: string): string | null {
  const cc = code.toUpperCase();
  if (!/^[A-Z]{2}$/.test(cc)) return null;
  const BASE = 0x1f1e6; // 🇦
  return String.fromCodePoint(BASE + cc.charCodeAt(0) - 65, BASE + cc.charCodeAt(1) - 65);
}

export function Flag({ code, size = 14 }: { code?: string | null; size?: number }) {
  const flag = (code && (OVERRIDES[code.toUpperCase()] ?? isoToEmoji(code))) || "🏳️";
  return (
    <span
      style={{
        fontSize: size,
        lineHeight: 1,
        fontFamily: '"Apple Color Emoji","Segoe UI Emoji",sans-serif',
      }}
      aria-hidden="true"
    >
      {flag}
    </span>
  );
}
