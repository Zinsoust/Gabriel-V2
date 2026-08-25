import React, { useEffect, useMemo, useState } from 'react';
import { GabrielMark, Icon } from '../icons.jsx';
import { workspaceInitial } from '../data-adapters.js';
import { agents } from '../agent-registry.js';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

const railItems = [
  { id: 'home', icon: 'home', label: 'Accueil' },
  { id: 'workspaces', icon: 'grid', label: 'Workspaces' },
  { id: 'library', icon: 'library', label: 'Bibliothèque' },
  { id: 'team', icon: 'team', label: 'Équipe' },
  { id: 'activity', icon: 'activity', label: 'Activité' },
  { id: 'strategies', icon: 'archive', label: 'Stratégies' },
];

const sectionCopy = {
  home: { eyebrow: 'Gabriel.ai', title: 'Votre espace', search: 'Rechercher dans Gabriel' },
  workspaces: { eyebrow: 'Organisation', title: 'Workspaces', search: 'Rechercher un workspace' },
  library: { eyebrow: 'Contexte', title: 'Bibliothèque', search: 'Rechercher une source' },
  team: { eyebrow: 'Spécialistes', title: 'Équipe', search: 'Rechercher un agent' },
  activity: { eyebrow: 'Suivi', title: 'Activité', search: 'Rechercher une activité' },
  strategies: { eyebrow: 'Décisions', title: 'Stratégies', search: 'Rechercher une stratégie' },
  settings: { eyebrow: 'Préférences', title: 'Paramètres', search: 'Rechercher un réglage' },
};

function RailButton({ item, active, onClick }) {
  return <button type="button" className={`gv2-rail-button${active ? ' is-active' : ''}`} onClick={onClick} title={item.label} aria-label={item.label}>
    <Icon name={item.icon} size={18} />
  </button>;
}

function AgentRow({ agent, active, onClick }) {
  return <button type="button" className={`gv2-agent-nav-row${active ? ' is-active' : ''}`} onClick={onClick}>
    <img src={agent.portrait} alt="" />
    <span><strong>{agent.shortName}</strong><small>{agent.contextLabel}</small></span>
    <Icon name="chevronRight" size={15} />
  </button>;
}

function WorkspaceList({ workspaces, activeWorkspaceId, query, onSelectWorkspace, onDeleteWorkspace, deletingWorkspaceId }) {
  const filtered = useMemo(() => workspaces.filter(workspace => (workspace.title || '').toLocaleLowerCase('fr').includes(query.toLocaleLowerCase('fr'))), [workspaces, query]);
  return <div className="gv2-workspace-list">
    {filtered.map(workspace => <div className="gv2-workspace-row" key={workspace.folder_id}>
      <button type="button" className={`gv2-workspace-select${workspace.folder_id === activeWorkspaceId ? ' is-current' : ''}`} onClick={() => onSelectWorkspace(workspace.folder_id)}>
        <span className="gv2-workspace-avatar">{workspaceInitial(workspace.title)}</span>
        <span>{workspace.title || 'Workspace'}</span>
        {workspace.folder_id === activeWorkspaceId && <Icon name="check" size={14} />}
      </button>
      <button type="button" className="gv2-workspace-delete" disabled={deletingWorkspaceId === workspace.folder_id} onClick={() => onDeleteWorkspace(workspace)} aria-label={`Supprimer ${workspace.title || 'ce workspace'}`} title="Supprimer ce workspace"><Icon name="close" size={13} /></button>
    </div>)}
    {!filtered.length && <p className="gv2-nav-empty">Aucun workspace ne correspond à cette recherche.</p>}
  </div>;
}

function HomePanel({ activeWorkspace, onStartNewConversation }) {
  return <div className="gv2-nav-content">
    <button type="button" className="gv2-nav-primary-action" onClick={onStartNewConversation}><Icon name="message" size={17} /><span>Nouvelle conversation</span></button>
    <section className="gv2-nav-note">
      <span className="gv2-nav-note-mark">G</span>
      <div><strong>{activeWorkspace?.title || 'Choisissez un workspace'}</strong><p>{activeWorkspace?.objective || 'Gabriel organise les sources, les spécialistes et les livrables autour de votre objectif.'}</p></div>
    </section>
  </div>;
}

function LibraryPanel({ activeWorkspace }) {
  return <div className="gv2-nav-content">
    <section className="gv2-nav-note">
      <span className="gv2-nav-note-mark"><Icon name="library" size={16} /></span>
      <div><strong>Sources du workspace</strong><p>{activeWorkspace?.source_type ? `Source active : ${activeWorkspace.source_type}.` : 'Les liens, fichiers et données utiles apparaîtront ici dès leur ajout dans la conversation.'}</p></div>
    </section>
    <p className="gv2-nav-section-label">ÉTAT DU DOSSIER</p>
    <div className="gv2-nav-status-list">
      <span><Icon name={activeWorkspace?.analysis_id ? 'check' : 'more'} size={14} />Analyse d’audience</span>
      <span><Icon name={activeWorkspace?.strategy_id ? 'check' : 'more'} size={14} />Décision stratégique</span>
      <span><Icon name={activeWorkspace?.creator_output_id ? 'check' : 'more'} size={14} />Créations</span>
    </div>
  </div>;
}

function TeamPanel({ activeTab, query, onSelectAgent }) {
  const filtered = Object.values(agents).filter(agent => `${agent.name} ${agent.contextLabel}`.toLocaleLowerCase('fr').includes(query.toLocaleLowerCase('fr')));
  return <div className="gv2-nav-content"><p className="gv2-nav-section-label">LES SPÉCIALISTES</p><div className="gv2-agent-nav-list">
    {filtered.map(agent => <AgentRow key={agent.id} agent={agent} active={activeTab === agent.id} onClick={() => onSelectAgent(agent.id)} />)}
    {!filtered.length && <p className="gv2-nav-empty">Aucun agent ne correspond à cette recherche.</p>}
  </div></div>;
}

const RESULTAT_LABEL = {
  fonctionne:    { classe: 'worked',   texte: 'A fonctionné' },
  sans_resultat: { classe: 'noresult', texte: 'Sans résultat' },
};

function fmtDateStrategie(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch (_) { return ''; }
}

/* Le retour terrain — « cette stratégie a-t-elle fonctionné ? » — est la
   seule chose que l'ancienne page « Mes stratégies » offrait et qu'on ne
   retrouvait nulle part dans la V2. Le reste (ouvrir, lire l'avancement)
   est déjà couvert par la liste des workspaces. */
function StrategyCard({ strategie, onMarquer, onSupprimer, suppression }) {
  const resultat = RESULTAT_LABEL[strategie.resultat];
  return <article className="gv2-strategy-card">
    <div className="gv2-strategy-card-top">
      <div>
        <div className="gv2-strategy-card-title">{strategie.title || 'Stratégie'}</div>
        <div className="gv2-strategy-card-meta">
          <span>{fmtDateStrategie(strategie.created_at)}</span>
          {resultat && <span className={`gv2-strategy-badge is-${resultat.classe}`}>{resultat.texte}</span>}
        </div>
      </div>
      <div className="gv2-strategy-card-actions">
        <a className="gv2-strategy-open" href={`/strategies/${encodeURIComponent(strategie.strategy_id)}/open`}>Ouvrir</a>
        <button type="button" className="gv2-strategy-delete" disabled={suppression} onClick={() => onSupprimer(strategie.strategy_id)} aria-label="Supprimer cette stratégie" title="Supprimer"><Icon name="close" size={13} /></button>
      </div>
    </div>
    <div className="gv2-strategy-track">
      <p>Cette stratégie a-t-elle fonctionné sur le terrain ?</p>
      <div className="gv2-strategy-track-options">
        <button type="button" className={strategie.resultat === 'fonctionne' ? 'is-selected' : ''} onClick={() => onMarquer(strategie.strategy_id, 'fonctionne')}>Oui, elle a marché</button>
        <button type="button" className={strategie.resultat === 'sans_resultat' ? 'is-selected' : ''} onClick={() => onMarquer(strategie.strategy_id, 'sans_resultat')}>Appliquée, sans résultat</button>
        <button type="button" className={!strategie.resultat ? 'is-selected' : ''} onClick={() => onMarquer(strategie.strategy_id, '')}>Pas encore testée</button>
      </div>
    </div>
  </article>;
}

function StrategiesPanel() {
  const [strategies, setStrategies] = useState(null);
  const [suppression, setSuppression] = useState('');

  useEffect(() => {
    let vivant = true;
    fetchV2('/strategies').then(async response => {
      if (isLoginResponse(response)) return;
      const payload = await readApiPayload(response, 'Vos stratégies').catch(() => null);
      if (vivant) setStrategies(Array.isArray(payload) ? payload : []);
    }).catch(() => { if (vivant) setStrategies([]); });
    return () => { vivant = false; };
  }, []);

  async function marquer(strategyId, resultat) {
    setStrategies(current => current.map(item => item.strategy_id === strategyId ? { ...item, resultat } : item));
    const strategie = (strategies || []).find(item => item.strategy_id === strategyId);
    try {
      await fetchV2('/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_id: strategyId, analysis_id: strategie?.analysis_id || '', resultat }),
      });
    } catch (_) { /* Le retour terrain reste affiché ; il se resynchronisera au prochain chargement. */ }
  }

  async function supprimer(strategyId) {
    if (!window.confirm('Supprimer définitivement cette stratégie ?')) return;
    setSuppression(strategyId);
    try {
      await fetchV2(`/strategies/${encodeURIComponent(strategyId)}`, { method: 'DELETE' });
      setStrategies(current => current.filter(item => item.strategy_id !== strategyId));
    } finally {
      setSuppression('');
    }
  }

  if (strategies === null) {
    return <div className="gv2-nav-content"><p className="gv2-nav-loading">Chargement de vos stratégies…</p></div>;
  }

  if (!strategies.length) {
    return <div className="gv2-nav-content">
      <section className="gv2-nav-note">
        <span className="gv2-nav-note-mark"><Icon name="archive" size={16} /></span>
        <div><strong>Aucune stratégie sauvegardée</strong><p>Chaque stratégie générée par Ariane est conservée ici. Vous pourrez suivre si elle a fonctionné sur le terrain.</p></div>
      </section>
    </div>;
  }

  const total  = strategies.length;
  const marche = strategies.filter(s => s.resultat === 'fonctionne').length;

  return <div className="gv2-nav-content gv2-nav-content--strategies">
    <div className="gv2-strategy-stats">
      <div><strong>{total}</strong><span>Créées</span></div>
      <div><strong>{marche}</strong><span>Ont fonctionné</span></div>
    </div>
    <div className="gv2-strategy-list">
      {strategies.map(strategie => <StrategyCard key={strategie.strategy_id} strategie={strategie}
        onMarquer={marquer} onSupprimer={supprimer} suppression={suppression === strategie.strategy_id} />)}
    </div>
  </div>;
}

function ActivityPanel({ mission, onSelectConversation }) {
  const status = mission?.status === 'running' ? 'En cours' : mission?.status === 'completed' ? 'Terminée' : mission ? 'À préparer' : 'Aucune mission active';
  return <div className="gv2-nav-content">
    <section className="gv2-nav-note"><span className="gv2-nav-note-mark"><Icon name="activity" size={16} /></span><div><strong>{status}</strong><p>{mission?.title || 'Les missions et les étapes pilotées par Gabriel seront regroupées ici.'}</p></div></section>
    {mission && <button type="button" className="gv2-nav-text-action" onClick={onSelectConversation}>Voir la conversation <Icon name="chevronRight" size={15} /></button>}
  </div>;
}

function SettingsPanel({ user, darkMode, onToggleDarkMode, onStartGuide }) {
  return <div className="gv2-nav-content">
    <section className="gv2-nav-note"><span className="gv2-user-avatar">{workspaceInitial(user?.name || user?.email || 'G')}</span><div><strong>{user?.name || user?.email?.split('@')[0] || 'Votre compte'}</strong><p>Les préférences personnelles, notifications et intégrations seront gérées ici.</p></div></section>
    <section className="gv2-nav-theme" aria-label="Apparence">
      <span><Icon name={darkMode ? 'moon' : 'sun'} size={16} /></span>
      <div><strong>Mode sombre</strong><p>{darkMode ? 'Activé' : 'Désactivé'}</p></div>
      <button type="button" role="switch" aria-checked={darkMode} aria-label="Activer le mode sombre" className={darkMode ? 'is-active' : ''} onClick={onToggleDarkMode}><i /></button>
    </section>
    <button className="gv2-nav-guide" type="button" onClick={onStartGuide}><Icon name="sparkle" size={15} /><span>Relancer le guide</span><Icon name="chevronRight" size={14} /></button>
  </div>;
}

export function Sidebar({ workspaces, activeWorkspaceId, activeWorkspace, activeTab, mission, onSelectWorkspace, onCreateWorkspace, onDeleteWorkspace, deletingWorkspaceId, onSelectConversation, onStartNewConversation, onSelectAgent, user, collapsed, onToggleCollapsed, darkMode, onToggleDarkMode, onStartGuide }) {
  const [creating, setCreating] = useState(false);
  const [workspaceName, setWorkspaceName] = useState('');
  const [creatingPending, setCreatingPending] = useState(false);
  const [activeSection, setActiveSection] = useState('workspaces');
  const [query, setQuery] = useState('');
  const content = sectionCopy[activeSection] || sectionCopy.workspaces;

  function selectSection(section) {
    setActiveSection(section);
    setQuery('');
    if (collapsed) onToggleCollapsed();
    if (section === 'home') onStartNewConversation();
  }

  function expandNavigation() {
    if (collapsed) onToggleCollapsed();
  }

  async function submit(event) {
    event.preventDefault();
    const title = workspaceName.trim();
    if (!title || creatingPending) return;
    setCreatingPending(true);
    try {
      await onCreateWorkspace(title);
      setWorkspaceName('');
      setCreating(false);
    } finally {
      setCreatingPending(false);
    }
  }

  return <aside className={`gv2-sidebar${collapsed ? ' is-collapsed' : ''}`} aria-label="Navigation principale">
    <nav className="gv2-rail" aria-label="Navigation globale">
      <button type="button" className="gv2-rail-brand" onClick={expandNavigation} aria-label="Ouvrir le menu Gabriel"><GabrielMark size={18} /></button>
      <div className="gv2-rail-items">{railItems.map(item => <RailButton key={item.id} item={item} active={activeSection === item.id} onClick={() => selectSection(item.id)} />)}</div>
      <div className="gv2-rail-bottom"><button type="button" className="gv2-rail-user" title={user?.name || user?.email || 'Votre compte'} aria-label="Votre compte" onClick={() => selectSection('settings')}><Icon name="settings" size={17} /></button></div>
    </nav>
    <button type="button" className={`gv2-sidebar-toggle${collapsed ? ' is-collapsed' : ''}`} onClick={onToggleCollapsed} aria-label={collapsed ? 'Agrandir le menu' : 'Réduire le menu'} title={collapsed ? 'Agrandir le menu' : 'Réduire le menu'}>
      <Icon name="panelLeft" size={18} />
    </button>

    {!collapsed && <section className="gv2-nav-detail" aria-label={content.title}>
      <header className="gv2-nav-detail-header"><div><p>{content.eyebrow}</p><h2>{content.title}</h2></div><div className="gv2-nav-shortcuts" aria-label="Sections du menu">{railItems.map(item => <RailButton key={item.id} item={item} active={activeSection === item.id} onClick={() => selectSection(item.id)} />)}</div></header>
      <label className="gv2-nav-search"><Icon name="search" size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder={content.search} aria-label={content.search} /></label>

      {activeSection === 'home' && <HomePanel activeWorkspace={activeWorkspace} onStartNewConversation={onStartNewConversation} />}
      {activeSection === 'workspaces' && <div className="gv2-nav-content gv2-nav-content--workspaces"><div className="gv2-create-wrap"><button className="gv2-new-workspace" type="button" onClick={() => setCreating(value => !value)} aria-expanded={creating}><Icon name="plus" size={17} /><span>Nouveau workspace</span><kbd>⌘ K</kbd></button>{creating && <form className="gv2-workspace-form" onSubmit={submit}><label htmlFor="workspace-name">Nom du workspace</label><div><input id="workspace-name" autoFocus value={workspaceName} onChange={event => setWorkspaceName(event.target.value)} placeholder="Ex. Golden Dove" maxLength="200" /><button type="submit" disabled={!workspaceName.trim() || creatingPending}>{creatingPending ? '…' : 'Créer'}</button></div></form>}</div><p className="gv2-nav-section-label">VOS WORKSPACES</p><WorkspaceList workspaces={workspaces} activeWorkspaceId={activeWorkspaceId} query={query} onSelectWorkspace={onSelectWorkspace} onDeleteWorkspace={onDeleteWorkspace} deletingWorkspaceId={deletingWorkspaceId} /></div>}
      {activeSection === 'library' && <LibraryPanel activeWorkspace={activeWorkspace} />}
      {activeSection === 'team' && <TeamPanel activeTab={activeTab} query={query} onSelectAgent={onSelectAgent} />}
      {activeSection === 'activity' && <ActivityPanel mission={mission} onSelectConversation={onSelectConversation} />}
      {activeSection === 'strategies' && <StrategiesPanel />}
      {activeSection === 'settings' && <SettingsPanel user={user} darkMode={darkMode} onToggleDarkMode={onToggleDarkMode} onStartGuide={onStartGuide} />}
    </section>}
  </aside>;
}
