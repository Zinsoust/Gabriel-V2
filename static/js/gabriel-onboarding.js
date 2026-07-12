(function () {
  'use strict';

  const STORAGE_DONE = 'gabriel_onboarding_done_v1';
  const STORAGE_STOPPED = 'gabriel_onboarding_stopped_v1';
  const STORAGE_INDEX = 'gabriel_onboarding_index_v1';
  const HIGHLIGHT_CLASS = 'gb-tour-highlight';

  const steps = [
    {
      title: 'Bienvenue dans Gabriel',
      body: `Bienvenue dans Gabriel. Ici, chaque projet commence par un dossier stratégique. Un dossier vous permet de centraliser une analyse, une stratégie, des contenus et vos décisions business.<p>Gabriel vous aide à transformer les réactions du marché en décisions business, stratégie et contenu.</p>`,
      cta: 'Commencer le tutoriel',
    },
    {
      selector: '[data-tour="create-folder"]',
      path: '/dossiers',
      title: 'Créer un dossier stratégique',
      body: `Commencez par créer un dossier stratégique. Il représente une décision ou un projet à éclairer : lancer une offre, comprendre une audience, analyser un concurrent ou préparer une campagne.`,
    },
    {
      selector: '[data-tour="folder-title"]',
      path: '/dossiers',
      before: () => window.openModal?.(),
      title: 'Nommer le dossier',
      body: `Donnez un nom clair à votre dossier. Exemple : “Lancement offre coaching”, “Analyse audience YouTube”, “Benchmark concurrent”, “Nouvelle campagne Instagram”.`,
    },
    {
      selector: '[data-tour="folder-objective"]',
      path: '/dossiers',
      before: () => window.openModal?.(),
      title: 'Définir l’objectif',
      body: `Ajoutez l’objectif du dossier. Plus l’objectif est clair, plus Gabriel peut vous aider à prendre une bonne décision.<p>Exemple : “Comprendre ce que mon audience attend avant de lancer mon offre.”</p>`,
    },
    {
      selector: '[data-tour="source-section"]',
      title: 'Ajouter une source',
      body: `Ajoutez une source de marché : commentaires, fichier CSV/Excel/JSON, avis clients ou lien compatible. Gabriel utilise cette matière pour comprendre ce que votre marché dit réellement.`,
    },
    {
      selector: ['#df-analyse-btn', '#step-btn-psychologue', '[data-tour="psychologue-start"]'],
      path: '/psychologue',
      title: 'Lancer le Psychologue',
      body: `L’Agent Psychologue analyse les réactions. Il détecte les désirs, frustrations, objections, émotions et signaux dominants de votre audience.<p>Son rôle n’est pas de vendre. Son rôle est de comprendre.</p>`,
    },
    {
      selector: '[data-tour="psychologue-dashboard"]',
      path: '/psychologue',
      title: 'Lire le Dashboard',
      body: `Le Dashboard vous donne une première lecture rapide : tendances, signaux, clusters, émotions, objections et opportunités.`,
    },
    {
      selector: '[data-tour="psychologue-interpretation"]',
      path: '/psychologue',
      title: 'Lire l’Interprétation',
      body: `L’Interprétation explique ce que ces signaux signifient humainement. Elle vous aide à comprendre pourquoi votre audience réagit ainsi.`,
    },
    {
      selector: '[data-tour="psychologue-personas"]',
      path: '/psychologue',
      title: 'Découvrir les Personas',
      body: `Les Personas représentent les grands profils d’audience détectés. Ils vous aident à mieux adapter votre offre, votre message et votre contenu.`,
    },
    {
      selector: ['#strat-launch-btn', '#step-btn-stratege', '[data-tour="stratege-start"]'],
      path: '/stratege',
      title: 'Lancer le Stratège',
      body: `L’Agent Stratège transforme l’analyse en décision business. Il vous aide à savoir quoi vendre, à qui, avec quel positionnement et quelle action prioritaire.<p>Son rôle est de décider.</p>`,
    },
    {
      selector: '[data-tour="stratege-result"]',
      path: '/stratege',
      title: 'Comprendre la décision recommandée',
      body: `Lisez d’abord la décision recommandée. Gabriel ne vous donne pas seulement des idées : il vous aide à choisir la meilleure direction à prendre maintenant.`,
    },
    {
      selector: ['#cre-gen', '#cre-card', '#step-btn-createur', '[data-tour="createur-start"]'],
      path: '/createur',
      title: 'Lancer le Créateur',
      body: `L’Agent Créateur transforme la stratégie en contenu concret : script, post, email, accroche ou message commercial.<p>Son rôle est d’écrire en respectant ce que le Psychologue a compris et ce que le Stratège a décidé.</p>`,
    },
    {
      selector: '[data-tour="orchestrator"]',
      path: '/createur',
      title: 'Utiliser l’Orchestrateur',
      body: `L’Orchestrateur est votre conseiller transversal. Il relie l’analyse, la stratégie et les contenus. Vous pouvez lui demander : “Quelle décision dois-je prendre ?”, “Est-ce que mon contenu est cohérent ?”, “Quelle est la prochaine action ?”.`,
    },
    {
      title: 'Vous êtes prêt',
      body: `Vous êtes prêt. Créez un dossier, ajoutez une source, puis laissez Gabriel transformer les signaux du marché en décisions et en contenus exploitables.`,
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

  function targetFor(step) {
    if (!step.selector || !pathMatches(step)) return null;
    const selectors = Array.isArray(step.selector) ? step.selector : [step.selector];
    for (const selector of selectors) {
      try {
        const el = document.querySelector(selector);
        if (isVisible(el)) return el;
      } catch (_) {}
    }
    return null;
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
      const needsRoute = Boolean(step.path && !pathMatches(step));
      const target = needsRoute ? null : targetFor(step);
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
            <button class="gb-tour-btn ghost" type="button" data-action="skip">Passer</button>
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
    if (step.path && !pathMatches(step)) {
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
    if (window.location.pathname === '/dossiers' || localStorage.getItem(STORAGE_INDEX)) {
      window.setTimeout(() => start(false), 450);
    }
  });
})();
