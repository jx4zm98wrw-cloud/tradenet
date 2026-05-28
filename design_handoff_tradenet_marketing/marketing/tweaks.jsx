// Tweaks panel for the marketing page — uses the shared TweaksPanel helper

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "oxblood",
  "currency": "USD",
  "showAnnualDiscount": true
}/*EDITMODE-END*/;

function MarketingTweaks() {
  const [t, setTweak] = window.useTweaks(TWEAK_DEFAULTS);

  React.useEffect(() => {
    document.body.dataset.theme = t.theme;
  }, [t.theme]);

  React.useEffect(() => {
    // Reflect currency choice into pricing toggle
    const btn = document.querySelector(`#seg-currency button[data-currency="${t.currency}"]`);
    if (btn && !btn.classList.contains('active')) btn.click();
  }, [t.currency]);

  React.useEffect(() => {
    const note = document.querySelector('.pricing-discount-note');
    const annualBtn = document.querySelector('#seg-period button[data-period="annual"]');
    if (annualBtn) {
      annualBtn.textContent = t.showAnnualDiscount ? "Annual · save 17%" : "Annual";
    }
  }, [t.showAnnualDiscount]);

  return (
    <window.TweaksPanel>
      <window.TweakSection label="Theme">
        <window.TweakRadio
          label="Brand color"
          value={t.theme}
          options={["oxblood", "teal", "ink"]}
          onChange={(v) => setTweak("theme", v)}
        />
      </window.TweakSection>
      <window.TweakSection label="Pricing">
        <window.TweakRadio
          label="Default currency"
          value={t.currency}
          options={["USD", "VND"]}
          onChange={(v) => setTweak("currency", v)}
        />
        <window.TweakToggle
          label="Show annual discount badge"
          value={t.showAnnualDiscount}
          onChange={(v) => setTweak("showAnnualDiscount", v)}
        />
      </window.TweakSection>
      <window.TweakSection label="Jump to">
        <window.TweakButton label="Landing" onClick={() => location.hash = '#/'}/>
        <window.TweakButton label="Pricing" onClick={() => location.hash = '#/pricing'}/>
        <window.TweakButton label="Coverage" onClick={() => location.hash = '#/coverage'}/>
        <window.TweakButton label="Docs" onClick={() => location.hash = '#/docs'}/>
        <window.TweakButton label="Login" onClick={() => location.hash = '#/login'}/>
        <window.TweakButton label="Open the app →" onClick={() => location.href = 'Trademark Gazette - Redesign.html'}/>
      </window.TweakSection>
    </window.TweaksPanel>
  );
}

ReactDOM.createRoot(document.getElementById("tweaks-root")).render(<MarketingTweaks/>);
