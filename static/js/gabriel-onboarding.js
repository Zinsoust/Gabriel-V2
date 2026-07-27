(function () {
  'use strict';

  const STORAGE_DONE = 'gabriel_onboarding_done_v1';
  const STORAGE_STOPPED = 'gabriel_onboarding_stopped_v1';
  const STORAGE_INDEX = 'gabriel_onboarding_index_v1';
  const HIGHLIGHT_CLASS = 'gb-tour-highlight';

  const steps = [
    {
      title: 'Bienvenue dans Gabriel',
      body: `Bienvenue dans Gabriel. Chaque projet devient un environnement de décision : une analyse psychologique, une stratégie business et des contenus alignés avec votre audience.<p>Ce parcours en 7 étapes vous montre l’essentiel. Vous pouvez l’ignorer à tout moment.</p>`,
      cta: 'Commencer le tutoriel',
    },
    {
      selector: '[data-tour="create-folder"]',
      path: '/dossiers',
      title: '1. Créer votre dossier stratégique',
      body: `Créez un dossier pour la décision ou le projet à éclairer, puis donnez-lui un nom et un objectif précis.<p>Exemple : “Comprendre les attentes de mon audience avant de lancer mon offre.”</p>`,
    },
    {
      selector: ['#youtubeUrl', '[data-tour="source-section"]', '.analyse-btn', '#df-analyse-btn'],
      path: '/psychologue',
      before: () => window.switchTab?.('youtube'),
      title: '2. Comprendre votre audience',
      body: `Collez une vidéo YouTube ou des commentaires, puis lancez le Psychologue. Il révèle les émotions, aspirations, douleurs, objections et segments dominants qui serviront de base aux décisions suivantes.`,
    },
    {
      selector: ['.ctx-panel', '#chat-input', '[data-tour="stratege-start"]'],
      path: '/stratege',
      title: '3. Décrire votre contexte business',
      body: `Présentez votre situation réelle : offre, ressources, budget, équipe, audience, positionnement et objectif. Plus ce contexte est précis, plus les recommandations seront réalistes et directement applicables.`,
    },
    {
      selector: ['#strat-launch-btn', '[data-tour="stratege-result"]', '#strat-dashboard', '.strat-layout'],
      path: '/stratege',
      title: '4. Transformer l’analyse en décision',
      body: `Générez la stratégie lorsque votre contexte est complet. Commencez par les décisions prioritaires, l’offre, le positionnement et les actions immédiates, puis consultez les risques et opportunités.`,
    },
    {
      selector: ['#cre-card', '#cre-req', '#cre-gen', '[data-tour="createur-start"]'],
      path: '/createur',
      title: '5. Créer des contenus alignés',
      body: `Le Créateur combine l’analyse de l’audience et la stratégie. Choisissez votre intention, votre tonalité, votre format et votre canal, puis générez un contenu fondé sur les mots et besoins réels de votre marché.`,
    },
    {
      title: 'Vous êtes prêt',
      body: `Vous connaissez maintenant le parcours Gabriel : créer un dossier, comprendre l’audience, décider une stratégie et produire les contenus qui l’exécutent.`,
      final: true,
    },
  ];

  let current = 0;
  let active = false;
  let forced = false;
  let card = null;
  let backdrop = null;
  let highlighted = null;

  function pathMatches(step) {
    if (!step.path) return true;
    return window.location.pathname === step.path;
  }

  function isVisible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  }

  function targetFor(step, options) {
    const ignorePath = Boolean(options && options.ignorePath);
    if (!step.selector || (!ignorePath && !pathMatches(step))) return null;
    const selectors = Array.isArray(step.selector) ? step.selector : [step.selector];
    for (const selector of selectors) {
      try {
        const el = document.querySelector(selector);
        if (isVisible(el)) return el;
      } catch (_) {}
    }
    return null;
  }

  function localRouteTargetFor(step) {
    if (!step.selector) return null;
    const selectors = (Array.isArray(step.selector) ? step.selector : [step.selector])
      .filter(selector => typeof selector === 'string' && !selector.trim().startsWith('[data-tour='));
    if (!selectors.length) return null;
    return targetFor({ ...step, selector: selectors }, { ignorePath: true });
  }

  function ensureDom() {
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.className = 'gb-tour-backdrop';
      document.body.appendChild(backdrop);
    }
    if (!card) {
      card = document.createElement('section');
      card.className = 'gb-tour-card';
      card.setAttribute('role', 'dialog');
      card.setAttribute('aria-live', 'polite');
      card.setAttribute('aria-label', 'Tutoriel Gabriel');
      document.body.appendChild(card);
    }
  }

  function clearHighlight() {
    if (highlighted) highlighted.classList.remove(HIGHLIGHT_CLASS);
    highlighted = null;
  }

  function stop(saveAsStopped) {
    active = false;
    clearHighlight();
    if (card) card.classList.remove('is-visible');
    if (backdrop) backdrop.classList.remove('is-visible');
    if (saveAsStopped) {
      localStorage.setItem(STORAGE_STOPPED, '1');
      localStorage.removeItem(STORAGE_INDEX);
    }
  }

  function finish() {
    localStorage.setItem(STORAGE_DONE, '1');
    localStorage.removeItem(STORAGE_STOPPED);
    localStorage.removeItem(STORAGE_INDEX);
    stop(false);
  }

  function positionCard(target) {
    if (!card) return;
    const margin = 16;
    if (!target || window.innerWidth < 720) {
      card.style.left = `${Math.max(margin, Math.round((window.innerWidth - Math.min(390, window.innerWidth - 32)) / 2))}px`;
      card.style.top = `${Math.max(80, Math.round(window.innerHeight * 0.18))}px`;
      return;
    }

    const rect = target.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    let left = rect.right + 22;
    let top = rect.top;

    if (left + cardRect.width + margin > window.innerWidth) left = rect.left - cardRect.width - 22;
    if (left < margin) left = Math.min(window.innerWidth - cardRect.width - margin, margin);
    if (top + cardRect.height + margin > window.innerHeight) top = window.innerHeight - cardRect.height - margin;
    if (top < margin) top = margin;

    card.style.left = `${Math.round(left)}px`;
    card.style.top = `${Math.round(top)}px`;
  }

  function updateBackdrop(target) {
    if (!backdrop) return;
    if (!target) {
      backdrop.style.setProperty('--gb-tour-x', '50%');
      backdrop.style.setProperty('--gb-tour-y', '50%');
      return;
    }
    const rect = target.getBoundingClientRect();
    backdrop.style.setProperty('--gb-tour-x', `${Math.round(rect.left + rect.width / 2)}px`);
    backdrop.style.setProperty('--gb-tour-y', `${Math.round(rect.top + rect.height / 2)}px`);
  }

  function render() {
    if (!active) return;
    ensureDom();
    clearHighlight();

    const step = steps[current] || steps[0];
    try { step.before?.(); } catch (_) {}

    window.setTimeout(() => {
      const localTarget = pathMatches(step) ? targetFor(step) : localRouteTargetFor(step);
      const needsRoute = Boolean(step.path && !pathMatches(step) && !localTarget);
      const target = needsRoute ? null : localTarget;
      if (target) {
        highlighted = target;
        highlighted.classList.add(HIGHLIGHT_CLASS);
        highlighted.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
      }

      const progress = `${current + 1}/${steps.length}`;
      const prevDisabled = current === 0 ? 'disabled aria-disabled="true"' : '';
      const primaryLabel = needsRoute ? 'Ouvrir la page' : (step.final ? 'Terminer' : (step.cta || 'Suivant'));
      const routeNote = needsRoute ? `<p class="gb-tour-route-note">Cette étape se trouve sur une autre page. Gabriel peut vous y emmener maintenant.</p>` : '';
      const body = `${step.body || ''}${routeNote}`;

      card.innerHTML = `
        <div class="gb-tour-top">
          <div class="gb-tour-progress">Étape ${progress}</div>
          <button class="gb-tour-close" type="button" aria-label="Fermer le tutoriel">×</button>
        </div>
        <div class="gb-tour-title">${escapeHtml(step.title || 'Tutoriel Gabriel')}</div>
        <div class="gb-tour-text">${body}</div>
        <div class="gb-tour-actions">
          <div class="gb-tour-actions-left">
            <button class="gb-tour-btn ghost" type="button" data-action="skip">Ignorer</button>
          </div>
          <div class="gb-tour-actions-right">
            <button class="gb-tour-btn" type="button" data-action="prev" ${prevDisabled}>Précédent</button>
            ${step.final ? '<button class="gb-tour-btn" type="button" data-action="dossiers">Créer mon premier dossier</button>' : ''}
            <button class="gb-tour-btn primary" type="button" data-action="next">${primaryLabel}</button>
          </div>
        </div>
      `;

      card.querySelector('.gb-tour-close')?.addEventListener('click', () => stop(true));
      card.querySelector('[data-action="skip"]')?.addEventListener('click', () => stop(true));
      card.querySelector('[data-action="prev"]')?.addEventListener('click', previous);
      card.querySelector('[data-action="next"]')?.addEventListener('click', next);
      card.querySelector('[data-action="dossiers"]')?.addEventListener('click', () => {
        finish();
        window.location.href = '/dossiers';
      });

      updateBackdrop(target);
      backdrop.classList.add('is-visible');
      card.classList.add('is-visible');
      requestAnimationFrame(() => positionCard(target));
      localStorage.setItem(STORAGE_INDEX, String(current));
    }, 80);
  }

  function next() {
    if (!active) return;
    const step = steps[current] || {};
    const localTarget = pathMatches(step) ? targetFor(step) : localRouteTargetFor(step);
    if (step.path && !pathMatches(step) && !localTarget) {
      localStorage.setItem(STORAGE_INDEX, String(current));
      window.location.href = step.path;
      return;
    }
    if (current >= steps.length - 1) return finish();
    current += 1;
    render();
  }

  function previous() {
    if (!active || current <= 0) return;
    current -= 1;
    render();
  }

  function start(force) {
    forced = Boolean(force);
    if (!forced && (localStorage.getItem(STORAGE_DONE) || localStorage.getItem(STORAGE_STOPPED))) return;
    active = true;
    current = forced ? 0 : Number(localStorage.getItem(STORAGE_INDEX) || 0);
    if (!Number.isFinite(current) || current < 0 || current >= steps.length) current = 0;
    if (forced) {
      localStorage.removeItem(STORAGE_DONE);
      localStorage.removeItem(STORAGE_STOPPED);
    }
    render();
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  window.GabrielOnboarding = {
    start,
    stop: () => stop(true),
    reset: () => {
      localStorage.removeItem(STORAGE_DONE);
      localStorage.removeItem(STORAGE_STOPPED);
      localStorage.removeItem(STORAGE_INDEX);
    },
  };

  window.addEventListener('resize', () => {
    if (!active) return;
    const target = targetFor(steps[current]);
    updateBackdrop(target);
    positionCard(target);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && active) stop(true);
  });

  document.addEventListener('DOMContentLoaded', () => {
    const onboardingPaths = ['/dossiers', '/psychologue', '/stratege', '/createur'];
    if (onboardingPaths.includes(window.location.pathname) || localStorage.getItem(STORAGE_INDEX)) {
      window.setTimeout(() => start(false), 450);
    }
  });
})();
