/* ═══════════════════════════════════════════════════════════════════════════
 * CREATOR WORKSPACE — le conteneur du parcours de création (Phase 1)
 *
 * Jumeau volontaire de static/js/strategy-workspace.js : même discipline de
 * machine à états, même coquille visuelle. Rôle unique : savoir à quelle ÉTAPE
 * du parcours de création on se trouve, et faire apparaître l'écran
 * correspondant. Rien d'autre.
 *
 * Ce module ne connaît ni le contenu des écrans, ni les appels réseau métier
 * (génération, raffinage), ni le texte produit. Un écran s'enregistre lui-même
 * avec ce qu'il doit faire pour apparaître et disparaître.
 *
 * Séparation volontaire (miroir du Stratège) :
 *   - static/js/creator-workspace.js  → le parcours côté écran (ce fichier)
 *   - templates/createur.html         → le CONTENU de chaque écran
 *
 * Le parcours est une machine à états : aucune navigation entre pages, aucune
 * redirection, aucun rechargement.
 *
 * Divergence assumée avec le Stratège : le parcours de création est court et
 * son état (format, émotion, ton choisis) est éphémère — il n'y a rien à
 * "reprendre" à mi-chemin comme un long entretien. goTo() reste donc purement
 * local, sans persistance serveur. Si un jour on veut reprendre une création
 * en cours, on ajoutera un core/creator_session.py calqué sur
 * core/strategy_session.py, et goTo() postera vers /creator-session/step —
 * exactement comme strategy-workspace.js. Le patron est prêt pour ça.
 * ═══════════════════════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  /**
   * Le tunnel complet de la création.
   *   brief      — format + demande (le "quoi")
   *   emotion    — facultatif : ce que l'audience doit RESSENTIR (l'impact)
   *   tone       — la voix du texte (le "comment ça sonne")
   *   generating — génération en cours
   *   result     — le contenu produit + raffinage
   * @type {string[]}
   */
  var STEPS = ['brief', 'emotion', 'tone', 'generating', 'result'];

  /**
   * Un écran du parcours.
   * @typedef {Object} Screen
   * @property {function():void} [enter] Appelé quand l'étape devient active.
   * @property {function():void} [leave] Appelé quand on quitte l'étape.
   */

  /** @type {Object.<string, Screen>} */
  var screens = {};

  /** @type {string} */
  var currentStep = 'brief';

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
      console.warn('[CreatorWorkspace] étape inconnue : ' + step);
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

  /**
   * Affiche une étape. Purement local et instantané.
   * @param {string} step
   */
  function show(step) {
    if (!screens[step]) {
      console.warn('[CreatorWorkspace] étape sans écran : ' + step);
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
   * Avance dans le parcours. Purement local (voir l'en-tête : état éphémère,
   * pas de persistance serveur pour le Créateur en Phase 1).
   * @param {string} step
   */
  function goTo(step) {
    show(step);
  }

  /**
   * Affiche la première étape développée. Appelé une fois au chargement.
   * @returns {string} l'étape affichée
   */
  function start() {
    var step = STEPS.find(function (s) { return !!screens[s]; }) || 'brief';
    show(step);
    return step;
  }

  global.CreatorWorkspace = {
    STEPS: STEPS,
    register: register,
    onChange: onChange,
    getStep: getStep,
    show: show,
    goTo: goTo,
    start: start
  };
})(window);
