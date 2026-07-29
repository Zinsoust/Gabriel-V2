/* ═══════════════════════════════════════════════════════════════════════════
 * STRATEGY WORKSPACE — le conteneur du parcours stratégique (Phase 1)
 *
 * Rôle unique : savoir à quelle ÉTAPE du parcours on se trouve, et faire
 * apparaître l'écran correspondant. Rien d'autre.
 *
 * Ce module ne connaît ni le contenu des écrans, ni les appels réseau
 * métier, ni la conversation. Un écran s'enregistre lui-même avec ce qu'il
 * doit faire pour apparaître et disparaître — c'est ce qui permettra
 * d'ajouter les étapes suivantes (analyse, synthèse, marketing…) sans jamais
 * revenir modifier ce fichier.
 *
 * Séparation volontaire :
 *   - core/strategy_session.py        → le parcours côté serveur (vérité)
 *   - static/js/strategy-workspace.js → le parcours côté écran (ce fichier)
 *   - templates/stratege.html         → le CONTENU de chaque écran
 *
 * Le parcours est une machine à états : aucune navigation entre pages,
 * aucune redirection, aucun rechargement.
 * ═══════════════════════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  /**
   * Le tunnel complet. Doit rester identique à JOURNEY_STEPS dans
   * core/strategy_session.py — le serveur reste la source de vérité, cette
   * liste ne sert qu'à valider localement avant d'appeler le réseau.
   * @type {string[]}
   */
  var STEPS = [
    'welcome', 'interview', 'conversation', 'analysis', 'summary',
    'marketing', 'branding', 'action_plan', 'decision', 'export'
  ];

  /**
   * Un écran du parcours.
   * @typedef {Object} Screen
   * @property {function():void} [enter] Appelé quand l'étape devient active.
   * @property {function():void} [leave] Appelé quand on quitte l'étape.
   */

  /** @type {Object.<string, Screen>} */
  var screens = {};

  /** @type {string} */
  var currentStep = 'welcome';

  /** @type {string} */
  var sessionId = '';

  /** @type {Array.<function(string, string):void>} */
  var listeners = [];

  /**
   * Déclare l'écran d'une étape. Les étapes non encore développées n'en
   * enregistrent aucun : le parcours les connaît mais ne peut pas y aller.
   * @param {string} step
   * @param {Screen} screen
   */
  function register(step, screen) {
    if (STEPS.indexOf(step) === -1) {
      console.warn('[StrategyWorkspace] étape inconnue : ' + step);
      return;
    }
    screens[step] = screen || {};
  }

  /**
   * Prévenu à chaque changement d'étape (pour la chrome autour des écrans :
   * panneau latéral, barre de saisie, en-tête…).
   * @param {function(string, string):void} fn (nouvelleEtape, ancienneEtape)
   */
  function onChange(fn) {
    if (typeof fn === 'function') listeners.push(fn);
  }

  /** @returns {string} */
  function getStep() { return currentStep; }

  /** @returns {string} */
  function getSessionId() { return sessionId; }

  /**
   * Affiche une étape. Purement local et instantané — la persistance est
   * faite séparément par goTo(), pour que l'écran n'attende jamais le
   * réseau pour apparaître.
   * @param {string} step
   */
  function show(step) {
    if (!screens[step]) {
      console.warn('[StrategyWorkspace] étape sans écran : ' + step);
      return;
    }
    var previous = currentStep;
    if (previous !== step && screens[previous] && screens[previous].leave) {
      screens[previous].leave();
    }
    currentStep = step;
    if (screens[step].enter) screens[step].enter();
    listeners.forEach(function (fn) {
      try { fn(step, previous); } catch (e) { console.error(e); }
    });
  }

  /**
   * Avance dans le parcours : l'écran change tout de suite, l'enregistrement
   * côté serveur suit. Si le réseau échoue, l'utilisateur n'est pas bloqué —
   * il perd seulement la reprise à cette étape au prochain chargement.
   * @param {string} step
   */
  function goTo(step) {
    show(step);
    fetch('/strategy-session/step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step: step })
    }).catch(function () { /* silencieux : l'affichage a déjà eu lieu */ });
  }

  /**
   * Crée ou reprend la session, puis affiche l'étape en cours. Appelé une
   * fois au chargement de la Salle de Conseil.
   * @returns {Promise<string>} l'étape affichée
   */
  function start() {
    return fetch('/strategy-session')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var step = (data && data.current_step) || 'welcome';
        sessionId = (data && data.session_id) || '';
        if (!screens[step]) step = 'welcome';
        show(step);
        return step;
      })
      .catch(function () { show('welcome'); return 'welcome'; });
  }

  global.StrategyWorkspace = {
    STEPS: STEPS,
    register: register,
    onChange: onChange,
    getStep: getStep,
    getSessionId: getSessionId,
    show: show,
    goTo: goTo,
    start: start
  };
})(window);
