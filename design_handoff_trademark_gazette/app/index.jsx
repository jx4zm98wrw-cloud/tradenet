// Root App — routing, tweaks, mounting
const { useState: useStateA, useEffect: useEffectA } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "oxblood",
  "density": "cozy",
  "useSerifHeads": true,
  "showSpecimenFrame": true
}/*EDITMODE-END*/;

function App() {
  // route: "dashboard" | "search" | "watchlists" | "gazettes" | "detail:<id>" | "compare:<id,id>"
  const [route, setRoute] = useStateA("dashboard");
  const [cmdkOpen, setCmdkOpen] = useStateA(false);
  const [t, setTweak] = (window.useTweaks ? window.useTweaks(TWEAK_DEFAULTS) : [TWEAK_DEFAULTS, () => {}]);

  // Apply theme + density to body
  useEffectA(() => {
    document.body.dataset.theme = t.theme;
    document.body.dataset.density = t.density;
    document.body.dataset.serifheads = t.useSerifHeads ? "1" : "0";
  }, [t.theme, t.density, t.useSerifHeads]);

  // Keyboard shortcut for cmd-k
  useEffectA(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setCmdkOpen(true); }
      if (e.key === "Escape") setCmdkOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onNav = (r) => { setRoute(r); window.scrollTo(0, 0); };

  const [route0, routeArg] = route.split(":");

  return (
    <>
      <TopNav route={route0} onNav={onNav} onOpenCmdK={() => setCmdkOpen(true)}/>

      <main className="app-main">
        {route0 === "dashboard" && <Dashboard onNav={onNav}/>}
        {route0 === "search"    && <Search    onNav={onNav} onCompareSelected={(ids) => onNav("compare:" + ids.join(","))}/>}
        {route0 === "watchlists"&& <Watchlists onNav={onNav}/>}
        {route0 === "gazettes"  && <Gazettes  onNav={onNav}/>}
        {route0 === "detail"    && <Detail    markId={routeArg || "tm-001"} onNav={onNav} onCompareWith={(id) => onNav("compare:" + id + ",tm-002,tm-003")}/>}
        {route0 === "compare"   && <Compare   markIds={(routeArg || "").split(",")} onNav={onNav}/>}
      </main>

      <CmdK open={cmdkOpen} onClose={() => setCmdkOpen(false)} onNav={onNav}/>

      {window.TweaksPanel && (
        <window.TweaksPanel>
          <window.TweakSection label="Theme">
            <window.TweakRadio
              label="Brand color"
              value={t.theme}
              onChange={(v) => setTweak("theme", v)}
              options={["oxblood", "teal", "ink"]}
            />
            <window.TweakToggle
              label="Serif section heads"
              value={t.useSerifHeads}
              onChange={(v) => setTweak("useSerifHeads", v)}
            />
            <window.TweakToggle
              label="Specimen plate frame"
              value={t.showSpecimenFrame}
              onChange={(v) => setTweak("showSpecimenFrame", v)}
            />
          </window.TweakSection>
          <window.TweakSection label="Density">
            <window.TweakRadio
              label="Row density"
              value={t.density}
              onChange={(v) => setTweak("density", v)}
              options={["compact", "cozy", "roomy"]}
            />
          </window.TweakSection>
          <window.TweakSection label="Jump to">
            <window.TweakButton label="Dashboard" onClick={() => onNav("dashboard")}/>
            <window.TweakButton label="Search" onClick={() => onNav("search")}/>
            <window.TweakButton label="Detail · NEUROFAX" onClick={() => onNav("detail:tm-001")}/>
            <window.TweakButton label="Detail · VINGROUP" onClick={() => onNav("detail:tm-005")}/>
            <window.TweakButton label="Compare · 3-up" onClick={() => onNav("compare:tm-001,tm-002,tm-003")}/>
            <window.TweakButton label="Watchlists" onClick={() => onNav("watchlists")}/>
            <window.TweakButton label="Gazettes (admin)" onClick={() => onNav("gazettes")}/>
          </window.TweakSection>
        </window.TweaksPanel>
      )}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
