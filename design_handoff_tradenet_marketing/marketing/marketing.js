// Tradenet marketing — vanilla view switching + pricing toggles + similarity rings

(() => {

  // ---------- View switcher ----------
  const views = document.querySelectorAll('[data-view]');
  const navLinks = document.querySelectorAll('[data-view-link]');
  const footer = document.getElementById('footer');
  let timelineRendered = false;

  function setView(name, opts = {}) {
    views.forEach(v => v.classList.toggle('active', v.dataset.view === name));
    // Update nav active state
    document.querySelectorAll('.mk-nav-links button, .mk-nav-links a').forEach(el => {
      const target = el.dataset.viewLink;
      el.classList.toggle('active', target === name);
    });
    // Footer hidden on login; nav hidden on login (full-bleed)
    if (footer) footer.style.display = name === 'login' ? 'none' : '';
    document.body.classList.toggle('login-mode', name === 'login');
    // Side-effects on view enter
    if (name === 'coverage') renderCoverageTimeline();
    // Update hash
    if (!opts.skipHash) {
      const hash = name === 'landing' ? '#/' : '#/' + name;
      if (location.hash !== hash) history.replaceState(null, '', hash);
    }
    window.scrollTo(0, 0);
  }

  navLinks.forEach(el => {
    el.addEventListener('click', e => {
      const target = el.dataset.viewLink;
      if (!target) return;
      e.preventDefault();
      setView(target);
    });
  });

  // Hash routing on load
  function routeFromHash() {
    const h = location.hash.replace(/^#\/?/, '');
    const known = ['landing', 'pricing', 'login', 'coverage', 'docs'];
    const name = (h === '' || !known.includes(h)) ? 'landing' : h;
    setView(name, { skipHash: true });
  }
  window.addEventListener('hashchange', routeFromHash);
  routeFromHash();

  // ---------- Pricing toggles ----------
  const PRICES = {
    USD: {
      annual:  { solo: 49,  firm: 179, soloYr: 588,  firmYr: 6444 },
      monthly: { solo: 59,  firm: 219, soloYr: null, firmYr: null },
    },
    VND: {
      annual:  { solo: '1.190.000', firm: '4.390.000', soloYr: '14.280.000', firmYr: '158.040.000' },
      monthly: { solo: '1.490.000', firm: '5.490.000', soloYr: null,         firmYr: null },
    },
  };

  let curPeriod = 'annual';
  let curCurrency = 'USD';

  function fmtAmount(v) {
    if (typeof v === 'number') return v.toLocaleString('en-US');
    return v; // already formatted string for VND
  }
  function symbol(cur) { return cur === 'USD' ? '$' : '₫'; }

  function updatePrices() {
    const p = PRICES[curCurrency][curPeriod];
    const isAnnual = curPeriod === 'annual';
    document.querySelectorAll('[data-price]').forEach(el => {
      const k = el.dataset.price; // 'solo' | 'firm'
      el.textContent = fmtAmount(p[k]);
    });
    document.querySelectorAll('[data-currency-symbol]').forEach(el => {
      el.textContent = symbol(curCurrency);
    });
    const soloNote = document.querySelector('[data-billnote="solo"]');
    const firmNote = document.querySelector('[data-billnote="firm"]');
    if (soloNote) {
      soloNote.textContent = isAnnual
        ? `Billed annually · ${symbol(curCurrency)}${fmtAmount(p.soloYr)} / yr · 1 seat`
        : `Billed monthly · ${symbol(curCurrency)}${fmtAmount(p.solo)} / mo · 1 seat`;
    }
    if (firmNote) {
      firmNote.textContent = isAnnual
        ? `Billed annually · from ${symbol(curCurrency)}${fmtAmount(p.firmYr)} / yr · 3 seats min`
        : `Billed monthly · from ${symbol(curCurrency)}${fmtAmount(p.firm * 3)} / mo · 3 seats min`;
    }
  }

  document.querySelectorAll('#seg-period button').forEach(btn => {
    btn.addEventListener('click', () => {
      curPeriod = btn.dataset.period;
      document.querySelectorAll('#seg-period button').forEach(b => b.classList.toggle('active', b === btn));
      updatePrices();
    });
  });
  document.querySelectorAll('#seg-currency button').forEach(btn => {
    btn.addEventListener('click', () => {
      curCurrency = btn.dataset.currency;
      document.querySelectorAll('#seg-currency button').forEach(b => b.classList.toggle('active', b === btn));
      updatePrices();
    });
  });

  updatePrices();

  // ---------- Similarity rings ----------
  function renderRing(el) {
    const score = parseFloat(el.dataset.score);
    const size = parseInt(el.dataset.size || 36, 10);
    const r = (size - 4) / 2;
    const c = 2 * Math.PI * r;
    const dash = c * score;
    let color = 'var(--ok)';
    if (score >= 0.85) color = 'var(--stamp)';
    else if (score >= 0.7) color = 'var(--warn)';
    const pct = Math.round(score * 100);
    el.style.width = size + 'px';
    el.style.height = size + 'px';
    el.style.display = 'inline-block';
    el.innerHTML = `
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="var(--line)" stroke-width="3"/>
        <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${color}" stroke-width="3"
          stroke-dasharray="${dash} ${c}" stroke-linecap="round"/>
      </svg>
      <div class="simring-text" style="font-size:${size * 0.28}px;color:${color};">${pct}</div>
    `;
  }
  document.querySelectorAll('.simring').forEach(renderRing);

  // ---------- Coverage timeline ----------
  // 52 weeks of synthetic but plausible load data
  function renderCoverageTimeline() {
    if (timelineRendered) return;
    const grid = document.getElementById('tl-grid');
    if (!grid) return;
    timelineRendered = true;

    // Header: empty corner + week numbers
    const frag = document.createDocumentFragment();
    const corner = document.createElement('div');
    corner.className = 'tl-grid-label';
    corner.textContent = 'wk';
    frag.appendChild(corner);
    for (let w = 1; w <= 52; w++) {
      const cell = document.createElement('div');
      cell.className = 'tl-grid-week';
      cell.textContent = (w % 4 === 1) ? w : '';
      frag.appendChild(cell);
    }

    const rows = [
      { label: '2025 · A', seed: 11 },
      { label: '2025 · B', seed: 23 },
      { label: '2026 · A', seed: 41, partial: true },
      { label: '2026 · B', seed: 59, partial: true },
    ];

    rows.forEach(({ label, seed, partial }) => {
      const labelCell = document.createElement('div');
      labelCell.className = 'tl-grid-label';
      labelCell.textContent = label;
      frag.appendChild(labelCell);
      for (let w = 1; w <= 52; w++) {
        const cell = document.createElement('div');
        cell.className = 'tl-grid-cell';
        // Pseudo-random but deterministic load
        const r = ((seed * 9301 + w * 49297) % 233280) / 233280;
        let load;
        if (partial && w > 20) load = 0;
        else if (r < 0.1) load = 0;
        else if (r < 0.3) load = 1;
        else if (r < 0.55) load = 2;
        else if (r < 0.85) load = 3;
        else load = 4;
        cell.dataset.load = load;
        if (load > 0) {
          const counts = ['', '< 2k', '2–5k', '5–8k', '> 8k'];
          cell.title = `${label} · wk ${w} · ${counts[load]} marks`;
        }
        frag.appendChild(cell);
      }
    });

    grid.innerHTML = '';
    grid.appendChild(frag);
  }

  // ---------- Docs sidebar ----------
  const PLACEHOLDER_DOCS = new Set(['team-invite', 'text-search', 'phonetic-search', 'vienna-search',
    'watchlists', 'opposition', 'reports', 'webhooks', 'sso']);

  function showDoc(slug) {
    const target = PLACEHOLDER_DOCS.has(slug) ? 'placeholder' : slug;
    document.querySelectorAll('[data-doc-content]').forEach(el => {
      el.style.display = el.dataset.docContent === target ? '' : 'none';
    });
    document.querySelectorAll('.docs-sb-link').forEach(el => {
      el.classList.toggle('active', el.dataset.doc === slug);
    });
    // Scroll docs main back to top
    const main = document.querySelector('.docs-main');
    if (main) main.scrollTo({ top: 0, behavior: 'auto' });
  }
  document.querySelectorAll('.docs-sb-link').forEach(btn => {
    btn.addEventListener('click', () => showDoc(btn.dataset.doc));
  });
  document.querySelectorAll('[data-doc-link]').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      showDoc(el.dataset.docLink);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

})();
