/** ISO-2 country code → flag emoji. Lookup-only; for the full name use
 * `countryDisplay()` from `lib/api`. */

const FLAGS: Record<string, string> = {
  VN: "🇻🇳", CN: "🇨🇳", US: "🇺🇸", KR: "🇰🇷", JP: "🇯🇵",
  SG: "🇸🇬", GB: "🇬🇧", DE: "🇩🇪", IN: "🇮🇳", FR: "🇫🇷",
  TH: "🇹🇭", TW: "🇹🇼", ID: "🇮🇩", MY: "🇲🇾", PH: "🇵🇭",
  AU: "🇦🇺", CA: "🇨🇦", NL: "🇳🇱", ES: "🇪🇸", IT: "🇮🇹",
  CH: "🇨🇭", TR: "🇹🇷", RU: "🇷🇺", BR: "🇧🇷", MX: "🇲🇽",
  HK: "🇭🇰", MO: "🇲🇴",
};

export function Flag({ code, size = 14 }: { code?: string | null; size?: number }) {
  const flag = (code && FLAGS[code]) || "🏳️";
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
