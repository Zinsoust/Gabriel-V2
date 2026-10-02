/*
 * Ariane — adaptation du parcours Lovable au frontend Gabriel.
 * Ce fichier ne fait aucun appel métier : il met en forme les états et les
 * livrables déjà produits par stratege.html.
 */
(function () {
  'use strict';

  /* Dans Gabriel V2, AgentWorkspace et Front End Stratège Builder sont les
     seuls propriétaires de la présentation embarquée. Ce script reste actif
     pour /stratege en page autonome, mais ne duplique plus le panneau de
     contexte ni la transformation des livrables dans l'iframe. */
  if (document.body.classList.contains('is-embedded-agent')) return;

  var CHAPTERS = {
    synthese: {
      nav: '01  Synthèse',
      kicker: '01 · Analyse stratégique',
      title: 'La décision en un regard'
    },
    marketing: {
      nav: '02  Diagnostic',
      kicker: '02 · Diagnostic stratégique',
      title: 'La situation en un regard'
    },
    branding: {
      nav: '03  Opportunités',
      kicker: '03 · Opportunités détectées',
      title: 'Là où le levier est le plus fort'
    },
    plan: {
      nav: '04  Priorités',
      kicker: '04 · Direction recommandée',
      title: 'Vos priorités'
    },
    decision: {
      nav: '05  Preuves & décision',
      kicker: '05 · Données, preuves et regard critique',
      title: 'Ce qui soutient cette décision'
    }
  };

  function forceWhiteCanvas() {
    document.documentElement.setAttribute('data-theme', 'light');
  }

  function enhanceContextPanel() {
    var side = document.getElementById('interview-side');
    if (!side || side.querySelector('.st-context-intro')) return;
    var progress = side.querySelector('.ctx-progress');
    if (!progress) return;

    var intro = document.createElement('div');
    intro.className = 'st-context-intro';
    intro.innerHTML =
      '<p>Ariane utilise uniquement les informations réellement reliées à ce workspace.</p>';
    progress.insertAdjacentElement('afterend', intro);
  }

  function syncContextState() {
    var side = document.getElementById('interview-side');
    var badge = document.getElementById('ctx-badge');
    if (!side || !badge) return;
    side.setAttribute('data-context-state',
      badge.classList.contains('ready') ? 'ready' :
      badge.classList.contains('partial') ? 'partial' : 'empty');
  }

  function enhanceComposer() {
    var composer = document.querySelector('.chat-input-row');
    if (!composer) return;
    composer.setAttribute('aria-label', 'Écrire à Ariane');
    var input = document.getElementById('chat-input');
    if (input) input.setAttribute('placeholder', 'Écrivez votre réponse ou utilisez le micro…');
    var messages = document.getElementById('chat-messages');
    if (messages) messages.setAttribute('aria-label', 'Conversation avec Ariane');
  }

  function reportDecision(data) {
    if (!data || typeof data !== 'object') return 'Votre stratégie, clarifiée et prête à être déployée.';
    var executive = data.executive_decision || {};
    return executive.one_sentence_decision || data.decision_centrale ||
      data.message_central || data.titre ||
      'Votre stratégie, clarifiée et prête à être déployée.';
  }

  function createReportCover(data) {
    var cover = document.createElement('header');
    cover.className = 'st-report-cover';
    var date = new Intl.DateTimeFormat('fr-FR', {
      day: 'numeric', month: 'long', year: 'numeric'
    }).format(new Date());
    cover.innerHTML =
      '<div class="st-report-meta"><span>Analyse stratégique</span><i></i><span>Analyse terminée · ' + date + '</span></div>' +
      '<h1 class="st-report-title">Rapport stratégique</h1>' +
      '<p class="st-report-subtitle">' + escapeHtml(reportDecision(data)) + '</p>';
    return cover;
  }

  function scrollToChapter(key) {
    var panel = document.getElementById('dash-panel-' + key);
    if (!panel) return;
    panel.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'start'
    });
  }

  function setActiveReportTab(key) {
    document.querySelectorAll('#strat-dashboard .dash-tab').forEach(function (button) {
      var active = button.getAttribute('data-st-key') === key;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
  }

  var reportIntersectionObserver = null;

  function watchReportChapters() {
    if (reportIntersectionObserver) reportIntersectionObserver.disconnect();
    if (!('IntersectionObserver' in window)) return;
    reportIntersectionObserver = new IntersectionObserver(function (entries) {
      var visible = entries
        .filter(function (entry) { return entry.isIntersecting; })
        .sort(function (a, b) { return b.intersectionRatio - a.intersectionRatio; });
      if (visible[0]) setActiveReportTab(visible[0].target.id.replace('dash-panel-', ''));
    }, { rootMargin: '-20% 0px -62% 0px', threshold: [0, .1, .35] });
    document.querySelectorAll('#strat-dashboard .dash-panel').forEach(function (panel) {
      reportIntersectionObserver.observe(panel);
    });
  }

  function enhanceReport() {
    var dash = document.getElementById('strat-dashboard');
    if (!dash || !dash.classList.contains('strat-cockpit-active')) return;
    var panels = Array.from(dash.querySelectorAll('.dash-panel'));
    var tabs = Array.from(dash.querySelectorAll('.dash-tab'));
    if (!panels.length || !tabs.length) return;

    var existingCover = dash.querySelector('.st-report-cover');
    if (!existingCover) {
      var actionBar = dash.querySelector('.strat-action-bar');
      var cover = createReportCover(window._lastStratData || null);
      if (actionBar) actionBar.insertAdjacentElement('afterend', cover);
      else dash.prepend(cover);
    }

    panels.forEach(function (panel) {
      var key = panel.id.replace('dash-panel-', '');
      var chapter = CHAPTERS[key];
      panel.classList.remove('hidden');
      panel.setAttribute('aria-hidden', 'false');
      if (!chapter || panel.querySelector('.st-chapter-head')) return;
      var head = document.createElement('header');
      head.className = 'st-chapter-head';
      head.innerHTML =
        '<div><div class="st-chapter-kicker">' + chapter.kicker + '</div>' +
        '<h2>' + chapter.title + '</h2></div>';
      panel.prepend(head);
    });

    tabs.forEach(function (button) {
      var key = (button.getAttribute('aria-controls') || '').replace('dash-panel-', '');
      var chapter = CHAPTERS[key];
      if (!chapter) return;
      button.textContent = chapter.nav;
      button.setAttribute('data-st-key', key);
      button.onclick = function (event) {
        event.preventDefault();
        setActiveReportTab(key);
        scrollToChapter(key);
      };
    });

    dash.setAttribute('data-st-enhanced', 'true');
    watchReportChapters();
  }

  function observeDynamicViews() {
    var side = document.getElementById('interview-side');
    if (side) {
      new MutationObserver(function () { syncContextState(); })
        .observe(side, { subtree: true, attributes: true, attributeFilter: ['class'] });
    }

    var dash = document.getElementById('strat-dashboard');
    if (dash) {
      var scheduled = false;
      new MutationObserver(function () {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(function () {
          scheduled = false;
          enhanceReport();
        });
      }).observe(dash, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    }
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  forceWhiteCanvas();
  enhanceContextPanel();
  enhanceComposer();
  syncContextState();
  observeDynamicViews();
  enhanceReport();
})();
