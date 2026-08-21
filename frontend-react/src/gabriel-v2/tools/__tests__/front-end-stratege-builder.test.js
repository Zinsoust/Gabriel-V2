import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  FRONT_END_STRATEGE_BUILDER,
  auditStrategistFrontend,
  classifyStrategistText,
  createFrontEndStrategeBuilder,
  mountFrontEndStrategeBuilder,
} from '../front-end-stratege-builder.js';

const SECTION_KEYS = ['synthese', 'marketing', 'branding', 'plan', 'decision'];

function renderDashboard() {
  const tabs = SECTION_KEYS.map((key, index) => `
    <button class="dash-tab${index === 0 ? ' active' : ''}" role="tab" aria-selected="${index === 0}" aria-controls="dash-panel-${key}">Ancien libellé</button>
  `).join('');
  const panels = SECTION_KEYS.map((key, index) => `
    <section class="dash-panel hidden" id="dash-panel-${key}" role="tabpanel">
      <article class="kpi-card">
        <div class="kpi-value kpi-value--text">${index === 0 ? 'Une projection particulièrement détaillée '.repeat(12) : `Livrable ${key}`}</div>
      </article>
    </section>
  `).join('');

  document.body.className = 'is-embedded-agent page-stratege';
  document.body.innerHTML = `
    <main class="app-content">
      <div id="strat-dashboard" class="strat-cockpit-active">
        <div class="strat-action-bar"></div>
        <nav class="dash-tabs" role="tablist">${tabs}</nav>
        ${panels}
      </div>
    </main>`;
  window.matchMedia = vi.fn().mockReturnValue({ matches: true });
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
  return document.getElementById('strat-dashboard');
}

afterEach(() => {
  window.__gabrielFrontEndStrategeBuilder?.destroy?.();
  delete window.__gabrielFrontEndStrategeBuilder;
  document.body.innerHTML = '';
  document.body.className = '';
  vi.restoreAllMocks();
});

describe('Front End Stratège Builder', () => {
  it('porte le nom demandé et classe la densité des textes', () => {
    expect(FRONT_END_STRATEGE_BUILDER.name).toBe('Front End Stratège Builder');
    expect(classifyStrategistText('Court', { medium: 10, long: 20, extended: 30 })).toBe('short');
    expect(classifyStrategistText('x'.repeat(15), { medium: 10, long: 20, extended: 30 })).toBe('medium');
    expect(classifyStrategistText('x'.repeat(25), { medium: 10, long: 20, extended: 30 })).toBe('long');
    expect(classifyStrategistText('x'.repeat(35), { medium: 10, long: 20, extended: 30 })).toBe('extended');
  });

  it('construit un rapport continu sans altérer le texte des livrables', () => {
    const dashboard = renderDashboard();
    const original = dashboard.querySelector('.kpi-value--text').textContent;
    const builder = createFrontEndStrategeBuilder(document);
    const report = builder.run();

    expect(dashboard).toHaveClass('gv2-strategy-report', 'sfb-report');
    expect(dashboard.dataset.sfbBuilder).toBe('Front End Stratège Builder');
    expect(document.querySelectorAll('.dash-panel:not(.hidden)')).toHaveLength(5);
    expect(document.querySelectorAll('.gv2-strategy-section-heading')).toHaveLength(5);
    expect(document.querySelectorAll('.sfb-deliverable')).toHaveLength(5);
    expect(document.querySelector('.kpi-value--text').textContent).toBe(original);
    expect(document.querySelector('.kpi-value--text')).toHaveAttribute('data-sfb-density', 'extended');
    expect(document.querySelector('.kpi-card')).toHaveAttribute('data-sfb-density', 'extended');
    expect(report.status).toBe('ok');
    expect(report.sections).toBe(5);
  });

  it('transforme les anciens onglets en sommaire accessible', () => {
    renderDashboard();
    const builder = mountFrontEndStrategeBuilder(document);
    const tabs = [...document.querySelectorAll('.dash-tab')];

    expect(document.querySelector('.dash-tabs')).toHaveAttribute('role', 'navigation');
    expect(tabs[0]).toHaveAttribute('aria-current', 'location');
    expect(tabs.every(tab => !tab.hasAttribute('role') && !tab.hasAttribute('aria-selected'))).toBe(true);
    tabs[1].click();
    expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
    expect(tabs[1]).toHaveAttribute('aria-current', 'location');
    expect(window.__gabrielFrontEndStrategeBuilder).toBe(builder);
  });

  it('signale un débordement horizontal mesuré dans le DOM final', () => {
    const dashboard = renderDashboard();
    const builder = createFrontEndStrategeBuilder(document);
    builder.run();
    const deliverable = dashboard.querySelector('.sfb-deliverable');
    Object.defineProperty(deliverable, 'clientWidth', { configurable: true, value: 300 });
    Object.defineProperty(deliverable, 'scrollWidth', { configurable: true, value: 460 });

    const report = auditStrategistFrontend(document);
    expect(report.status).toBe('warning');
    expect(report.issues).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: 'horizontal-overflow' }),
    ]));
    expect(deliverable).toHaveClass('sfb-has-horizontal-overflow');
  });

  it('réévalue automatiquement un livrable ajouté après le premier rendu', async () => {
    const dashboard = renderDashboard();
    mountFrontEndStrategeBuilder(document);
    const lateCard = document.createElement('article');
    lateCard.className = 'kpi-card';
    lateCard.innerHTML = `<div class="kpi-value kpi-value--text">${'Nouveau texte détaillé '.repeat(15)}</div>`;
    dashboard.querySelector('#dash-panel-synthese').append(lateCard);

    await vi.waitFor(() => {
      expect(lateCard).toHaveClass('sfb-deliverable');
      expect(lateCard).toHaveAttribute('data-sfb-density', 'extended');
    });
  });

  it('masque un livrable vide puis le réaffiche dès que son contenu arrive', () => {
    const dashboard = renderDashboard();
    const emptyCard = document.createElement('article');
    emptyCard.className = 'strat-card';
    dashboard.querySelector('#dash-panel-synthese').append(emptyCard);
    const builder = createFrontEndStrategeBuilder(document);

    builder.run();
    expect(emptyCard).toHaveClass('sfb-deliverable', 'sfb-empty-deliverable');

    emptyCard.textContent = 'Contenu stratégique chargé';
    builder.run();
    expect(emptyCard).not.toHaveClass('sfb-empty-deliverable');
  });

  it('attend proprement tant que le tableau de bord n’existe pas', () => {
    document.body.innerHTML = '';
    expect(auditStrategistFrontend(document)).toMatchObject({
      ready: false,
      status: 'waiting',
      sections: 0,
    });
  });
});
