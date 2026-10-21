import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { Sidebar } from './Sidebar.jsx';
import { WorkspaceTabs, tabLabels } from './WorkspaceTabs.jsx';
import { Composer, ConversationFeed } from './Conversation.jsx';
import { ContextPanel } from './ContextPanel.jsx';
import { AgentWorkbench } from './AgentWorkbench.jsx';
import { CreatorConversation } from './CreatorConversation.jsx';
import { PsychologueView } from './PsychologueView.jsx';
import { StrategeView } from './StrategeView.jsx';
import { TarifsView } from './TarifsView.jsx';
import { OnboardingTour } from './OnboardingTour.jsx';
import { Icon } from '../icons.jsx';
import { missionFromConversationResponse, workspaceInitial } from '../data-adapters.js';
import { DEFAULT_TAB, getAgent, isAgentTab, tabFromUrl, urlWithTab } from '../agent-registry.js';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

function timeNow() {
  return new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' }).format(new Date());
}

function makeItem(role, content, extras = {}) {
  return { id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`, role, content, createdAt: timeNow(), ...extras };
}

function welcomeMessage(workspace) {
  const target = workspace?.title ? ` dans « ${workspace.title} »` : '';
  return makeItem('assistant', `Bonjour. Je suis Gabriel${target}.\nDécrivez ce que vous souhaitez accomplir : je vais clarifier votre besoin et orchestrer la suite.`);
}

function wait(duration) {
  return new Promise(resolve => window.setTimeout(resolve, duration));
}

const LEFT_DEFAULT = 264;
const LEFT_MIN = 238;
const LEFT_MAX = 300;
const RIGHT_DEFAULT = 320;
const RIGHT_MIN = 240;
const RIGHT_MAX = 460;
const DISCUSSION_DEFAULT = 360;
const DISCUSSION_MIN = 280;
const DISCUSSION_MAX = 560;
const CREATOR_DEFAULTS = {
  contentType: 'script',
  channel: '',
  tone: 'expert',
  emotion: '',
  creativity: 50,
  objective: '',
  generateVariant: false,
};
const ONBOARDING_STORAGE_KEY = 'gabriel-v2:onboarding-completed-2026';

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function savedNumber(key, fallback, min, max) {
  try {
    const value = Number(window.localStorage.getItem(key));
    return Number.isFinite(value) ? clamp(value, min, max) : fallback;
  } catch (_) {
    return fallback;
  }
}

function savedBoolean(key, fallback = false) {
  try {
    const stored = window.localStorage.getItem(key);
    return stored === null ? fallback : stored === 'true';
  } catch (_) {
    return fallback;
  }
}

function onboardingIsPending() {
  try { return !window.localStorage.getItem(ONBOARDING_STORAGE_KEY); } catch (_) { return false; }
}

function creditBalanceFrom(source) {
  const candidate = source?.credits ?? source?.credit_balance ?? source?.remaining_credits ?? source?.balance;
  const value = Number(candidate);
  return Number.isFinite(value) && value >= 0 ? Math.floor(value) : null;
}

function formatCredits(value) {
  return value === null ? '—' : new Intl.NumberFormat('fr-FR').format(value);
}

function conversationStorageKey(workspaceId) {
  return `gabriel-v2:conversation:${workspaceId || 'inbox'}`;
}

function withMissionStatus(mission, status, extras = {}) {
  const agentStatus = { ready: 'selected', running: 'running', completed: 'completed', failed: 'failed' }[status] || 'pending';
  return {
    ...mission,
    ...extras,
    status,
    agents: (mission.agents || []).map(agent => ({ ...agent, status: agentStatus })),
  };
}

function WorkspaceItem({ icon, title, detail, complete = false }) {
  return <article className={`gv2-workspace-item${complete ? ' is-complete' : ''}`}>
    <span><Icon name={icon} size={17} /></span><div><strong>{title}</strong><p>{detail}</p></div>{complete && <Icon name="check" size={16} />}
  </article>;
}

function WorkspaceActivity({ workspace, mission }) {
  const hasWorkspace = Boolean(workspace);
  const hasAnalysis = Boolean(workspace?.analysis_id);
  const hasStrategy = Boolean(workspace?.strategy_id);
  const hasCreator = Boolean(workspace?.creator_output_id);
  return <section className="gv2-workspace-overview" aria-label="Activité du workspace">
    <header><p>Suivi du workspace</p><h1>Activité</h1><span>{hasWorkspace ? 'Les étapes réellement enregistrées dans cette session.' : 'Commencez une conversation pour créer votre première session.'}</span></header>
    {mission && <section className={`gv2-workspace-mission gv2-workspace-mission--${mission.status || 'ready'}`}><Icon name="sparkle" size={17} /><div><strong>{mission.title}</strong><p>{mission.status === 'running' ? `Mission en cours · ${mission.progress || 0}%` : mission.status === 'completed' ? 'Mission terminée' : mission.objective || 'Mission préparée par Gabriel'}</p></div></section>}
    <div className="gv2-workspace-item-list">
      <WorkspaceItem icon="link" title="Source" detail={workspace?.source_summary || (workspace?.source_type ? `Source ${workspace.source_type} reliée au workspace.` : 'Aucune source reliée pour le moment.')} complete={Boolean(workspace?.source_type)} />
      <WorkspaceItem icon="knowledge" title="Analyse d’audience" detail={hasAnalysis ? 'Analyse disponible dans le Psychologue.' : 'Prête à être lancée quand une source est fournie.'} complete={hasAnalysis} />
      <WorkspaceItem icon="sparkle" title="Décision stratégique" detail={hasStrategy ? 'Décision disponible dans le Stratège.' : 'Disponible après l’analyse d’audience.'} complete={hasStrategy} />
      <WorkspaceItem icon="briefcase" title="Créations" detail={hasCreator ? 'Contenu enregistré dans le Créateur.' : 'Disponible quand une direction est validée.'} complete={hasCreator} />
    </div>
  </section>;
}

function WorkspaceMemory({ workspace }) {
  const hasWorkspace = Boolean(workspace);
  const records = [
    workspace?.objective && { icon: 'message', title: 'Objectif déclaré', detail: workspace.objective },
    workspace?.source_summary && { icon: 'link', title: 'Source reliée', detail: workspace.source_summary },
    workspace?.analysis_id && { icon: 'knowledge', title: 'Analyse d’audience', detail: 'Le Psychologue a enregistré une analyse dans cette session.' },
    workspace?.strategy_id && { icon: 'sparkle', title: 'Décision stratégique', detail: 'Le Stratège a enregistré une décision dans cette session.' },
    workspace?.creator_output_id && { icon: 'briefcase', title: 'Création', detail: 'Le Créateur a enregistré un contenu dans cette session.' },
  ].filter(Boolean);
  return <section className="gv2-workspace-overview" aria-label="Mémoire du workspace">
    <header><p>Contexte conservé</p><h1>Mémoire</h1><span>{hasWorkspace ? 'Gabriel ne réutilise ici que les éléments liés à ce workspace.' : 'Aucun élément n’est encore associé à cette nouvelle conversation.'}</span></header>
    <div className="gv2-workspace-item-list">
      {records.length ? records.map(record => <WorkspaceItem key={record.title} {...record} complete />) : <div className="gv2-workspace-empty"><Icon name="archive" size={20} /><p>La mémoire se construit au fil de la conversation, des sources et des productions validées.</p></div>}
    </div>
  </section>;
}

export function AppShell({ bootstrap }) {
  const [workspaces, setWorkspaces] = useState(bootstrap.workspaces || []);
  // L'accueil reste un Hall neutre. Un workspace existant n'est ouvert que si
  // l'utilisateur l'a demandé dans l'URL ou depuis la navigation.
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(bootstrap.selectedWorkspaceId || null);
  /* Les anciennes adresses (/psychologue, /stratege, /createur) renvoient
     désormais vers la V2 en indiquant l'agent visé. Sans cette lecture,
     toutes ces redirections atterriraient sur la Conversation. */
  const [tab, setTab] = useState(() => tabFromUrl(window.location.href));
  const activeWorkspace = useMemo(() => workspaces.find(item => item.folder_id === activeWorkspaceId) || null, [workspaces, activeWorkspaceId]);
  const [items, setItems] = useState(() => [welcomeMessage(null)]);
  const [mission, setMission] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isStartingMission, setIsStartingMission] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [deletingWorkspaceId, setDeletingWorkspaceId] = useState('');
  const [leftWidth, setLeftWidth] = useState(() => savedNumber('gabriel-v2:left-width', LEFT_DEFAULT, LEFT_MIN, LEFT_MAX));
  const [rightWidth, setRightWidth] = useState(() => savedNumber('gabriel-v2:right-width', RIGHT_DEFAULT, RIGHT_MIN, RIGHT_MAX));
  // Le rail compact est la vue de travail par défaut. Le panneau détaillé
  // s'ouvre uniquement quand l'utilisateur en a besoin.
  /* /upgrade et le retour Stripe renvoient vers ?section=settings : la
     navigation doit déjà être ouverte à l'arrivée, sinon le panneau visé
     n'apparaît jamais. */
  const sectionDemandee = useMemo(() => new URL(window.location.href).searchParams.get('section'), []);
  const [leftCollapsed, setLeftCollapsed] = useState(() => sectionDemandee ? false : savedBoolean('gabriel-v2:sidebar-compact-spatial', true));
  const [rightCollapsed, setRightCollapsed] = useState(() => savedBoolean('gabriel-v2:context-collapsed', true));
  const [discussionWidth, setDiscussionWidth] = useState(() => savedNumber('gabriel-v2:discussion-width', DISCUSSION_DEFAULT, DISCUSSION_MIN, DISCUSSION_MAX));
  const [discussionCollapsed, setDiscussionCollapsed] = useState(() => savedBoolean('gabriel-v2:discussion-collapsed'));
  // Le design blanc reste le thème d'entrée de Gabriel.
  // La version sombre est la version native (13/09/2026) : on ne revient au
  // clair que sur choix explicite, mémorisé sous une clé neuve — l'ancienne
  // clé enregistrait « false » par défaut et aurait gardé tout le monde en clair.
  // Analyse demandée depuis le menu : transmise au Psychologue, qui la charge.
  const [analysisToOpen, setAnalysisToOpen] = useState(null);
  // Dernière analyse du Psychologue vue dans cette session : le Créateur s'en sert par défaut.
  const [lastAnalysis, setLastAnalysis] = useState(null);
  // Passage volontaire Ariane → Créateur. Ce contexte reste en mémoire React
  // uniquement : un rechargement ou un changement de dossier ne peut donc pas
  // réactiver une ancienne stratégie par accident.
  const [creatorHandoff, setCreatorHandoff] = useState(null);
  const [darkMode, setDarkMode] = useState(() => {
    try { return window.localStorage.getItem('gabriel-v2:theme') !== 'light'; } catch (_) { return true; }
  });
  const [onboardingOpen, setOnboardingOpen] = useState(onboardingIsPending);
  const [creatorSettings, setCreatorSettings] = useState(CREATOR_DEFAULTS);
  const [creatorHasOutput, setCreatorHasOutput] = useState(false);
  const [creatorRefinementRequest, setCreatorRefinementRequest] = useState(null);
  // État réel de l'entretien d'Ariane (contextProgress/currentDimension/
  // interviewReady/messages), remonté depuis StrategeView pour que le panneau
  // de contexte (Progression/Historique) affiche exactement ce que le
  // serveur a renvoyé — jamais une complétude recalculée ou devinée ici.
  const [strategeInterview, setStrategeInterview] = useState(null);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  // Sur téléphone, le menu latéral s'ouvre en tiroir (il est masqué sinon : rien d'autre ne permet d'y accéder).
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [creditBalance, setCreditBalance] = useState(() => creditBalanceFrom(bootstrap.user));
  const [landingContextOpen, setLandingContextOpen] = useState(false);
  const [backendError, setBackendError] = useState('');
  const mountedRef = useRef(true);
  const shellRef = useRef(null);
  const workspaceTransitionRef = useRef(null);
  const workspaceSwitcherRef = useRef(null);
  const accountMenuRef = useRef(null);

  const refreshCredits = useCallback(async () => {
    try {
      const response = await fetchV2('/credits');
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      if (!response.ok) return;
      const payload = await readApiPayload(response, 'Vos crédits');
      const nextBalance = creditBalanceFrom(payload);
      if (nextBalance !== null && mountedRef.current) setCreditBalance(nextBalance);
    } catch (_) {
      // Le solde affiché reste le dernier montant connu si le rafraîchissement
      // ne peut pas être effectué, sans interrompre le travail en cours.
    }
  }, []);

  const refreshWorkspace = useCallback(async () => {
    if (!activeWorkspaceId) return null;
    try {
      const response = await fetchV2(`/api/v2/workspaces/${encodeURIComponent(activeWorkspaceId)}`);
      if (isLoginResponse(response)) { window.location.assign('/login'); return null; }
      const payload = await readApiPayload(response, 'Le workspace');
      if (!response.ok || !payload?.workspace) return null;
      setWorkspaces(current => current.map(item => item.folder_id === payload.workspace.folder_id ? payload.workspace : item));
      return payload.workspace;
    } catch (_) {
      return null;
    }
  }, [activeWorkspaceId]);

  /* L'objectif du dossier n'est pas décoratif : Gabriel le lit au début de
     chaque conversation (« Objectif déclaré : … »). L'ancienne interface le
     demandait à la création ; la V2 ne le demandait nulle part, si bien que
     tous les dossiers créés ici partaient avec un objectif vide.

     Il est modifiable à tout moment plutôt qu'exigé à la création : la V2
     crée parfois un dossier silencieusement quand on ouvre un agent, et
     imposer un formulaire à ce moment-là casserait ce parcours sans
     friction. L'affichage est mis à jour tout de suite ; en cas d'échec on
     revient à l'état précédent plutôt que de laisser croire à un
     enregistrement qui n'a pas eu lieu. */
  const updateWorkspaceFields = useCallback(async (workspaceId, fields) => {
    if (!workspaceId) return false;
    let precedent = null;
    setWorkspaces(current => current.map(item => {
      if (item.folder_id !== workspaceId) return item;
      precedent = item;
      return { ...item, ...fields };
    }));
    try {
      const response = await fetchV2(`/api/folders/${encodeURIComponent(workspaceId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return false; }
      const payload = await readApiPayload(response, 'La mise à jour du workspace');
      if (!response.ok || !payload?.success) throw new Error(payload?.error || '');
      return true;
    } catch (_) {
      if (precedent) setWorkspaces(current => current.map(item => item.folder_id === workspaceId ? precedent : item));
      setBackendError('Cet objectif n’a pas pu être enregistré. Réessayez.');
      return false;
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem('gabriel-v2:left-width', String(leftWidth));
      window.localStorage.setItem('gabriel-v2:right-width', String(rightWidth));
      window.localStorage.setItem('gabriel-v2:sidebar-compact-spatial', String(leftCollapsed));
      window.localStorage.setItem('gabriel-v2:context-collapsed', String(rightCollapsed));
      window.localStorage.setItem('gabriel-v2:discussion-width', String(discussionWidth));
      window.localStorage.setItem('gabriel-v2:discussion-collapsed', String(discussionCollapsed));
    } catch (_) { /* Les préférences restent locales si le stockage est indisponible. */ }
  }, [leftWidth, rightWidth, leftCollapsed, rightCollapsed, discussionWidth, discussionCollapsed]);

  useEffect(() => {
    try { window.localStorage.setItem('gabriel-v2:theme', darkMode ? 'dark' : 'light'); } catch (_) { /* préférence locale facultative */ }
    document.documentElement.dataset.gabrielV2Theme = darkMode ? 'dark' : 'light';
    document.documentElement.style.colorScheme = darkMode ? 'dark' : 'light';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', darkMode ? '#131313' : '#f5f5f7');
  }, [darkMode]);

  useLayoutEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !shellRef.current) return undefined;
    const context = gsap.context(() => {
      gsap.fromTo('.gv2-sidebar, .gv2-main-column, .gv2-context-panel',
        { autoAlpha: 0, y: 12 },
        { autoAlpha: 1, y: 0, duration: .55, ease: 'power2.out', stagger: .07, clearProps: 'transform' },
      );
      gsap.fromTo('.gv2-workspace-header, .gv2-composer',
        { autoAlpha: 0, y: 8 },
        { autoAlpha: 1, y: 0, duration: .42, delay: .16, ease: 'power2.out', stagger: .08, clearProps: 'transform' },
      );
    }, shellRef);
    return () => context.revert();
  }, []);

  useEffect(() => () => { mountedRef.current = false; }, []);

  useEffect(() => {
    if (!workspaceMenuOpen) return undefined;
    const closeMenu = event => {
      if (event.key === 'Escape' || !workspaceSwitcherRef.current?.contains(event.target)) setWorkspaceMenuOpen(false);
    };
    document.addEventListener('pointerdown', closeMenu);
    document.addEventListener('keydown', closeMenu);
    return () => {
      document.removeEventListener('pointerdown', closeMenu);
      document.removeEventListener('keydown', closeMenu);
    };
  }, [workspaceMenuOpen]);

  useEffect(() => {
    if (!accountMenuOpen) return undefined;
    const closeMenu = event => {
      if (event.key === 'Escape' || (event.type === 'pointerdown' && !accountMenuRef.current?.contains(event.target))) setAccountMenuOpen(false);
    };
    document.addEventListener('pointerdown', closeMenu);
    document.addEventListener('keydown', closeMenu);
    return () => {
      document.removeEventListener('pointerdown', closeMenu);
      document.removeEventListener('keydown', closeMenu);
    };
  }, [accountMenuOpen]);

  useEffect(() => {
    void refreshCredits();
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void refreshCredits();
    };
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => document.removeEventListener('visibilitychange', refreshWhenVisible);
  }, [refreshCredits]);

  // La zone 3 est secondaire dans le Hall, mais elle devient le panneau de
  // réglages indispensable dès qu'un agent est ouvert. On la rouvre donc au
  // changement d'agent ; l'utilisateur peut toujours la refermer ensuite.
  async function selectTab(nextTab, navigationContext = null) {
    const validCreatorHandoff = nextTab === 'createur'
      && navigationContext?.source === 'stratege'
      && navigationContext.folder_id === activeWorkspaceId
      && navigationContext.strategy_id === activeWorkspace?.strategy_id;
    setCreatorHandoff(validCreatorHandoff ? {
      source: 'stratege',
      folder_id: navigationContext.folder_id,
      strategy_id: navigationContext.strategy_id,
    } : null);
    // Sans workspace, un agent intégré créerait un dossier isolé dans son
    // iframe. Ouvrir un agent démarre donc une session V2 explicite, reliée
    // au shell avant le chargement de l'iframe.
    if (isAgentTab(nextTab) && !activeWorkspaceId) {
      try {
        await createWorkspace(nextTab === 'psychologue' ? 'Nouvelle analyse' : 'Nouvel espace de travail', { openTab: nextTab });
      } catch (error) {
        setBackendError(error.message || 'Impossible de préparer cette session.');
      }
      return;
    }
    setTab(nextTab);
    /* L'adresse suit l'onglet : recharger la page rouvre le même écran, et
       le lien reste partageable. */
    window.history.replaceState({}, '', urlWithTab(window.location.href, nextTab));
  }

  function resizePanel(side, delta) {
    if (side === 'left') {
      setLeftWidth(current => clamp(current + delta, LEFT_MIN, LEFT_MAX));
    } else {
      setRightWidth(current => clamp(current + delta, RIGHT_MIN, RIGHT_MAX));
    }
  }

  function beginResize(side, event) {
    if (window.matchMedia('(max-width: 980px)').matches) return;
    event.preventDefault();
    const originX = event.clientX;
    const originWidth = side === 'left' ? leftWidth : rightWidth;
    document.body.classList.add('gv2-is-resizing');

    const move = moveEvent => {
      const rawDelta = moveEvent.clientX - originX;
      const nextWidth = side === 'left'
        ? clamp(originWidth + rawDelta, LEFT_MIN, LEFT_MAX)
        : clamp(originWidth - rawDelta, RIGHT_MIN, RIGHT_MAX);
      if (side === 'left') setLeftWidth(nextWidth); else setRightWidth(nextWidth);
    };
    const end = () => {
      document.body.classList.remove('gv2-is-resizing');
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  }

  function handleResizeKey(side, event) {
    const increase = side === 'left' ? event.key === 'ArrowRight' : event.key === 'ArrowLeft';
    const decrease = side === 'left' ? event.key === 'ArrowLeft' : event.key === 'ArrowRight';
    if (!increase && !decrease) return;
    event.preventDefault();
    resizePanel(side, (increase ? 1 : -1) * (event.shiftKey ? 24 : 12));
  }

  function beginDiscussionResize(event) {
    if (window.matchMedia('(max-width: 980px)').matches || discussionCollapsed) return;
    event.preventDefault();
    const originX = event.clientX;
    const originWidth = discussionWidth;
    document.body.classList.add('gv2-is-resizing');
    const move = moveEvent => setDiscussionWidth(clamp(originWidth + moveEvent.clientX - originX, DISCUSSION_MIN, DISCUSSION_MAX));
    const end = () => {
      document.body.classList.remove('gv2-is-resizing');
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  }

  function handleDiscussionResizeKey(event) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    setDiscussionWidth(current => clamp(current + direction * (event.shiftKey ? 24 : 12), DISCUSSION_MIN, DISCUSSION_MAX));
  }

  useEffect(() => {
    let live = true;
    const location = new URL(window.location.href);
    const requestedWorkspaceId = location.searchParams.get('folder_id');
    const endpoint = requestedWorkspaceId
      ? `/api/v2/bootstrap?folder_id=${encodeURIComponent(requestedWorkspaceId)}`
      : '/api/v2/bootstrap';
    fetchV2(endpoint).then(async response => {
      if (isLoginResponse(response)) { window.location.assign('/login'); return null; }
      const payload = await readApiPayload(response, 'Le chargement de Gabriel');
      if (!response.ok || !payload?.success) throw new Error(payload?.error || 'Le backend Gabriel est indisponible.');
      return payload;
    }).then(payload => {
      const nextWorkspaces = Array.isArray(payload?.workspaces) ? payload.workspaces : [];
      if (!live || !payload?.success) return;
      setBackendError('');
      setWorkspaces(nextWorkspaces);
      setActiveWorkspaceId(current => current || payload.workspace?.folder_id || null);
    }).catch(error => {
      if (live) setBackendError(error.message || 'La connexion au backend Gabriel est indisponible.');
    });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    let live = true;
    // Lors du premier message, le backend crée le workspace et React bascule
    // vers lui. Il ne faut pas réinitialiser les deux messages déjà visibles
    // pendant cette unique transition.
    if (workspaceTransitionRef.current?.workspaceId === activeWorkspaceId) {
      workspaceTransitionRef.current = null;
      return () => { live = false; };
    }
    setItems([welcomeMessage(activeWorkspace)]);
    setMission(null);
    setConversationId(null);
    setCreatorHasOutput(false);
    setCreatorRefinementRequest(null);
    setLandingContextOpen(false);
    let storedConversationId = '';
    try { storedConversationId = window.localStorage.getItem(conversationStorageKey(activeWorkspaceId)) || ''; } catch (_) { /* stockage indisponible */ }
    if (!storedConversationId) return () => { live = false; };

    const query = activeWorkspaceId ? `?folder_id=${encodeURIComponent(activeWorkspaceId)}` : '';
    fetchV2(`/api/v2/conversations/${encodeURIComponent(storedConversationId)}${query}`).then(async response => {
      if (isLoginResponse(response)) { window.location.assign('/login'); return null; }
      const payload = await readApiPayload(response, 'La restauration de la conversation');
      return response.ok ? payload : null;
    }).then(payload => {
      if (!live || !payload?.success) return;
      const restoredItems = (payload.messages || []).filter(item => (
        item && (item.role === 'user' || item.role === 'assistant') && typeof item.content === 'string'
      )).map(item => makeItem(item.role, item.content));
      if (restoredItems.length) setItems(restoredItems);
      setConversationId(payload.conversation_id || storedConversationId);
      const restoredMission = missionFromConversationResponse(payload);
      if (restoredMission) setMission(restoredMission);
    }).catch(() => {});
    return () => { live = false; };
  }, [activeWorkspaceId]);

  // Les agents Psychologue et Stratège restent des applications intégrées :
  // on ne modifie pas leurs pipelines. Pendant qu'un agent est ouvert, le
  // shell rafraîchit simplement le contrat workspace qui alimente la zone 3.
  useEffect(() => {
    if (!activeWorkspaceId || !isAgentTab(tab)) return undefined;
    let live = true;
    const update = async () => {
      if (live) await refreshWorkspace();
    };
    update();
    const interval = window.setInterval(update, 8000);
    return () => {
      live = false;
      window.clearInterval(interval);
    };
  }, [activeWorkspaceId, refreshWorkspace, tab]);

  function selectWorkspace(id, { openConversation = true } = {}) {
    setActiveWorkspaceId(id);
    if (openConversation) setTab('conversation');
    const location = new URL(window.location.href);
    if (id) location.searchParams.set('folder_id', id); else location.searchParams.delete('folder_id');
    window.history.replaceState({}, '', location);
  }

  /* Changer d'espace depuis le menu ne doit pas faire quitter l'écran en cours :
     on reste dans le Psychologue (ou l'agent ouvert) avec le nouvel espace.
     Seuls les écrans hors espace (tarifs) ramènent à la porte d'entrée. */
  function openWorkspace(id) {
    selectWorkspace(id, { openConversation: false });
    if (!isAgentTab(tab) && tab !== 'conversation' && tab !== 'activity' && tab !== 'memory') selectTab(DEFAULT_TAB);
  }

  // Le Hall n'écrit rien à l'avance : le backend créera le workspace seulement
  // lorsque le premier message sera réellement envoyé. Cela évite les dossiers
  // vides tout en donnant à l'utilisateur un vrai départ de conversation.
  function startNewConversation() {
    workspaceTransitionRef.current = null;
    setBackendError('');
    selectWorkspace(null);
  }

  async function createWorkspace(title, { openTab = 'conversation' } = {}) {
    const response = await fetchV2('/api/v2/workspaces', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, folder_type: 'workspace' }) });
    if (isLoginResponse(response)) { window.location.assign('/login'); return; }
    const payload = await readApiPayload(response, 'La création du workspace');
    if (!response.ok || !payload?.success || !payload.workspace) throw new Error(payload?.error || 'Impossible de créer le workspace.');
    setWorkspaces(current => [payload.workspace, ...current]);
    selectWorkspace(payload.workspace.folder_id);
    setTab(openTab);
    return payload.workspace;
  }

  async function deleteWorkspace(workspace) {
    const workspaceId = workspace?.folder_id;
    if (!workspaceId || deletingWorkspaceId) return;
    const title = workspace.title || 'ce workspace';
    if (!window.confirm(`Supprimer « ${title} » de votre liste ?\n\nLes analyses et livrables déjà générés ne seront pas supprimés.`)) return;

    setDeletingWorkspaceId(workspaceId);
    setBackendError('');
    try {
      const response = await fetchV2(`/api/folders/${encodeURIComponent(workspaceId)}`, { method: 'DELETE' });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const payload = await readApiPayload(response, 'La suppression du workspace');
      if (!response.ok || !payload?.success) throw new Error(payload?.error || 'Impossible de supprimer ce workspace.');
      setWorkspaces(current => current.filter(item => item.folder_id !== workspaceId));
      if (activeWorkspaceId === workspaceId) startNewConversation();
    } catch (error) {
      setBackendError(error.message || 'Impossible de supprimer ce workspace.');
    } finally {
      if (mountedRef.current) setDeletingWorkspaceId('');
    }
  }

  async function sendMessage(content, attachments) {
    if (isSubmitting) return;
    const userItem = makeItem('user', content);
    const previousHistory = items.filter(item => item.role === 'user' || item.role === 'assistant').slice(-10).map(item => ({ role: item.role, content: item.content }));
    setIsSubmitting(true);
    try {
      let uploadedSource = null;
      if (attachments.length) {
        if (attachments.length > 1) throw new Error('Ajoutez un seul fichier de commentaires à la fois pour lancer une analyse fiable.');
        const file = attachments[0];
        const form = new FormData();
        form.append('file', file, file.name);
        const uploadResponse = await fetchV2('/upload-comments-file', { method: 'POST', body: form });
        if (isLoginResponse(uploadResponse)) { window.location.assign('/login'); return; }
        const uploadPayload = await readApiPayload(uploadResponse, 'L’import du fichier');
        if (!uploadResponse.ok || !uploadPayload?.success) throw new Error(uploadPayload?.error || 'Le fichier ne contient pas de commentaires exploitables.');
        uploadedSource = {
          filename: file.name,
          comments: Array.isArray(uploadPayload.normalized_comments) ? uploadPayload.normalized_comments : [],
        };
      }
      setItems(current => [...current, userItem]);
      const response = await fetchV2('/api/v2/conversations/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: content, history: previousHistory, folder_id: activeWorkspaceId, conversation_id: conversationId, uploaded_source: uploadedSource }) });
      if (isLoginResponse(response)) { window.location.assign('/login'); return false; }
      const payload = await readApiPayload(response, 'La conversation');
      if (!response.ok || payload.error) throw new Error(payload.error || 'Une erreur est survenue.');
      const nextMission = missionFromConversationResponse(payload);
      const nextConversationId = payload.conversation_id || conversationId;
      const nextWorkspaceId = payload.workspace?.folder_id || activeWorkspaceId;

      if (payload.workspace?.folder_id && payload.workspace.folder_id !== activeWorkspaceId) {
        workspaceTransitionRef.current = { workspaceId: payload.workspace.folder_id };
        setWorkspaces(current => [
          payload.workspace,
          ...current.filter(item => item.folder_id !== payload.workspace.folder_id),
        ]);
        selectWorkspace(payload.workspace.folder_id);
      }

      setConversationId(nextConversationId);
      if (nextConversationId) {
        try { window.localStorage.setItem(conversationStorageKey(nextWorkspaceId), nextConversationId); } catch (_) { /* stockage indisponible */ }
      }
      setItems(current => [...current, makeItem('assistant', payload.reply || 'Je vous réponds dans un instant.'), ...(nextMission ? [makeItem('event', '', { mission: nextMission })] : [])]);
      if (nextMission) setMission(nextMission);
      return true;
    } catch (error) {
      setItems(current => [...current, makeItem('error', error.message || 'Une erreur de connexion est survenue. Réessayez dans un instant.')]);
      return false;
    } finally {
      setIsSubmitting(false);
    }
  }

  async function persistMission(nextMission) {
    if (!conversationId || !nextMission?.id) return nextMission;
    const response = await fetchV2(`/api/v2/conversations/${encodeURIComponent(conversationId)}/missions/${encodeURIComponent(nextMission.id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: conversationId,
        folder_id: activeWorkspaceId,
        status: nextMission.status,
        job_id: nextMission.jobId || undefined,
        progress: nextMission.progress || 0,
        error: nextMission.error || undefined,
      }),
    });
    if (isLoginResponse(response)) {
      window.location.assign('/login');
      throw new Error('Votre session a expiré.');
    }
    const payload = await readApiPayload(response, 'La synchronisation de la mission');
    if (!response.ok) {
      throw new Error(payload?.error || 'Impossible de synchroniser la mission.');
    }
    return missionFromConversationResponse(payload) || nextMission;
  }

  async function finishMission(currentMission, status, extras = {}) {
    const nextMission = withMissionStatus(currentMission, status, extras);
    if (mountedRef.current) setMission(nextMission);
    try {
      const persisted = await persistMission(nextMission);
      if (mountedRef.current) setMission(persisted);
      return persisted;
    } catch (error) {
      // L'agent a bien pu finir même si la synchronisation du panneau échoue.
      // Le résultat est déjà persisté par son pipeline ; on garde l'état local
      // et expose seulement un message clair dans la conversation.
      if (mountedRef.current) setItems(items => [...items, makeItem('error', error.message)]);
      return nextMission;
    }
  }

  async function pollMission(currentMission) {
    const jobId = currentMission.jobId;
    for (let attempt = 0; attempt < 180 && mountedRef.current; attempt += 1) {
      await wait(2000);
      const response = await fetchV2(`/api/v2/jobs/${encodeURIComponent(jobId)}`);
      if (isLoginResponse(response)) {
        window.location.assign('/login');
        return;
      }
      const payload = await readApiPayload(response, 'Le suivi de la mission').catch(error => ({ error: error.message }));
      if (!response.ok || !payload) {
        await finishMission(currentMission, 'failed', { error: payload?.error || 'Le suivi de la mission est indisponible.' });
        return;
      }
      if (payload.status === 'done') {
        await finishMission(currentMission, 'completed', { progress: 100, error: '' });
        await refreshWorkspace();
        if (mountedRef.current) setItems(items => [...items, makeItem('assistant', 'L’analyse est terminée et ses résultats sont enregistrés dans ce workspace. Je peux maintenant en faire la synthèse, construire la décision stratégique ou préparer les contenus qui en découlent.')]);
        return;
      }
      if (payload.status === 'error' || payload.status === 'interrupted' || payload.status === 'not_found') {
        await finishMission(currentMission, 'failed', { error: payload.error || 'La mission n’a pas pu être menée à terme.' });
        return;
      }
      const progress = Number.isFinite(payload.progress) ? payload.progress : currentMission.progress || 0;
      const running = withMissionStatus(currentMission, 'running', { progress, jobId });
      if (mountedRef.current) setMission(running);
      currentMission = running;
      // Une écriture toutes les 10 % suffit à restaurer une mission en cas de
      // rechargement sans ajouter de trafic à chaque cycle de polling.
      if (progress === 0 || progress === 100 || progress % 10 === 0) {
        try { await persistMission(running); } catch (_) { /* état local conservé */ }
      }
    }
    await finishMission(currentMission, 'failed', { error: 'Le suivi a expiré. Le résultat reste disponible dans le workspace si le job a fini.' });
  }

  async function startMission() {
    const currentMission = mission;
    if (!currentMission?.execution || isStartingMission) return;
    setIsStartingMission(true);
    try {
      const response = await fetchV2(currentMission.execution.endpoint, {
        method: currentMission.execution.method || 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...currentMission.execution.payload, folder_id: activeWorkspaceId }),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const payload = await readApiPayload(response, 'Le lancement de la mission');
      if (!response.ok || !payload?.job_id) throw new Error(payload?.error || 'La mission n’a pas pu démarrer.');
      const running = withMissionStatus(currentMission, 'running', { jobId: payload.job_id, progress: 1, error: '' });
      setMission(running);
      await persistMission(running);
      await pollMission(running);
    } catch (error) {
      if (mountedRef.current) setMission(withMissionStatus(currentMission, 'failed', { error: error.message || 'La mission n’a pas pu démarrer.' }));
    } finally {
      if (mountedRef.current) setIsStartingMission(false);
    }
  }

  const firstName = (bootstrap.user?.name || bootstrap.user?.email || 'Nalay').split(/[\s@]/)[0];
  const displayedCredits = formatCredits(creditBalance);
  const activeAgent = getAgent(tab);
  const currentTabLabel = tabLabels[tab] || 'Workspace';
  const isConversationLanding = tab === 'conversation' && !mission && !items.some(item => item.role === 'user');
  // Le contexte n'apparaît que lorsqu'il aide réellement à agir : mission en
  // cours, réglages du Stratège ou paramètres du Créateur. Le Psychologue
  // garde ainsi toute la largeur pour l'analyse.
  const hasContextToSurface = Boolean(mission) || ['stratege', 'createur'].includes(activeAgent?.id);
  // Réduit, le menu conserve son rail d'icônes : l'utilisateur peut toujours
  // le réagrandir depuis sa propre bordure, sans bouton dans l'en-tête.
  const effectiveLeftCollapsed = leftCollapsed;
  const effectiveRightCollapsed = hasContextToSurface ? rightCollapsed : !landingContextOpen;

  function toggleNavigation() {
    setLeftCollapsed(current => !current);
  }

  function showNavigation() {
    setLeftCollapsed(false);
  }

  function finishOnboarding() {
    try { window.localStorage.setItem(ONBOARDING_STORAGE_KEY, 'true'); } catch (_) { /* le guide reste simplement local à cette session */ }
    setOnboardingOpen(false);
  }

  function toggleContext() {
    if (!hasContextToSurface) {
      setLandingContextOpen(current => !current);
      return;
    }
    setRightCollapsed(current => !current);
  }

  // Le tiroir se referme dès qu'on a choisi quelque part où aller, ou avec Échap.
  useEffect(() => { setMobileMenuOpen(false); }, [tab, analysisToOpen, activeWorkspaceId]);
  useEffect(() => {
    if (!mobileMenuOpen) return undefined;
    const onKey = event => { if (event.key === 'Escape') setMobileMenuOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileMenuOpen]);

  return <main className={`gv2-shell${mobileMenuOpen ? ' is-mobile-menu-open' : ''}${darkMode ? ' gv2-theme-dark' : ''}${effectiveLeftCollapsed ? ' is-left-collapsed' : ''}${effectiveRightCollapsed ? ' is-right-collapsed' : ''}${isConversationLanding ? ' is-landing' : ''}`} ref={shellRef} style={{ '--gv2-left-width': `${effectiveLeftCollapsed ? 0 : leftWidth}px`, '--gv2-right-width': `${effectiveRightCollapsed ? 0 : rightWidth}px`, '--gv2-discussion-width': `${discussionCollapsed ? 47 : discussionWidth}px` }}>
    <Sidebar workspaces={workspaces} activeWorkspaceId={activeWorkspaceId} activeWorkspace={activeWorkspace} activeTab={tab} mission={mission} onSelectWorkspace={openWorkspace} onCreateWorkspace={createWorkspace} onDeleteWorkspace={deleteWorkspace} deletingWorkspaceId={deletingWorkspaceId} onSelectConversation={() => selectTab('conversation')} onStartNewConversation={startNewConversation} onStartAnalysis={() => selectTab(DEFAULT_TAB)} onOpenAnalysis={id => { setAnalysisToOpen({ id, at: Date.now() }); selectTab(DEFAULT_TAB); }} onOpenCross={id => { setAnalysisToOpen({ crossId: id, at: Date.now() }); selectTab(DEFAULT_TAB); }} onStartCross={() => { setAnalysisToOpen({ startCross: true, at: Date.now() }); selectTab(DEFAULT_TAB); }} onSelectAgent={selectTab} user={bootstrap.user} collapsed={effectiveLeftCollapsed && !mobileMenuOpen} onToggleCollapsed={toggleNavigation} darkMode={darkMode} onToggleDarkMode={() => setDarkMode(current => !current)} onStartGuide={() => setOnboardingOpen(true)} initialSection={sectionDemandee} />
    {mobileMenuOpen && <button type="button" className="gv2-mobile-backdrop" onClick={() => setMobileMenuOpen(false)} aria-label="Fermer le menu de navigation" />}
    <section className="gv2-main-column">
      <header className="gv2-workspace-header">
        <div className="gv2-topline">
          <button type="button" className="gv2-mobile-menu-button" onClick={() => setMobileMenuOpen(true)} aria-label="Ouvrir le menu de navigation" aria-expanded={mobileMenuOpen}><Icon name="menu" size={18} /></button>
          <div className="gv2-workspace-heading" ref={workspaceSwitcherRef}>
            <button type="button" className="gv2-workspace-title" onClick={() => setWorkspaceMenuOpen(current => !current)} aria-expanded={workspaceMenuOpen} aria-controls="gv2-workspace-switcher"><span>{activeWorkspace?.title || 'Nouvel espace de travail'}</span><Icon name="chevronDown" size={17} /></button>
            {workspaceMenuOpen && <div className="gv2-workspace-switcher" id="gv2-workspace-switcher" role="menu" aria-label="Choisir un espace de travail"><button type="button" className="gv2-workspace-switcher-new" role="menuitem" onClick={() => { startNewConversation(); setWorkspaceMenuOpen(false); }}><Icon name="plus" size={15} /><span>Nouvelle conversation</span></button><p>Vos espaces de travail</p><div>{workspaces.length ? workspaces.map(workspace => <button key={workspace.folder_id} type="button" role="menuitem" className={workspace.folder_id === activeWorkspaceId ? 'is-current' : ''} onClick={() => { openWorkspace(workspace.folder_id); setWorkspaceMenuOpen(false); }}><span>{workspaceInitial(workspace.title)}</span><strong>{workspace.title || 'Espace sans titre'}</strong>{workspace.folder_id === activeWorkspaceId && <Icon name="check" size={14} />}</button>) : <small>Aucun espace de travail enregistré pour le moment.</small>}</div></div>}
            <p className="gv2-navigation-trail" aria-label={`Vous êtes ici : ${currentTabLabel}`}><span>Espace de travail</span><Icon name="chevronRight" size={12} /><strong>{currentTabLabel}</strong></p>
          </div>
          <div className="gv2-header-actions">
            <button className={`gv2-header-icon gv2-theme-toggle${darkMode ? ' is-active' : ''}`} type="button" onClick={() => setDarkMode(current => !current)} aria-label={darkMode ? 'Passer au mode clair' : 'Passer au mode sombre'} title={darkMode ? 'Passer au mode clair' : 'Passer au mode sombre'} aria-pressed={darkMode}><Icon name={darkMode ? 'sun' : 'moon'} size={18} /></button>
            {hasContextToSurface && <button className={`gv2-header-icon gv2-context-toggle${tab === 'createur' ? ' gv2-context-toggle--atelier' : ''}`} type="button" onClick={toggleContext} aria-label={tab === 'createur' ? (effectiveRightCollapsed ? 'Ouvrir l’Atelier' : 'Fermer l’Atelier') : (effectiveRightCollapsed ? 'Afficher le contexte du workspace' : 'Masquer le contexte du workspace')} title={tab === 'createur' ? (effectiveRightCollapsed ? 'Ouvrir l’Atelier' : 'Fermer l’Atelier') : (effectiveRightCollapsed ? 'Afficher le contexte du workspace' : 'Masquer le contexte du workspace')}>{tab === 'createur' ? <span>Atelier</span> : <Icon name="sparkle" size={18} />}</button>}
            <div className="gv2-account-menu-wrap" ref={accountMenuRef}>
              <button className="gv2-header-credit" type="button" onClick={() => setAccountMenuOpen(current => !current)} aria-label={`Vos crédits : ${displayedCredits}`} title="Voir vos crédits et les offres"><Icon name="sparkle" size={14} /><strong>{displayedCredits}</strong><span>crédits</span></button>
              <button className="gv2-header-avatar gv2-header-avatar--button" type="button" onClick={() => setAccountMenuOpen(current => !current)} aria-expanded={accountMenuOpen} aria-controls="gv2-account-menu" aria-label="Ouvrir le menu du compte">{workspaceInitial(bootstrap.user?.name || bootstrap.user?.email || 'Nalay')}</button>
              {accountMenuOpen && <section className="gv2-account-menu" id="gv2-account-menu" aria-label="Compte et crédits">
                <header><span>{workspaceInitial(bootstrap.user?.name || bootstrap.user?.email || 'Nalay')}</span><div><strong>{bootstrap.user?.name || firstName}</strong><small>{bootstrap.user?.email || 'Votre espace Gabriel'}</small></div></header>
                <div className="gv2-account-credit-balance"><div><span>Crédits disponibles</span><strong>{displayedCredits}</strong></div><button type="button" onClick={refreshCredits} aria-label="Actualiser le solde de crédits" title="Actualiser"><Icon name="refresh" size={15} /></button></div>
                <p>Utilisez-les pour mobiliser vos spécialistes et faire avancer vos dossiers.</p>
                <div className="gv2-account-menu-actions"><button type="button" onClick={() => { selectTab('tarifs'); setAccountMenuOpen(false); }}>Voir les tarifs<Icon name="chevronRight" size={15} /></button><a className="is-primary" href="/upgrade">Mettre à niveau</a></div>
              </section>}
            </div>
          </div>
        </div>
        <WorkspaceTabs currentTab={tab} onChange={selectTab} />
      </header>
      {backendError && <p className="gv2-backend-notice" role="alert">{backendError}</p>}
      {tab === 'conversation'
        ? <section className={`gv2-conversation-stage${isConversationLanding ? ' is-landing' : ''}`}><ConversationFeed items={items} firstName={firstName} isSubmitting={isSubmitting} landing={isConversationLanding} /><Composer onSend={sendMessage} disabled={isSubmitting} landing={isConversationLanding} /></section>
        : tab === 'createur'
          ? <CreatorConversation workspace={activeWorkspace} lastAnalysis={lastAnalysis} creatorHandoff={creatorHandoff} settings={creatorSettings} refinementRequest={creatorRefinementRequest} onHasOutputChange={setCreatorHasOutput} onWorkspaceChange={refreshWorkspace} onSettingsChange={patch => setCreatorSettings(current => ({ ...current, ...patch }))} contextCollapsed={effectiveRightCollapsed} onShowContext={() => setRightCollapsed(false)} />
          : tab === 'psychologue'
          ? <PsychologueView workspace={activeWorkspace} onWorkspaceChange={refreshWorkspace} onNavigateAgent={selectTab} openAnalysisRequest={analysisToOpen} onAnalysisReady={setLastAnalysis} />
          : tab === 'stratege'
          ? <StrategeView workspace={activeWorkspace} onWorkspaceChange={refreshWorkspace} onNavigateAgent={selectTab} onInterviewChange={setStrategeInterview} />
          : tab === 'tarifs'
          ? <TarifsView />
          : isAgentTab(tab)
          ? <AgentWorkbench agentId={tab} agent={activeAgent} workspace={activeWorkspace} items={items} firstName={firstName} isSubmitting={isSubmitting} onSend={sendMessage} discussionCollapsed={discussionCollapsed} onToggleDiscussion={() => setDiscussionCollapsed(current => !current)} onResizeStart={beginDiscussionResize} onResizeKey={handleDiscussionResizeKey} onResizeReset={() => setDiscussionWidth(DISCUSSION_DEFAULT)} onReturnToConversation={() => selectTab('conversation')} onNavigateAgent={selectTab} contextCollapsed={effectiveRightCollapsed && hasContextToSurface} onShowContext={() => setRightCollapsed(false)} darkMode={darkMode} />
          : tab === 'activity'
            ? <WorkspaceActivity workspace={activeWorkspace} mission={mission} />
            : <WorkspaceMemory workspace={activeWorkspace} />}
    </section>
    <ContextPanel mission={mission} workspace={activeWorkspace} onUpdateWorkspace={updateWorkspaceFields} activeAgent={activeAgent} onStartMission={startMission} isStartingMission={isStartingMission} creatorSettings={creatorSettings} onCreatorSettingsChange={patch => setCreatorSettings(current => ({ ...current, ...patch }))} creatorHasOutput={creatorHasOutput} onCreatorRefinement={text => setCreatorRefinementRequest({ id: Date.now(), text })} onCreatorClose={() => setRightCollapsed(true)} strategeInterview={strategeInterview} />
    {!effectiveLeftCollapsed && <button className="gv2-resize-handle gv2-resize-handle--left" type="button" onPointerDown={event => beginResize('left', event)} onDoubleClick={() => setLeftWidth(LEFT_DEFAULT)} onKeyDown={event => handleResizeKey('left', event)} aria-label="Redimensionner la navigation" title="Glisser pour redimensionner · double clic pour réinitialiser" />}
    {!effectiveRightCollapsed && <button className="gv2-resize-handle gv2-resize-handle--right" type="button" onPointerDown={event => beginResize('right', event)} onDoubleClick={() => setRightWidth(RIGHT_DEFAULT)} onKeyDown={event => handleResizeKey('right', event)} aria-label="Redimensionner le contexte" title="Glisser pour redimensionner · double clic pour réinitialiser" />}
    {onboardingOpen && <OnboardingTour onFinish={finishOnboarding} onOpenNavigation={showNavigation} />}
  </main>;
}
