/**
 * Front End Stratège Builder
 *
 * Couche de présentation exclusivement frontend pour les livrables produits
 * par le Stratège. Le Builder ne transforme jamais les données métier : il
 * qualifie leur densité, construit la lecture continue du rapport et audite
 * le DOM final afin d'éviter les débordements, les cartes vides et les grands
 * espaces accidentels.
 */

export const FRONT_END_STRATEGE_BUILDER = Object.freeze({
  name: 'Front End Stratège Builder',
  version: '1.0.0',
});

export const STRATEGIST_REPORT_SECTIONS = Object.freeze([
  { key: 'synthese', label: 'Synthèse', eyebrow: 'Analyse stratégique', title: 'La décision en un regard' },
  { key: 'marketing', label: 'Opportunités', eyebrow: 'Marché & valeur', title: 'Là où le levier est le plus fort' },
  { key: 'branding', label: 'Positionnement', eyebrow: 'Marque & contenus', title: 'Construire une préférence claire' },
  { key: 'plan', label: 'Priorités', eyebrow: 'Ordre d’action', title: 'Passer de la décision à l’exécution' },
  { key: 'decision', label: 'Vigilance', eyebrow: 'Regard critique', title: 'Ce qui pourrait remettre la stratégie en question' },
]);

const CARD_SELECTOR = [
  '.kpi-card',
  '.strat-card',
  '.decision-card',
  '.obj-card',
  '.opp-card',
  '.conf-gauge-card',
  '.fb-card',
  '.createur-bridge',
].join(',');

const TEXT_RULES = Object.freeze([
  { selector: '.strat-hero-decision', thresholds: { medium: 105, long: 190, extended: 320 } },
  { selector: '.kpi-value--text', thresholds: { medium: 65, long: 125, extended: 220 } },
  { selector: '.decision-text', thresholds: { medium: 105, long: 195, extended: 330 } },
  { selector: '.obj-text', thresholds: { medium: 145, long: 275, extended: 460 } },
  { selector: '.opp-decision-text', thresholds: { medium: 115, long: 220, extended: 370 } },
  { selector: '.opp-signal-text, .opp-sub-text', thresholds: { medium: 150, long: 290, extended: 480 } },
  { selector: '.crit-row-text, .reco-signal', thresholds: { medium: 165, long: 315, extended: 520 } },
  { selector: '.plan-item, .plan-decision, .risk-text, .risk-mitigation', thresholds: { medium: 150, long: 300, extended: 500 } },
]);

const DENSITY_RANK = Object.freeze({ short: 0, medium: 1, long: 2, extended: 3 });

function cleanText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

/** Retourne une densité stable, utilisable par le CSS et les tests. */
export function classifyStrategistText(value, thresholds = {}) {
  const text = cleanText(value);
  const limits = {
    medium: Number.isFinite(thresholds.medium) ? thresholds.medium : 120,
    long: Number.isFinite(thresholds.long) ? thresholds.long : 240,
    extended: Number.isFinite(thresholds.extended) ? thresholds.extended : 420,
  };

  if (text.length >= limits.extended) return 'extended';
  if (text.length >= limits.long) return 'long';
  if (text.length >= limits.medium) return 'medium';
  return 'short';
}

function getAvailableSections(dashboard, tabsBar) {
  return STRATEGIST_REPORT_SECTIONS.map(section => ({
    section,
    tab: tabsBar.querySelector(`[aria-controls="dash-panel-${section.key}"]`),
    panel: dashboard.querySelector(`#dash-panel-${section.key}`),
  })).filter(item => item.tab && item.panel);
}

function setActiveSection(tabs, activeIndex) {
  tabs.forEach((tab, index) => {
    const isActive = index === activeIndex;
    tab.classList.toggle('active', isActive);
    tab.removeAttribute('role');
    tab.removeAttribute('aria-selected');
    if (isActive) tab.setAttribute('aria-current', 'location');
    else tab.removeAttribute('aria-current');
  });
}

function buildContinuousReport(frameDocument, state) {
  const dashboard = frameDocument.getElementById('strat-dashboard');
  const frameWindow = frameDocument.defaultView;
  const tabsBar = dashboard?.querySelector('.dash-tabs');
  if (!dashboard || !frameWindow || !tabsBar || !dashboard.classList.contains('strat-cockpit-active')) return false;

  const availableSections = getAvailableSections(dashboard, tabsBar);
  if (!availableSections.length) return false;
  const tabs = availableSections.map(item => item.tab);
  const panels = availableSections.map(item => item.panel);

  dashboard.classList.add('gv2-strategy-report', 'sfb-report');
  dashboard.dataset.sfbBuilder = FRONT_END_STRATEGE_BUILDER.name;
  dashboard.dataset.sfbVersion = FRONT_END_STRATEGE_BUILDER.version;
  frameDocument.body?.classList.add('gv2-strategy-report-active');
  tabsBar.setAttribute('role', 'navigation');
  tabsBar.setAttribute('aria-label', 'Sommaire du rapport stratégique');

  if (!tabsBar.querySelector('.gv2-strategy-report-nav-head')) {
    const head = frameDocument.createElement('div');
    head.className = 'gv2-strategy-report-nav-head';
    head.innerHTML = '<span>Votre rapport</span><strong>Rapport stratégique</strong><small>Décision &amp; exécution</small>';
    tabsBar.prepend(head);
  }
  if (!tabsBar.querySelector('.gv2-strategy-report-nav-foot')) {
    const foot = frameDocument.createElement('div');
    foot.className = 'gv2-strategy-report-nav-foot';
    foot.innerHTML = '<span aria-hidden="true">✦</span><p>Analysé par Gabriel<small>Intelligence business</small></p>';
    tabsBar.append(foot);
  }

  availableSections.forEach(({ tab, panel, section }, visibleIndex) => {
    const number = String(visibleIndex + 1).padStart(2, '0');
    if (tab.textContent !== section.label) tab.textContent = section.label;
    tab.dataset.reportNumber = number;
    tab.removeAttribute('role');
    tab.removeAttribute('aria-selected');
    panel.classList.remove('hidden');
    panel.removeAttribute('role');
    panel.dataset.reportSection = number;
    panel.dataset.sfbSection = section.key;

    if (!panel.querySelector(':scope > .gv2-strategy-section-heading')) {
      const heading = frameDocument.createElement('header');
      heading.className = 'gv2-strategy-section-heading';
      heading.innerHTML = `<p><span>${number}</span>${section.eyebrow}</p><h2>${section.title}</h2>`;
      panel.prepend(heading);
    }

    tab.onclick = () => {
      setActiveSection(tabs, tabs.indexOf(tab));
      panel.scrollIntoView({
        behavior: frameWindow.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
        block: 'start',
      });
    };
  });

  const initiallyActive = tabs.findIndex(tab => tab.classList.contains('active'));
  setActiveSection(tabs, initiallyActive >= 0 ? initiallyActive : 0);

  state.sectionObserver?.disconnect();
  if (frameWindow.IntersectionObserver) {
    const scrollRoot = frameDocument.querySelector('.app-content');
    state.sectionObserver = new frameWindow.IntersectionObserver(entries => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      const activeIndex = panels.indexOf(visible.target);
      if (activeIndex >= 0) setActiveSection(tabs, activeIndex);
    }, { root: scrollRoot || null, rootMargin: '-12% 0px -62% 0px', threshold: [0, .08, .2, .45] });
    panels.forEach(panel => state.sectionObserver.observe(panel));
  }

  return true;
}

function applyContentDensity(dashboard) {
  const cardDensities = new Map();

  dashboard.querySelectorAll('.dash-panel').forEach(panel => {
    [...panel.children].forEach(element => {
      if (element.classList.contains('gv2-strategy-section-heading')) return;
      const hasRenderableContent = Boolean(
        cleanText(element.textContent) || element.querySelector('img, svg, canvas, video'),
      );
      element.classList.add('sfb-deliverable');
      element.classList.toggle('sfb-empty-deliverable', !hasRenderableContent);
    });
  });

  TEXT_RULES.forEach(rule => {
    dashboard.querySelectorAll(rule.selector).forEach(element => {
      const density = classifyStrategistText(element.textContent, rule.thresholds);
      element.dataset.sfbDensity = density;
      const card = element.closest(CARD_SELECTOR);
      if (!card) return;
      const previous = cardDensities.get(card) || 'short';
      if (DENSITY_RANK[density] > DENSITY_RANK[previous]) cardDensities.set(card, density);
      else if (!cardDensities.has(card)) cardDensities.set(card, previous);
    });
  });

  dashboard.querySelectorAll(CARD_SELECTOR).forEach(card => {
    card.dataset.sfbDensity = cardDensities.get(card) || 'short';
  });
}

function hasHorizontalOverflow(element) {
  return element.clientWidth > 0 && element.scrollWidth > element.clientWidth + 2;
}

/** Produit un diagnostic lisible sans modifier les données du livrable. */
export function auditStrategistFrontend(frameDocument) {
  const dashboard = frameDocument?.getElementById('strat-dashboard');
  if (!dashboard) {
    return {
      builder: FRONT_END_STRATEGE_BUILDER.name,
      version: FRONT_END_STRATEGE_BUILDER.version,
      ready: false,
      status: 'waiting',
      sections: 0,
      deliverables: 0,
      issues: [{ type: 'missing-dashboard', message: 'Le tableau de bord du Stratège n’est pas encore disponible.' }],
    };
  }

  const issues = [];
  const sections = [...dashboard.querySelectorAll('.dash-panel')];
  const deliverables = [...dashboard.querySelectorAll('.sfb-deliverable')];

  sections.forEach(panel => {
    const content = [...panel.children].filter(element => !element.classList.contains('gv2-strategy-section-heading'));
    if (!content.length) {
      issues.push({ type: 'empty-section', section: panel.dataset.sfbSection || panel.id, message: 'Section sans livrable visible.' });
    }
  });

  deliverables.forEach((element, index) => {
    const text = cleanText(element.textContent);
    if (!text && !element.querySelector('img, svg, canvas, video')) {
      issues.push({ type: 'empty-deliverable', index, message: 'Bloc de livrable vide.' });
    }
    const overflow = hasHorizontalOverflow(element);
    element.classList.toggle('sfb-has-horizontal-overflow', overflow);
    if (overflow) issues.push({ type: 'horizontal-overflow', index, message: 'Débordement horizontal détecté.' });
  });

  const actionBar = dashboard.querySelector('.strat-action-bar');
  const firstPanel = sections[0];
  if (actionBar && firstPanel && typeof actionBar.getBoundingClientRect === 'function') {
    const barRect = actionBar.getBoundingClientRect();
    const panelRect = firstPanel.getBoundingClientRect();
    const viewportHeight = frameDocument.defaultView?.innerHeight || 0;
    const gap = panelRect.top - barRect.bottom;
    if (barRect.height > 0 && gap > Math.max(420, viewportHeight * .62)) {
      issues.push({ type: 'excessive-section-gap', pixels: Math.round(gap), message: 'Espace excessif avant le premier livrable.' });
    }
  }

  const report = {
    builder: FRONT_END_STRATEGE_BUILDER.name,
    version: FRONT_END_STRATEGE_BUILDER.version,
    ready: dashboard.classList.contains('strat-cockpit-active'),
    status: issues.length ? 'warning' : 'ok',
    sections: sections.length,
    deliverables: deliverables.length,
    densities: {
      short: dashboard.querySelectorAll('[data-sfb-density="short"]').length,
      medium: dashboard.querySelectorAll('[data-sfb-density="medium"]').length,
      long: dashboard.querySelectorAll('[data-sfb-density="long"]').length,
      extended: dashboard.querySelectorAll('[data-sfb-density="extended"]').length,
    },
    issues,
  };

  dashboard.dataset.sfbStatus = report.status;
  dashboard.dataset.sfbIssueCount = String(issues.length);
  dashboard.__sfbAudit = report;
  return report;
}

export function createFrontEndStrategeBuilder(frameDocument) {
  const frameWindow = frameDocument?.defaultView;
  const dashboard = frameDocument?.getElementById('strat-dashboard');
  const state = {
    destroyed: false,
    queued: false,
    mutationObserver: null,
    resizeObserver: null,
    sectionObserver: null,
    lastAudit: null,
  };

  const run = () => {
    if (state.destroyed || !dashboard) return auditStrategistFrontend(frameDocument);
    const ready = buildContinuousReport(frameDocument, state);
    if (ready) applyContentDensity(dashboard);
    state.lastAudit = auditStrategistFrontend(frameDocument);
    return state.lastAudit;
  };

  const schedule = () => {
    if (state.destroyed || state.queued) return;
    state.queued = true;
    const defer = frameWindow?.requestAnimationFrame
      ? callback => frameWindow.requestAnimationFrame(callback)
      : callback => frameWindow?.setTimeout(callback, 0);
    defer(() => {
      state.queued = false;
      run();
    });
  };

  const observe = () => {
    run();
    if (!dashboard || !frameWindow) return api;

    state.mutationObserver?.disconnect();
    if (frameWindow.MutationObserver) {
      state.mutationObserver = new frameWindow.MutationObserver(schedule);
      state.mutationObserver.observe(dashboard, { childList: true, subtree: true, characterData: true });
    }

    state.resizeObserver?.disconnect();
    if (frameWindow.ResizeObserver) {
      state.resizeObserver = new frameWindow.ResizeObserver(schedule);
      state.resizeObserver.observe(dashboard);
    }
    return api;
  };

  const destroy = () => {
    state.destroyed = true;
    state.mutationObserver?.disconnect();
    state.resizeObserver?.disconnect();
    state.sectionObserver?.disconnect();
  };

  const api = {
    name: FRONT_END_STRATEGE_BUILDER.name,
    version: FRONT_END_STRATEGE_BUILDER.version,
    run,
    audit: () => auditStrategistFrontend(frameDocument),
    observe,
    destroy,
    get lastAudit() { return state.lastAudit; },
  };

  return api;
}

/** Point d'entrée utilisé par l'espace iframe de Gabriel V2. */
export function mountFrontEndStrategeBuilder(frameDocument) {
  const frameWindow = frameDocument?.defaultView;
  frameWindow?.__gabrielFrontEndStrategeBuilder?.destroy?.();
  const builder = createFrontEndStrategeBuilder(frameDocument);
  builder.observe();
  if (frameWindow) frameWindow.__gabrielFrontEndStrategeBuilder = builder;
  return builder;
}
