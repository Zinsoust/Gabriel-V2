import React, { useEffect, useMemo, useRef } from 'react';
import { Icon } from '../icons.jsx';
import { agents, getAgent } from '../agent-registry.js';
import { mountFrontEndStrategeBuilder } from '../tools/front-end-stratege-builder.js';

function agentUrl(agent, folderId) {
  const params = new URLSearchParams({ embedded: '1' });
  if (folderId) params.set('folder_id', folderId);
  return `${agent.path}?${params.toString()}`;
}

/**
 * Les agents conservent leur vraie page et leurs appels backend. L'iframe ne
 * sert qu'à placer cet espace dans la colonne centrale de Gabriel V2 ; le
 * mode embedded retire la navigation legacy qui ferait doublon.
 */
function agentIdForPath(pathname) {
  return Object.values(agents).find(candidate => candidate.path === pathname)?.id || null;
}

/* Cet état de réflexion est créé dans l'iframe au moment de son intégration
   V2. Il n'existe donc pas dans le template historique du Stratège. */
function addStrategistThinkingState(frameDocument) {
  const chatWindow = frameDocument.querySelector('.chat-window');
  const panel = frameDocument.querySelector('.ctx-panel');
  if (!chatWindow || !panel) return;

  let thinking = frameDocument.getElementById('gv2-audio-thinking');
  if (!thinking) {
    thinking = frameDocument.createElement('section');
    thinking.id = 'gv2-audio-thinking';
    thinking.className = 'gv2-audio-thinking';
    thinking.setAttribute('role', 'status');
    thinking.setAttribute('aria-live', 'polite');
    thinking.innerHTML = `
      <div class="gv2-audio-thinking-surface">
        <span class="gv2-audio-thinking-dots" aria-hidden="true"><i></i><i></i></span>
        <div class="gv2-audio-thinking-preview"><span>V</span><p data-gv2-audio-preview></p><b aria-hidden="true"></b></div>
        <div class="gv2-audio-thinking-status"><i aria-hidden="true"></i><em>Ariane réfléchit…</em></div>
        <p class="gv2-audio-thinking-copy">Je relie les éléments de votre réponse à votre situation.</p>
      </div>`;
    chatWindow.append(thinking);
  }

  const sync = () => {
    const isThinking = panel.dataset.interviewState === 'transcribing';
    thinking.classList.toggle('is-active', isThinking);
    if (!isThinking) return;

    const transcript = frameDocument.querySelector('#listening-transcript')?.textContent?.trim();
    const draft = frameDocument.querySelector('#chat-input')?.value?.trim();
    const rawPreview = transcript && transcript !== 'Je vous écoute…' ? transcript : draft;
    const preview = (rawPreview || 'Votre réponse est en cours de préparation.').replace(/\s+/g, ' ');
    const previewNode = thinking.querySelector('[data-gv2-audio-preview]');
    if (previewNode) previewNode.textContent = preview.length > 110 ? `${preview.slice(0, 107).trimEnd()}…` : preview;
  };

  sync();
  if (!chatWindow.__gv2ThinkingObserver && frameDocument.defaultView?.MutationObserver) {
    const observer = new frameDocument.defaultView.MutationObserver(sync);
    observer.observe(panel, { attributes: true, attributeFilter: ['data-interview-state'] });
    chatWindow.__gv2ThinkingObserver = observer;
  }
}

/*
 * Les outils spécialisés restent des pages autonomes pour préserver leur
 * fonctionnement historique. Cette couche est toutefois injectée dans
 * l'instance iframe, et uniquement depuis le shell V2 : elle ne modifie ni
 * les templates ni les styles de Gabriel V1.
 */
function applyV2EmbeddedPresentation(frameDocument, agentId, darkMode) {
  if (!['stratege', 'psychologue'].includes(agentId) || !frameDocument?.head) return;

  if (agentId === 'stratege') {
    /* Le Stratège devient une interlocutrice identifiable dans l'espace V2.
       Ce remplacement vit dans l'iframe et ne réécrit pas la page historique. */
    const welcomeTitle = frameDocument.querySelector('#gate-welcome .gate-title');
    const welcomeCopy = frameDocument.querySelector('#gate-welcome .gate-sub');
    const audioLabel = frameDocument.querySelector('#gate-intro .gate-eyebrow');
    const audioQuestion = frameDocument.querySelector('#gate-intro .gate-question');
    const audioWrite = frameDocument.querySelector('#gate-intro .gate-write');
    const listeningTitle = frameDocument.querySelector('#listening-title');
    const listeningCopy = frameDocument.querySelector('#listening-overlay .listening-copy');
    if (welcomeTitle) welcomeTitle.textContent = 'Bonjour, je suis Ariane, votre stratège.';
    if (welcomeCopy) welcomeCopy.textContent = 'Ensemble, transformons vos ambitions et vos enjeux en une stratégie claire, solide et prête à être déployée.';
    if (audioLabel) audioLabel.textContent = 'Ariane · votre stratège';
    if (audioQuestion && !audioQuestion.textContent.trim()) audioQuestion.textContent = 'Exprimez votre besoin avec vos propres mots. Ariane en clarifiera les priorités et la suite.';
    if (audioWrite) audioWrite.textContent = 'Je préfère répondre par écrit';
    if (listeningTitle) listeningTitle.textContent = 'Ariane vous écoute.';
    if (listeningCopy) listeningCopy.textContent = 'Parlez librement. Votre réponse est retranscrite en direct.';
    addStrategistThinkingState(frameDocument);
    mountFrontEndStrategeBuilder(frameDocument);
  }

  const styleId = 'gabriel-v2-embedded-presentation';
  let style = frameDocument.getElementById(styleId);
  if (!style) {
    style = frameDocument.createElement('style');
    style.id = styleId;
    frameDocument.head.append(style);
  }

  style.textContent = agentId === 'psychologue' ? `
    /* Le nom de l'agent est déjà présent dans la navigation V2 : ce sur-titre
       fait doublon dans l'outil embarqué. */
    body.page-psychologue .page-label { display: none !important; }
    /* Le studio de réglage est un outil interne de la page historique. Dans
       le workbench V2, il n'apporte pas de valeur au travail courant. */
    body.is-embedded-agent.page-psychologue :is(.uxs-fab, .uxs, .uxs-toast) { display: none !important; }
    ${darkMode ? `
      /* Thème sombre appliqué à l'instance embarquée depuis Gabriel V2.
         Aucune feuille de style historique n'est modifiée. */
      body.is-embedded-agent.page-psychologue {
        --bg-main: #17191a !important;
        --bg-panel: #1d1f20 !important;
        --bg-card: #232526 !important;
        --bg-card-hover: #2c2e30 !important;
        --text-primary: #f2f3f3 !important;
        --text-secondary: #d3d5d5 !important;
        --text-muted: #a4a6a8 !important;
        --text-disabled: #777a7c !important;
        --champagne: #f0f1f1 !important;
        --champagne-light: #d9dbdc !important;
        --champagne-soft: #c6c8c9 !important;
        --border-soft: rgba(255,255,255,.11) !important;
        --border-medium: rgba(255,255,255,.17) !important;
        color: #f2f3f3 !important;
        color-scheme: dark !important;
        background: #17191a !important;
      }
      body.is-embedded-agent.page-psychologue :is(.app-layout, .app-main, .app-content) { background: #17191a !important; }
      body.is-embedded-agent.page-psychologue :is(.input-card, .url-input-row, .file-drop-zone, .chat-input-row, .sc-input-row) { background: #232526 !important; border-color: rgba(255,255,255,.13) !important; }
      body.is-embedded-agent.page-psychologue :is(input:not([type="checkbox"]):not([type="radio"]):not([type="range"]), textarea, select) { color: #f2f3f3 !important; caret-color: #f2f3f3 !important; background-color: #202223 !important; border-color: rgba(255,255,255,.16) !important; }
      body.is-embedded-agent.page-psychologue :is(input, textarea)::placeholder { color: #989b9d !important; }
      body.is-embedded-agent.page-psychologue select option { color: #f2f3f3 !important; background: #202223 !important; }
      body.is-embedded-agent.page-psychologue :is(.url-hint, .url-hint.is-busy, .url-hint.is-success, .status-msg, .comment-meta, .input-zone a) { color: #b1b3b5 !important; }
      /* Sources : les composants de cette page historique imposent leurs
         propres blancs. On les ramène dans la palette sombre V2, ici dans
         l'iframe uniquement. */
      body.is-embedded-agent.page-psychologue .input-card {
        background: linear-gradient(135deg, #1d1d19, #171815) !important;
        border-color: rgba(240,210,162,.24) !important;
      }
      body.is-embedded-agent.page-psychologue :is(.src-tabs, .card-footer) { border-color: rgba(240,210,162,.18) !important; }
      body.is-embedded-agent.page-psychologue .src-tab { color: #9d9589 !important; }
      body.is-embedded-agent.page-psychologue .src-tab.active { color: #f1dfc3 !important; }
      body.is-embedded-agent.page-psychologue .src-tab::after { background: #e0b978 !important; }
      body.is-embedded-agent.page-psychologue .src-tab:hover:not(.active) { color: #efe0ca !important; background: rgba(214,174,109,.08) !important; }
      body.is-embedded-agent.page-psychologue .source-platform {
        border-color: rgba(240,210,162,.23) !important;
        background: #26241f !important;
        color: #d7cbb9 !important;
      }
      body.is-embedded-agent.page-psychologue .source-platform:hover { border-color: #d7b273 !important; color: #fff2df !important; }
      body.is-embedded-agent.page-psychologue .source-platform.is-active {
        border-color: #e0ba7b !important;
        background: linear-gradient(135deg, #f0d29f, #d2a466) !important;
        color: #281e13 !important;
      }
      body.is-embedded-agent.page-psychologue .source-platform:not(.is-active) .source-platform-mark { color: #ead5b8 !important; background: rgba(240,210,162,.13) !important; }
      body.is-embedded-agent.page-psychologue .source-platform.is-active .source-platform-mark { color: #2a1d10 !important; background: rgba(255,249,238,.7) !important; }
      body.is-embedded-agent.page-psychologue .source-link-row {
        border-color: rgba(240,210,162,.25) !important;
        background: #20201b !important;
      }
      body.is-embedded-agent.page-psychologue .source-link-row:focus-within { border-color: #dbb576 !important; box-shadow: 0 0 0 3px rgba(219,181,118,.12) !important; }
      body.is-embedded-agent.page-psychologue .source-link-row > svg { color: #e8cfaa !important; }
      body.is-embedded-agent.page-psychologue .source-link-row .input { color: #f2eadf !important; background: transparent !important; }
      body.is-embedded-agent.page-psychologue .url-check-btn.source-submit { background: #e3bf86 !important; color: #251b10 !important; }
      body.is-embedded-agent.page-psychologue .url-check-btn.source-submit:hover { background: #f0d3a2 !important; }
      body.is-embedded-agent.page-psychologue .source-example { color: #9f9688 !important; }
      body.is-embedded-agent.page-psychologue .analyse-btn {
        border-color: #e2bd83 !important;
        background: linear-gradient(135deg, #f1d3a0, #d2a566) !important;
        color: #261b10 !important;
      }
      body.is-embedded-agent.page-psychologue .analyse-btn:hover { background: #f5dcb0 !important; border-color: #f5dcb0 !important; color: #261b10 !important; }
    ` : ''}
  ` : `
    /* Dix pixels gagnés en bas donnent de la place au fil sans alourdir la
       boîte de saisie. Le sélecteur reste volontairement limité au Stratège. */
    body.page-stratege:not(.strategy-studio-preview) .chat-input-row {
      margin-bottom: 8px;
    }
    body.page-stratege:not(.strategy-studio-preview) .strat-layout.has-strategy .chat-input-row {
      bottom: max(8px, env(safe-area-inset-bottom));
    }
    /* Entretien d'Ariane : la page historique distribuait le titre, le micro
       et l'action sur toute la hauteur. Dans la colonne V2 ils forment un
       seul moment de réponse, lisible et compact. */
    body.is-embedded-agent.page-stratege .app-content {
      padding-top: 20px !important;
      padding-bottom: 10px !important;
    }
    body.is-embedded-agent.page-stratege .interview-session-bar {
      padding-bottom: 8px !important;
      margin-bottom: 8px !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro {
      justify-content: center !important;
      gap: 0 !important;
      padding: clamp(28px, 5vh, 62px) 24px 32px !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro .gate-eyebrow {
      align-self: center !important;
      margin: 0 0 25px !important;
      font-size: clamp(19px, 2vw, 25px) !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro .gate-mic {
      width: 64px !important;
      height: 64px !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro .gate-mic svg {
      width: 45px !important;
      height: 45px !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro .gate-question {
      margin: 20px 0 0 !important;
      max-width: 590px !important;
      line-height: 1.65 !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro .gate-actions { margin-top: 18px !important; }
    /* Audio Ariane : l'invitation et le moment d'écoute deviennent une seule
       surface calme, avec les vrais contrôles existants de l'entretien. */
    body.is-embedded-agent.page-stratege #gate-intro {
      width: min(430px, calc(100% - 48px)) !important;
      height: 416px !important;
      min-height: 0 !important;
      max-height: calc(100% - 30px) !important;
      box-sizing: border-box !important;
      align-self: center !important;
      justify-self: center !important;
      border: 1px solid rgba(83,76,67,.08) !important;
      border-radius: 24px !important;
      background: linear-gradient(145deg, rgba(255,255,255,.94), rgba(247,246,243,.82)) !important;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.98), 0 18px 42px rgba(41,37,31,.055) !important;
      backdrop-filter: blur(24px) saturate(125%) !important;
      -webkit-backdrop-filter: blur(24px) saturate(125%) !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro .gate-eyebrow {
      color: #72695d !important;
      font-size: 11px !important;
      font-weight: 650 !important;
      letter-spacing: .12em !important;
      text-transform: uppercase !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro .gate-mic {
      position: relative !important;
      width: 72px !important;
      height: 72px !important;
      border: 1px solid rgba(48,44,38,.12) !important;
      border-radius: 50% !important;
      background: linear-gradient(145deg, #2b2823, #171613) !important;
      color: #f5d9a8 !important;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 10px 22px rgba(32,28,22,.14) !important;
    }
    body.is-embedded-agent.page-stratege #gate-intro .gate-mic::before { display: none !important; }
    body.is-embedded-agent.page-stratege #gate-intro .gate-mic svg { width: 29px !important; height: 29px !important; stroke: currentColor !important; }
    body.is-embedded-agent.page-stratege #gate-intro .gate-question { min-height: 46px !important; color: #5f594f !important; font-size: 13px !important; text-align: center !important; }
    body.is-embedded-agent.page-stratege #gate-intro .gate-question:empty::before { content: 'Expliquez votre besoin avec vos propres mots. Ariane structure ensuite les priorités.'; }
    body.is-embedded-agent.page-stratege #gate-intro .gate-write { color: #71685d !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay {
      inset: 20px !important;
      border: 1px solid rgba(196,157,99,.2) !important;
      border-radius: 28px !important;
      background: linear-gradient(145deg, rgba(255,255,255,.9), rgba(239,237,231,.82)) !important;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.95), 0 24px 56px rgba(41,37,31,.12) !important;
      backdrop-filter: blur(26px) saturate(125%) !important;
      -webkit-backdrop-filter: blur(26px) saturate(125%) !important;
    }
    body.is-embedded-agent.page-stratege .listening-kicker { display: block !important; color: #9a7648 !important; }
    body.is-embedded-agent.page-stratege .listening-title { display: block !important; margin: 0 0 10px !important; color: #24211d !important; font-size: 29px !important; font-weight: 430 !important; letter-spacing: -.045em !important; }
    body.is-embedded-agent.page-stratege .listening-copy { display: block !important; max-width: 320px !important; margin: 0 0 22px !important; color: #756d63 !important; font-size: 12px !important; line-height: 1.55 !important; }
    body.is-embedded-agent.page-stratege .listening-transcript { min-height: 70px !important; margin-bottom: 20px !important; color: #4c463e !important; }
    body.is-embedded-agent.page-stratege .listening-mic-btn {
      width: 68px !important; height: 68px !important; margin-bottom: 20px !important;
      border-color: rgba(196,157,99,.34) !important;
      background: linear-gradient(145deg, #f4dfbb, #dfb679) !important;
    }
    body.is-embedded-agent.page-stratege .listening-mic-btn svg { stroke: #2a1e11 !important; }
    body.is-embedded-agent.page-stratege .listening-wave span { background: #b28752 !important; }
    body.is-embedded-agent.page-stratege .listening-action.primary { background: #2b2823 !important; border-color: #2b2823 !important; color: #fffaf1 !important; }
    /* Architecture de l'écoute : pendant l'enregistrement il n'y a qu'un
       centre de gravité. Les réglages de voix et la barre de session ne
       viennent pas concurrencer l'écoute ou se superposer à la carte. */
    body.is-embedded-agent.page-stratege .ctx-panel[data-interview-state="listening"] .interview-session-bar,
    body.is-embedded-agent.page-stratege .ctx-panel[data-interview-state="listening"] .chat-input-row,
    body.is-embedded-agent.page-stratege .chat-window.is-recording .voice-toolbar { display: none !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay {
      top: 50% !important;
      right: auto !important;
      bottom: auto !important;
      left: 50% !important;
      width: min(560px, calc(100% - 56px)) !important;
      height: min(500px, calc(100% - 40px)) !important;
      min-height: 0 !important;
      padding: 30px 34px 26px !important;
      transform: translate(-50%, -50%) !important;
      box-sizing: border-box !important;
      justify-content: center !important;
    }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-transcript {
      min-height: 58px !important;
      margin-bottom: 16px !important;
    }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-mic-btn { margin-bottom: 16px !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-wave { margin-bottom: 10px !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-meta { margin-bottom: 18px !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-actions { width: 100% !important; gap: 8px !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-action { flex: 1 1 0 !important; padding: 9px 10px !important; }
    /* Signal audio V2 : une lumière circule sur le contour plutôt qu'un
       effet massif. La surface reste lisible, le mouvement n'apparaît que
       pendant l'écoute et respecte la préférence de mouvement réduite. */
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay {
      isolation: isolate !important;
      overflow: hidden !important;
      border-color: rgba(116,99,248,.35) !important;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.95), 0 22px 58px rgba(66,58,116,.13), 0 0 0 1px rgba(181,146,255,.06) !important;
    }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay::before {
      position: absolute !important;
      z-index: 0 !important;
      inset: -42% !important;
      border-radius: inherit !important;
      background: conic-gradient(from 20deg, transparent 0deg, transparent 68deg, rgba(102,87,255,.92) 108deg, rgba(210,168,255,.72) 142deg, rgba(116,99,248,.82) 178deg, transparent 228deg, transparent 360deg) !important;
      animation: gv2-audio-neon-orbit 4.2s linear infinite !important;
      content: '' !important; pointer-events: none !important;
    }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay::after {
      position: absolute !important;
      z-index: 1 !important;
      inset: 1px !important;
      border-radius: 27px !important;
      background: radial-gradient(circle at 50% 14%, rgba(154,137,255,.18), transparent 39%), linear-gradient(145deg, rgba(255,255,255,.93), rgba(238,238,244,.86)) !important;
      content: '' !important; pointer-events: none !important;
    }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay > * { position: relative !important; z-index: 2 !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-mic-btn {
      border-color: rgba(119,100,255,.68) !important;
      background: radial-gradient(circle at 36% 28%, #7062ee, #40357d 72%) !important;
      color: #fff !important;
      box-shadow: 0 0 0 7px rgba(117,99,248,.07), 0 0 28px rgba(115,96,246,.34), inset 0 1px 0 rgba(255,255,255,.32) !important;
      animation: gv2-audio-mic-breathe 1.9s ease-in-out infinite !important;
    }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-mic-btn::before { display: none !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-mic-btn svg { stroke: #fff !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-wave span { background: linear-gradient(#7465fa, #c49aff) !important; box-shadow: 0 0 8px rgba(118,101,248,.24); }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-kicker { color: #6d5ce7 !important; }
    body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-silence { color: #735fd1 !important; }
    /* Restitution stratégique V2 — le contenu reste identique, mais chaque
       onglet devient une grille lisible. Le regard suit : décision, preuve,
       puis action, au lieu de traverser une succession de longs documents. */
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active {
      gap: 16px !important;
      padding: 18px 20px 72px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-action-bar::before {
      font-size: clamp(24px, 2.5vw, 36px) !important;
      font-weight: 520 !important;
      letter-spacing: -.055em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-tabs {
      justify-content: flex-start !important;
      gap: clamp(16px, 2.6vw, 36px) !important;
      margin-bottom: 20px !important;
      padding: 0 4px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-tab {
      padding-bottom: 11px !important;
      font-size: 10px !important;
      letter-spacing: .09em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-panel {
      display: grid !important;
      grid-column: 1 / -1 !important;
      grid-template-columns: repeat(12, minmax(0, 1fr)) !important;
      gap: 14px !important;
      align-items: start !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-panel.hidden { display: none !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero,
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .kpi-row,
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active :is(.strat-card--psychology, .strat-card--offer, .strat-card--opportunities, .strat-card--recommendations, .strat-card--plan, .strat-card--critique) {
      grid-column: 1 / -1 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active :is(.decision-card, .obj-card) { grid-column: span 6 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active :is(.strat-card--pricing, .strat-card--monetization, .strat-card--social, .strat-card--positioning, .strat-card--content, .strat-card--risks, .strat-card--indicators, .strat-card--clarify) { grid-column: span 6 !important; }
    /* Une analyse qui porte une idée complète ne doit pas s'arrêter au milieu
       du canevas : elle devient un volet éditorial, sans vide parasitaire. */
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--value { grid-column: 1 / -1 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero {
      grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr) !important;
      min-height: 0 !important;
      border-radius: 17px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero-body {
      min-height: 330px !important;
      padding: clamp(25px, 3.2vw, 42px) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero-visual { min-height: 330px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero-decision {
      max-width: 760px !important;
      font-size: clamp(27px, 3vw, 43px) !important;
      font-weight: 470 !important;
      letter-spacing: -.057em !important;
      line-height: 1.04 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero-week {
      max-width: 700px !important;
      margin-top: 22px !important;
      padding: 12px 14px !important;
      border-radius: 10px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .kpi-row { gap: 14px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .kpi-card {
      min-height: 132px !important;
      padding: 17px 18px !important;
      border-radius: 13px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .kpi-value { font-size: clamp(25px, 2.25vw, 34px) !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .decision-card,
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .obj-card {
      min-height: 0 !important;
      padding: 21px 23px !important;
      border-radius: 13px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .decision-text {
      font-size: clamp(20px, 1.85vw, 27px) !important;
      line-height: 1.22 !important;
      letter-spacing: -.04em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card {
      min-height: 0 !important;
      padding: 19px 20px !important;
      border-radius: 14px !important;
      box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text-primary) 3%, transparent) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-sec-head { margin-bottom: 13px !important; padding-bottom: 12px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-sec-title { font-size: 14px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .psycho-used-grid { grid-template-columns: repeat(4, minmax(0, 1fr)) !important; gap: 8px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .psycho-used-item {
      min-height: 0 !important;
      padding: 12px !important;
      border-radius: 9px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .psycho-used-val { font-size: 11px !important; line-height: 1.52 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--value .value-core { margin-bottom: 15px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--value .value-rows {
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      gap: 10px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--value .value-row {
      min-height: 0 !important;
      padding: 15px 16px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--value .value-gap {
      margin-top: 10px !important;
      padding: 12px 15px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--offer .dash-sec-head { margin: 20px 22px 0 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .offer-card {
      min-height: 0 !important;
      padding: 24px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .offer-poster { min-height: 0 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .offer-poster .offer-name {
      max-width: 690px !important;
      font-size: clamp(31px, 3.7vw, 51px) !important;
      line-height: .98 !important;
      letter-spacing: -.072em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .offer-poster-message { min-height: 64px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .mono-visual { min-height: 210px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .opp-list {
      display: grid !important;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)) !important;
      gap: 10px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .opp-card { height: 100% !important; margin: 0 !important; padding: 14px !important; border-radius: 10px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .reco-list { display: grid !important; grid-template-columns: repeat(3, minmax(0, 1fr)) !important; gap: 9px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .reco-item { min-height: 124px !important; height: 100% !important; padding: 13px !important; border-radius: 10px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .crit-head { margin-bottom: 12px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--critique { display: grid !important; grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 10px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--critique .crit-head,
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--critique .crit-conf { grid-column: 1 / -1 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .crit-row { margin: 0 !important; min-height: 132px !important; padding: 14px !important; border-radius: 10px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .plan-tabs { margin-bottom: 14px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .plan-phase { max-width: 860px !important; }
    /* Les actions après analyse sont secondaires : une seule ligne claire,
       sans la hauteur d'une nouvelle section de rapport. */
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-card {
      display: grid !important;
      grid-template-columns: minmax(220px, auto) auto minmax(220px, 1fr) auto !important;
      align-items: center !important;
      gap: 10px 14px !important;
      min-height: 0 !important;
      padding: 15px 18px !important;
      background: color-mix(in srgb, var(--bg-card) 94%, transparent) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-title { margin: 0 !important; font-size: 12px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-options { margin: 0 !important; gap: 6px !important; flex-wrap: nowrap !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-btn { padding: 7px 12px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-comment { min-height: 38px !important; height: 38px !important; padding: 8px 11px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-card > div:last-child { justify-self: end !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .createur-bridge-inner {
      display: grid !important;
      grid-template-columns: minmax(0, 1fr) auto !important;
      align-items: center !important;
      gap: 14px 24px !important;
      padding: 18px 20px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .createur-bridge-header { min-width: 0 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .createur-bridge-sub { max-width: 780px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .createur-features { display: none !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .createur-send-btn { grid-column: 2 !important; grid-row: 1 !important; min-width: max-content !important; padding: 11px 14px !important; }
    @media (max-width: 920px) {
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-panel { grid-template-columns: repeat(6, minmax(0, 1fr)) !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .decision-card,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .obj-card,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active :is(.strat-card--pricing, .strat-card--monetization, .strat-card--social, .strat-card--positioning, .strat-card--content, .strat-card--risks, .strat-card--indicators, .strat-card--clarify) { grid-column: span 3 !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero { grid-template-columns: 1fr !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero-visual { min-height: 220px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .psycho-used-grid,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .reco-list { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-card { grid-template-columns: 1fr auto !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-comment { grid-column: 1 / -1 !important; grid-row: 2 !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-card > div:last-child { grid-column: 2 !important; grid-row: 3 !important; }
    }
    @media (max-width: 620px) {
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-panel { grid-template-columns: 1fr !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .dash-panel > *,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .decision-card,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .obj-card,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active :is(.strat-card--pricing, .strat-card--monetization, .strat-card--social, .strat-card--positioning, .strat-card--content, .strat-card--risks, .strat-card--indicators, .strat-card--clarify) { grid-column: 1 !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .kpi-row,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .psycho-used-grid,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--value .value-rows,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .reco-list,
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-card--critique { grid-template-columns: 1fr !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-card { display: flex !important; align-items: stretch !important; flex-direction: column !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-options { flex-wrap: wrap !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .fb-card > div:last-child { justify-self: auto !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .createur-bridge-inner { grid-template-columns: 1fr !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .createur-send-btn { grid-column: 1 !important; grid-row: auto !important; width: 100% !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero-body { min-height: 0 !important; padding: 24px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .strat-hero-decision { font-size: 31px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.strat-cockpit-active .offer-poster { grid-template-columns: 1fr !important; gap: 15px !important; }
    }
    /* Rapport stratégique continu — adaptation de la direction éditoriale
       fournie pour Gabriel. Les données, boutons et événements restent ceux
       de la page historique ; seule leur mise en scène V2 est remplacée. */
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report {
      --report-bg: ${darkMode ? '#181a19' : '#f4f5f3'};
      --report-rail: ${darkMode ? '#1d201e' : '#f7f8f6'};
      --report-surface: ${darkMode ? '#202321' : '#fbfcfa'};
      --report-text: ${darkMode ? '#f0f2ef' : '#171b1a'};
      --report-muted: ${darkMode ? '#9da59f' : '#7d8681'};
      --report-faint: ${darkMode ? '#747c77' : '#9ba39f'};
      --report-rule: ${darkMode ? 'rgba(255,255,255,.12)' : '#dce1dd'};
      --report-accent: ${darkMode ? '#789486' : '#728d7e'};
      --report-accent-soft: ${darkMode ? '#27302b' : '#e8eeea'};
      display: grid !important;
      grid-template-columns: 220px minmax(0, 1fr) !important;
      gap: 0 !important;
      width: 100% !important;
      max-width: none !important;
      padding: 0 0 120px !important;
      color: var(--report-text) !important;
      background: linear-gradient(90deg, var(--report-rail) 0 220px, var(--report-bg) 220px) !important;
      overflow: visible !important;
      isolation: isolate !important;
    }
    html:has(body.gv2-strategy-report-active) {
      height: 100% !important;
      overflow: hidden !important;
    }
    body.is-embedded-agent.page-stratege.gv2-strategy-report-active {
      height: 100vh !important;
      min-height: 0 !important;
      overflow: hidden !important;
    }
    body.is-embedded-agent.page-stratege.gv2-strategy-report-active :is(.app-layout, .app-main) {
      height: 100% !important;
      min-height: 0 !important;
      overflow: hidden !important;
    }
    body.is-embedded-agent.page-stratege.gv2-strategy-report-active .app-content {
      flex: 1 1 auto !important;
      height: 100% !important;
      min-height: 0 !important;
      max-width: none !important;
      padding: 0 !important;
      background: var(--report-bg, ${darkMode ? '#181a19' : '#f4f5f3'}) !important;
      overflow-x: hidden !important;
      overflow-y: auto !important;
      overscroll-behavior-y: contain !important;
      scrollbar-gutter: stable !important;
      -webkit-overflow-scrolling: touch !important;
    }
    body.is-embedded-agent.page-stratege.gv2-strategy-report-active .app-content {
      scrollbar-width: thin !important;
      scrollbar-color: color-mix(in srgb, var(--report-muted) 48%, transparent) transparent !important;
    }
    body.is-embedded-agent.page-stratege.gv2-strategy-report-active .app-content::-webkit-scrollbar { width: 9px !important; }
    body.is-embedded-agent.page-stratege.gv2-strategy-report-active .app-content::-webkit-scrollbar-track { background: transparent !important; }
    body.is-embedded-agent.page-stratege.gv2-strategy-report-active .app-content::-webkit-scrollbar-thumb {
      border: 3px solid transparent !important;
      border-radius: 999px !important;
      background: color-mix(in srgb, var(--report-muted) 48%, transparent) !important;
      background-clip: padding-box !important;
    }
    body.is-embedded-agent.page-stratege .strat-layout.has-strategy:has(#strat-dashboard.gv2-strategy-report) > .ctx-panel {
      display: none !important;
    }
    body.is-embedded-agent.page-stratege .strat-layout.has-strategy:has(#strat-dashboard.gv2-strategy-report),
    body.is-embedded-agent.page-stratege .strat-layout.has-strategy:has(#strat-dashboard.gv2-strategy-report) #strat-right {
      width: 100% !important;
      max-width: none !important;
      margin: 0 !important;
      padding: 0 !important;
      background: var(--report-bg, ${darkMode ? '#181a19' : '#f4f5f3'}) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report > * {
      grid-column: 2 !important;
      min-width: 0 !important;
      color: var(--report-text) !important;
      box-sizing: border-box !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tabs {
      /* Le sommaire reste visible, mais ne participe pas au calcul des lignes
         de la grille. Avec position: sticky + height: 100vh, la première
         ligne prenait toute la hauteur de l'écran et créait un grand vide
         entre l'en-tête et la première section du rapport. */
      position: fixed !important;
      z-index: 14 !important;
      top: 0 !important;
      left: 0 !important;
      grid-column: 1 !important;
      align-self: start !important;
      display: flex !important;
      flex-direction: column !important;
      align-items: stretch !important;
      justify-content: flex-start !important;
      gap: 2px !important;
      width: 220px !important;
      height: 100vh !important;
      margin: 0 !important;
      padding: 38px 20px 22px !important;
      border: 0 !important;
      border-right: 1px solid var(--report-rule) !important;
      background: color-mix(in srgb, var(--report-rail) 94%, transparent) !important;
      backdrop-filter: blur(16px) !important;
      -webkit-backdrop-filter: blur(16px) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-report-nav-head {
      display: flex !important;
      flex-direction: column !important;
      gap: 5px !important;
      margin-bottom: 30px !important;
      padding-bottom: 25px !important;
      border-bottom: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-report-nav-head > span {
      margin-bottom: 18px !important;
      color: var(--report-faint) !important;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
      font-size: 9px !important;
      font-weight: 600 !important;
      letter-spacing: .17em !important;
      text-transform: uppercase !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-report-nav-head > strong {
      max-width: 150px !important;
      color: var(--report-text) !important;
      font-size: 15px !important;
      font-weight: 650 !important;
      line-height: 1.24 !important;
      letter-spacing: -.025em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-report-nav-head > small {
      color: var(--report-muted) !important;
      font-size: 11px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tab {
      position: relative !important;
      display: flex !important;
      align-items: center !important;
      width: 100% !important;
      min-height: 43px !important;
      padding: 0 10px 0 40px !important;
      border: 0 !important;
      border-radius: 8px !important;
      color: var(--report-muted) !important;
      background: transparent !important;
      font-family: inherit !important;
      font-size: 12px !important;
      font-weight: 450 !important;
      line-height: 1 !important;
      letter-spacing: -.01em !important;
      text-align: left !important;
      text-transform: none !important;
      transition: color .2s ease, background .2s ease !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tab::before {
      position: absolute !important;
      left: 12px !important;
      color: var(--report-faint) !important;
      content: attr(data-report-number) !important;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
      font-size: 9px !important;
      letter-spacing: .08em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tab::after { display: none !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tab:hover,
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tab.active {
      color: var(--report-text) !important;
      background: var(--report-accent-soft) !important;
      font-weight: 620 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-report-nav-foot {
      display: flex !important;
      align-items: center !important;
      gap: 10px !important;
      margin-top: auto !important;
      padding-top: 18px !important;
      border-top: 1px solid var(--report-rule) !important;
      color: var(--report-muted) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-report-nav-foot > span {
      display: grid !important;
      width: 29px !important;
      height: 29px !important;
      place-items: center !important;
      border: 1px solid var(--report-rule) !important;
      border-radius: 50% !important;
      color: var(--report-accent) !important;
      font-size: 13px !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-report-nav-foot p {
      display: flex !important;
      flex-direction: column !important;
      gap: 3px !important;
      margin: 0 !important;
      font-size: 10px !important;
      line-height: 1.2 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-report-nav-foot small { color: var(--report-faint) !important; font-size: 8px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-action-bar {
      grid-column: 2 !important;
      grid-row: 1 !important;
      display: grid !important;
      grid-template-columns: minmax(0, 1fr) auto auto !important;
      align-items: end !important;
      gap: 18px !important;
      min-height: 132px !important;
      margin: 0 !important;
      padding: 38px clamp(32px, 5vw, 76px) 28px !important;
      border-bottom: 1px solid var(--report-rule) !important;
      background: var(--report-bg) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-action-bar::before {
      align-self: end !important;
      margin: 0 !important;
      color: var(--report-text) !important;
      content: 'Rapport stratégique' !important;
      font-size: clamp(30px, 3.2vw, 46px) !important;
      font-weight: 480 !important;
      line-height: .92 !important;
      letter-spacing: -.072em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.strat-result-label, .regen-btn) {
      align-self: center !important;
      color: var(--report-muted) !important;
      border-color: var(--report-rule) !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-panel,
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-panel.hidden {
      display: grid !important;
      grid-column: 2 !important;
      grid-template-columns: repeat(12, minmax(0, 1fr)) !important;
      gap: 18px !important;
      align-items: start !important;
      margin: 0 !important;
      padding: 0 clamp(32px, 5vw, 76px) 84px !important;
      border-bottom: 1px solid var(--report-rule) !important;
      background: var(--report-bg) !important;
      scroll-margin-top: 10px !important;
      animation: none !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-section-heading {
      grid-column: 1 / -1 !important;
      display: grid !important;
      grid-template-columns: minmax(180px, .32fr) minmax(0, 1fr) !important;
      align-items: end !important;
      gap: 26px !important;
      min-height: 148px !important;
      padding: 36px 0 26px !important;
      border-bottom: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-section-heading p {
      display: flex !important;
      gap: 18px !important;
      align-items: center !important;
      margin: 0 0 7px !important;
      color: var(--report-muted) !important;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
      font-size: 10px !important;
      font-weight: 600 !important;
      letter-spacing: .13em !important;
      text-transform: uppercase !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-section-heading p span { color: var(--report-faint) !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-section-heading h2 {
      max-width: 820px !important;
      margin: 0 !important;
      color: var(--report-text) !important;
      font-size: clamp(30px, 3vw, 46px) !important;
      font-weight: 470 !important;
      line-height: .98 !important;
      letter-spacing: -.07em !important;
      text-wrap: balance !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-panel > :not(.gv2-strategy-section-heading) {
      color: var(--report-text) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.strat-hero, .strat-card, .decision-card, .obj-card, .kpi-card, .fb-card, .createur-bridge) {
      border-color: var(--report-rule) !important;
      border-radius: 0 !important;
      color: var(--report-text) !important;
      box-shadow: none !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.strat-card, .decision-card, .obj-card, .kpi-card) {
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero {
      grid-column: 1 / -1 !important;
      grid-template-columns: minmax(0, 1.45fr) minmax(260px, .55fr) !important;
      min-height: 350px !important;
      margin-top: 18px !important;
      overflow: hidden !important;
      border: 1px solid var(--report-rule) !important;
      background: var(--report-surface) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero-body {
      min-height: 350px !important;
      padding: clamp(28px, 3.6vw, 52px) !important;
      background: var(--report-surface) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero-visual { min-height: 350px !important; border-left: 1px solid var(--report-rule) !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero-portrait { filter: grayscale(1) contrast(.9) !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero-decision {
      max-width: 820px !important;
      color: var(--report-text) !important;
      font-size: clamp(26px, 2.4vw, 38px) !important;
      font-weight: 470 !important;
      line-height: 1.01 !important;
      letter-spacing: -.065em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.strat-hero-kicker, .strat-hero-week-label, .dash-sec-title, .kpi-label, .value-row-label, .crit-label) {
      color: var(--report-muted) !important;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
      letter-spacing: .12em !important;
      text-transform: uppercase !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero-week {
      border: 0 !important;
      border-top: 1px solid var(--report-rule) !important;
      border-radius: 0 !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .kpi-row {
      grid-column: 1 / -1 !important;
      display: grid !important;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)) !important;
      gap: 0 !important;
      margin: 16px 0 0 !important;
      border: 1px solid var(--report-rule) !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .kpi-card {
      min-height: 150px !important;
      padding: 25px !important;
      border: 0 !important;
      border-right: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .kpi-card:last-child { border-right: 0 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .kpi-value { color: var(--report-text) !important; font-size: clamp(28px, 3vw, 44px) !important; font-weight: 480 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .kpi-value.kpi-value--text {
      font-size: clamp(17px, 1.35vw, 22px) !important;
      line-height: 1.24 !important;
      letter-spacing: -.035em !important;
      overflow-wrap: anywhere !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.decision-card, .obj-card) {
      grid-column: span 6 !important;
      min-height: 220px !important;
      padding: 30px !important;
      border: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .decision-text { color: var(--report-text) !important; font-size: clamp(23px, 2.4vw, 34px) !important; font-weight: 470 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-card {
      min-height: 0 !important;
      padding: 30px 0 !important;
      border: 0 !important;
      border-top: 1px solid var(--report-rule) !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-sec-head {
      margin: 0 0 24px !important;
      padding: 0 0 18px !important;
      border-bottom: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-sec-ico {
      color: var(--report-accent) !important;
      border-color: var(--report-rule) !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-sec-title { color: var(--report-muted) !important; font-size: 10px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .psycho-used-grid,
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-card--value .value-rows {
      gap: 0 !important;
      border: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.psycho-used-item, .value-row) {
      min-height: 145px !important;
      padding: 22px !important;
      border: 0 !important;
      border-right: 1px solid var(--report-rule) !important;
      border-radius: 0 !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.psycho-used-item, .value-row):last-child { border-right: 0 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .opp-list {
      grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
      gap: 0 !important;
      border: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .opp-card {
      min-height: 260px !important;
      padding: 28px !important;
      border: 0 !important;
      border-right: 1px solid var(--report-rule) !important;
      border-radius: 0 !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .opp-card:first-child { background: var(--report-accent-soft) !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .opp-card:last-child { border-right: 0 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .reco-list {
      display: flex !important;
      flex-direction: column !important;
      gap: 0 !important;
      border-top: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .reco-item {
      min-height: 155px !important;
      margin: 0 !important;
      padding: 26px 22px !important;
      border: 0 !important;
      border-bottom: 1px solid var(--report-rule) !important;
      border-radius: 0 !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-card--critique {
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      gap: 0 !important;
      border: 1px solid var(--report-rule) !important;
      padding: 0 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-card--critique :is(.crit-head, .crit-conf) { padding: 24px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .crit-row {
      min-height: 220px !important;
      margin: 0 !important;
      padding: 28px !important;
      border: 0 !important;
      border-top: 1px solid var(--report-rule) !important;
      border-right: 1px solid var(--report-rule) !important;
      border-radius: 0 !important;
      background: transparent !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .crit-row:nth-child(odd) { border-right: 0 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .plan-phase {
      max-width: none !important;
      padding: 28px 0 !important;
      border-bottom: 1px solid var(--report-rule) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.fb-card, .createur-bridge) {
      grid-column: 2 !important;
      width: auto !important;
      margin: 24px clamp(32px, 5vw, 76px) 0 !important;
      border: 1px solid var(--report-rule) !important;
      background: var(--report-surface) !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(p, li, .obj-text, .kpi-sub, .value-row-text, .psycho-used-val, .opp-signal-text, .opp-decision-text, .opp-sub-text, .reco-signal, .crit-row-text) { color: var(--report-muted) !important; }
    /* Les panneaux historiques utilisaient douze colonnes et plusieurs blocs
       sans placement explicite. Dans un rapport continu, chacun de ces blocs
       doit occuper la ligne de lecture entière : cela évite les jauges de
       quelques pixels et les cartes tassées visibles dans le rendu réel. */
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-panel > :not(.gv2-strategy-section-heading) {
      grid-column: 1 / -1 !important;
      width: 100% !important;
      min-width: 0 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .conf-gauge-pair {
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      width: 100% !important;
      margin: 18px 0 0 !important;
    }
    /* Front End Stratège Builder — la taille suit la densité réelle du
       livrable, pas le type de carte supposé par le template historique. */
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report [data-sfb-density] {
      min-width: 0 !important;
      max-width: 100% !important;
      text-wrap: pretty !important;
      overflow-wrap: break-word !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report .sfb-empty-deliverable {
      display: none !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report :is(.strat-hero-decision, .decision-text)[data-sfb-density="long"] {
      font-size: clamp(25px, 2.15vw, 34px) !important;
      line-height: 1.08 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report :is(.strat-hero-decision, .decision-text)[data-sfb-density="extended"] {
      font-size: clamp(21px, 1.75vw, 28px) !important;
      line-height: 1.14 !important;
      letter-spacing: -.045em !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report .kpi-value--text[data-sfb-density="medium"] { font-size: 19px !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report .kpi-value--text[data-sfb-density="long"] { font-size: 17px !important; line-height: 1.3 !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report .kpi-value--text[data-sfb-density="extended"] { font-size: 15px !important; line-height: 1.36 !important; letter-spacing: -.02em !important; }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report :is(.opp-decision-text, .opp-signal-text, .opp-sub-text, .crit-row-text, .reco-signal)[data-sfb-density="long"] {
      font-size: 14px !important;
      line-height: 1.5 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report :is(.opp-decision-text, .opp-signal-text, .opp-sub-text, .crit-row-text, .reco-signal)[data-sfb-density="extended"] {
      font-size: 13px !important;
      line-height: 1.55 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report :is(.obj-text, .plan-item, .plan-decision, .risk-text, .risk-mitigation)[data-sfb-density="long"] {
      font-size: 13px !important;
      line-height: 1.55 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report :is(.obj-text, .plan-item, .plan-decision, .risk-text, .risk-mitigation)[data-sfb-density="extended"] {
      font-size: 12px !important;
      line-height: 1.6 !important;
    }
    body.is-embedded-agent.page-stratege #strat-dashboard.sfb-report .sfb-has-horizontal-overflow {
      max-width: 100% !important;
      overflow-x: hidden !important;
      overflow-wrap: anywhere !important;
      word-break: break-word !important;
    }
    @media (max-width: 980px) {
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report {
        grid-template-columns: 174px minmax(0, 1fr) !important;
        background: linear-gradient(90deg, var(--report-rail) 0 174px, var(--report-bg) 174px) !important;
      }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tabs { width: 174px !important; padding-inline: 13px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-section-heading { grid-template-columns: 1fr !important; gap: 13px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero { grid-template-columns: 1fr !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero-visual { min-height: 250px !important; border-top: 1px solid var(--report-rule) !important; border-left: 0 !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .kpi-row { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)) !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .opp-list { grid-template-columns: 1fr !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .opp-card { min-height: 0 !important; border-right: 0 !important; border-bottom: 1px solid var(--report-rule) !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .opp-card:last-child { border-bottom: 0 !important; }
    }
    @media (max-width: 700px) {
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report {
        display: block !important;
        padding-bottom: 70px !important;
        background: var(--report-bg) !important;
      }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-action-bar {
        grid-template-columns: minmax(0, 1fr) auto !important;
        min-height: 130px !important;
        padding: 28px 20px 22px !important;
      }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-action-bar::before { font-size: 35px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-result-label { display: none !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tabs {
        position: sticky !important;
        top: 0 !important;
        left: auto !important;
        display: flex !important;
        flex-direction: row !important;
        gap: 5px !important;
        width: 100% !important;
        height: auto !important;
        padding: 9px 12px !important;
        flex-wrap: wrap !important;
        overflow-x: hidden !important;
        border-right: 0 !important;
        border-bottom: 1px solid var(--report-rule) !important;
      }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.gv2-strategy-report-nav-head, .gv2-strategy-report-nav-foot) { display: none !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tab {
        flex: 1 1 calc(33.333% - 5px) !important;
        width: auto !important;
        min-width: 88px !important;
        min-height: 36px !important;
        justify-content: center !important;
        padding: 0 8px !important;
        font-size: 11px !important;
        text-align: center !important;
        white-space: normal !important;
      }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-tab::before { display: none !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-panel,
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-panel.hidden {
        grid-template-columns: 1fr !important;
        gap: 12px !important;
        padding: 0 20px 60px !important;
      }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .dash-panel > *,
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.decision-card, .obj-card) { grid-column: 1 !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-section-heading { min-height: 142px !important; padding: 28px 0 22px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .gv2-strategy-section-heading h2 { font-size: 32px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero-body { min-height: 0 !important; padding: 24px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-hero-decision { font-size: 30px !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .kpi-row,
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .psycho-used-grid,
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-card--value .value-rows,
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .strat-card--critique,
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report .conf-gauge-pair { grid-template-columns: 1fr !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.kpi-card, .psycho-used-item, .value-row, .crit-row) { border-right: 0 !important; border-bottom: 1px solid var(--report-rule) !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.kpi-card, .psycho-used-item, .value-row, .crit-row):last-child { border-bottom: 0 !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.decision-card, .obj-card) { min-height: 0 !important; }
      body.is-embedded-agent.page-stratege #strat-dashboard.gv2-strategy-report :is(.fb-card, .createur-bridge) {
        width: auto !important;
        margin: 20px !important;
      }
    }
    /* Après l'écoute, Ariane reste présente pendant la mise au clair : la
       transcription est visible, puis un halo discret prend le relais. */
    body.is-embedded-agent.page-stratege .gv2-audio-thinking {
      position: absolute !important;
      z-index: 18 !important;
      inset: 20px !important;
      display: none !important;
      place-items: center !important;
      overflow: hidden !important;
      border: 1px solid rgba(112,92,248,.6) !important;
      border-radius: 28px !important;
      background: linear-gradient(136deg, rgba(255,255,255,.58), rgba(235,232,252,.46)) !important;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.94), 0 24px 62px rgba(70,60,120,.16), 0 0 0 1px rgba(178,152,255,.1) !important;
      backdrop-filter: blur(27px) saturate(128%) !important;
      -webkit-backdrop-filter: blur(27px) saturate(128%) !important;
      isolation: isolate !important;
    }
    body.is-embedded-agent.page-stratege .ctx-panel[data-interview-state="transcribing"] .gv2-audio-thinking.is-active { display: grid !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking::before {
      position: absolute !important;
      z-index: 0 !important;
      inset: -48% !important;
      border-radius: inherit !important;
      background: conic-gradient(from 18deg, transparent 0deg, transparent 70deg, rgba(109,89,255,.82) 105deg, rgba(215,164,255,.7) 142deg, rgba(100,214,255,.78) 175deg, transparent 228deg, transparent 360deg) !important;
      animation: gv2-audio-thinking-orbit 5.4s linear infinite !important;
      content: '' !important;
      pointer-events: none !important;
    }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking::after {
      position: absolute !important;
      z-index: 1 !important;
      inset: 1px !important;
      border-radius: 27px !important;
      background: radial-gradient(circle at 21% 105%, rgba(169,143,255,.2), transparent 36%), radial-gradient(circle at 93% 8%, rgba(126,207,255,.17), transparent 34%), linear-gradient(140deg, rgba(255,255,255,.7), rgba(239,239,247,.6)) !important;
      content: '' !important;
      pointer-events: none !important;
    }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-surface { position: relative !important; z-index: 2 !important; display: grid !important; width: min(440px, calc(100% - 48px)) !important; gap: 22px !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-dots { display: inline-flex !important; align-items: center !important; justify-content: center !important; width: 62px !important; height: 31px !important; gap: 7px !important; border-radius: 999px !important; background: #141517 !important; box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 7px 18px rgba(37,35,51,.16) !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-dots i { width: 7px !important; height: 7px !important; border-radius: 50% !important; background: #fff !important; animation: gv2-audio-thinking-dot 1.2s ease-in-out infinite alternate !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-dots i:last-child { animation-delay: .2s !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview { display: grid !important; grid-template-columns: 27px minmax(0,1fr) 15px !important; align-items: center !important; gap: 11px !important; min-height: 70px !important; padding: 12px 16px !important; border: 1px solid rgba(92,91,108,.23) !important; border-radius: 22px !important; background: rgba(255,255,255,.3) !important; box-shadow: inset 0 1px 0 rgba(255,255,255,.52) !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview > span { display: grid !important; width: 27px !important; height: 27px !important; place-items: center !important; border-radius: 50% !important; background: #126bb4 !important; color: #fff !important; font-size: 11px !important; font-weight: 700 !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview p { display: -webkit-box !important; margin: 0 !important; overflow: hidden !important; color: #272830 !important; font-size: 15px !important; line-height: 1.36 !important; text-overflow: ellipsis !important; -webkit-box-orient: vertical !important; -webkit-line-clamp: 2 !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview b { position: relative !important; display: block !important; width: 14px !important; height: 14px !important; border: 1.5px solid #555863 !important; border-radius: 3px !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview b::after { position: absolute !important; top: -4px !important; right: -4px !important; width: 9px !important; height: 9px !important; border: 1.5px solid #555863 !important; border-radius: 2px !important; background: rgba(245,245,250,.62) !important; content: '' !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-status { display: flex !important; align-items: center !important; gap: 11px !important; padding-left: 7px !important; color: #545561 !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-status > i { display: block !important; width: 22px !important; height: 22px !important; border: 2px solid rgba(82,84,94,.24) !important; border-top-color: #6f5be9 !important; border-radius: 50% !important; animation: gv2-audio-thinking-spin .9s linear infinite !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-status em { font-size: 18px !important; font-style: italic !important; letter-spacing: -.025em !important; }
    body.is-embedded-agent.page-stratege .gv2-audio-thinking-copy { margin: -13px 0 0 40px !important; color: #73727e !important; font-size: 11px !important; line-height: 1.5 !important; }
    @keyframes gv2-audio-neon-orbit { to { transform: rotate(360deg); } }
    @keyframes gv2-audio-mic-breathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.045); } }
    @keyframes gv2-audio-thinking-orbit { to { transform: rotate(360deg); } }
    @keyframes gv2-audio-thinking-spin { to { transform: rotate(360deg); } }
    @keyframes gv2-audio-thinking-dot { to { opacity: .4; transform: translateY(-1px); } }
    @media (prefers-reduced-motion: reduce) {
      body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay::before,
      body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-mic-btn,
      body.is-embedded-agent.page-stratege .gv2-audio-thinking::before,
      body.is-embedded-agent.page-stratege .gv2-audio-thinking-status > i,
      body.is-embedded-agent.page-stratege .gv2-audio-thinking-dots i { animation: none !important; }
    }
    ${darkMode ? `
      body.is-embedded-agent.page-stratege #gate-intro,
      body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay {
        border-color: rgba(240,210,162,.2) !important;
        background: linear-gradient(145deg, rgba(53,48,40,.92), rgba(23,23,19,.91)) !important;
        box-shadow: inset 0 1px 0 rgba(255,239,214,.08), 0 24px 56px rgba(0,0,0,.28) !important;
      }
      body.is-embedded-agent.page-stratege :is(#gate-intro .gate-eyebrow, #gate-intro .gate-question, #gate-intro .gate-write, .listening-copy) { color: #d6c7b4 !important; }
      body.is-embedded-agent.page-stratege .listening-title,
      body.is-embedded-agent.page-stratege .listening-transcript { color: #f5ece0 !important; }
      body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-overlay::after { background: radial-gradient(circle at 50% 14%, rgba(147,130,255,.19), transparent 39%), linear-gradient(145deg, rgba(45,42,53,.95), rgba(24,24,28,.94)) !important; }
      body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-kicker { color: #c7bbff !important; }
      body.is-embedded-agent.page-stratege .chat-window.is-recording .listening-silence { color: #d5cdfa !important; }
      body.is-embedded-agent.page-stratege .gv2-audio-thinking { border-color: rgba(161,142,255,.66) !important; background: linear-gradient(140deg, rgba(52,49,69,.74), rgba(25,25,34,.72)) !important; box-shadow: inset 0 1px 0 rgba(255,255,255,.08), 0 24px 62px rgba(0,0,0,.32) !important; }
      body.is-embedded-agent.page-stratege .gv2-audio-thinking::after { background: radial-gradient(circle at 21% 105%, rgba(157,129,255,.23), transparent 36%), radial-gradient(circle at 93% 8%, rgba(116,191,255,.16), transparent 34%), linear-gradient(140deg, rgba(47,45,60,.88), rgba(25,25,32,.9)) !important; }
      body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview { border-color: rgba(218,211,255,.17) !important; background: rgba(255,255,255,.055) !important; box-shadow: inset 0 1px 0 rgba(255,255,255,.08) !important; }
      body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview p { color: #f3f0fa !important; }
      body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview b, body.is-embedded-agent.page-stratege .gv2-audio-thinking-preview b::after { border-color: #c9c3d2 !important; background: rgba(47,45,60,.8) !important; }
      body.is-embedded-agent.page-stratege .gv2-audio-thinking-status { color: #e8e3f1 !important; }
      body.is-embedded-agent.page-stratege .gv2-audio-thinking-copy { color: #bab3c3 !important; }
    ` : ''}
  `;
}

export function AgentWorkspace({ agentId, workspace, onReturnToConversation, onNavigate, contextCollapsed, onShowContext, darkMode = false }) {
  const agent = getAgent(agentId);
  const source = useMemo(() => agent ? agentUrl(agent, workspace?.folder_id) : '', [agent, workspace?.folder_id]);
  const repairedPaths = useRef(new Set());
  const frameRef = useRef(null);

  useEffect(() => {
    try { applyV2EmbeddedPresentation(frameRef.current?.contentDocument, agentId, darkMode); } catch (_) { /* iframe indisponible pendant son chargement */ }
  }, [agentId, darkMode]);

  if (!agent) return null;

  function handleFrameLoad(event) {
    /*
     * Les pages agents sont encore les surfaces qui portent les appels backend
     * historiques. Certaines de leurs actions utilisent window.location : sans
     * cette passerelle, la redirection restait prisonnière de l'iframe et
     * pouvait afficher Gabriel V2 à l'intérieur de Gabriel V2.
     *
     * Toutes les pages sont same-origin. On peut donc lire leur URL sans
     * exposer de données, puis remettre la navigation dans le shell V2.
     */
    try {
      const loadedPath = event.currentTarget.contentWindow?.location?.pathname;
      if (!loadedPath) return;

      if (loadedPath === agent.path) {
        applyV2EmbeddedPresentation(event.currentTarget.contentDocument, agentId, darkMode);
        return;
      }

      if (loadedPath === '/orchestrateur') {
        onReturnToConversation?.();
        return;
      }

      const nextAgentId = agentIdForPath(loadedPath);
      if (nextAgentId) {
        onNavigate?.(nextAgentId);
        return;
      }

      if (loadedPath === '/login') {
        window.location.assign('/login');
        return;
      }

      // Une destination inconnue ne doit jamais remplacer l'outil actif dans
      // son panneau. On retente une seule fois l'URL canonique puis on laisse
      // la page stable plutôt que de créer une boucle de redirections.
      if (!repairedPaths.current.has(loadedPath)) {
        repairedPaths.current.add(loadedPath);
        event.currentTarget.src = source;
      }
    } catch (_) {
      // Si le navigateur bloque la lecture de l'iframe, l'outil reste chargé
      // à son URL explicitement définie ci-dessus : aucune navigation parent
      // n'est forcée.
    }
  }

  return <section className="gv2-agent-workspace" aria-label={`Espace ${agent.name}`}>
    <header className="gv2-agent-workspace-header">
      <img className="gv2-agent-portrait" src={agent.portrait} alt="" />
      <div className="gv2-agent-workspace-copy">
        <h1>{agent.name}</h1>
        <p>{agent.role}</p>
      </div>
      {contextCollapsed && <div className="gv2-agent-workspace-actions">
        {contextCollapsed && <button type="button" className="gv2-agent-context-link" onClick={() => onShowContext?.()}>
          <Icon name="sparkle" size={15} /><span>Contexte</span>
        </button>}
      </div>}
    </header>
    <div className="gv2-agent-frame-wrap">
      <iframe ref={frameRef} key={source} className="gv2-agent-frame" src={source} onLoad={handleFrameLoad} title={`Espace de travail — ${agent.name}`} />
    </div>
  </section>;
}
