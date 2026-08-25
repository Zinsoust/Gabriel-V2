import React, { useState } from 'react';
import { Icon } from '../icons.jsx';
import { agents } from '../agent-registry.js';

const agentColors = ['violet', 'green', 'blue', 'orange'];
const statusLabels = { pending: 'En attente', selected: 'Prêt', running: 'En cours', completed: 'Terminé', failed: 'En erreur' };
const missionStatusLabels = { awaiting_input: 'Informations requises', ready: 'Prête à démarrer', running: 'En cours', completed: 'Terminée', failed: 'À relancer' };

function EmptyPanel() {
  return <div className="gv2-panel-empty"><div className="gv2-panel-empty-icon"><Icon name="sparkle" size={23} /></div><h2>Aucune mission active</h2><p>Expliquez à Gabriel ce que vous souhaitez accomplir. Il déterminera la mission et mobilisera les experts utiles.</p></div>;
}

function JourneyRow({ label, done, current, unavailable }) {
  return <div className={`gv2-context-journey-row${current ? ' is-current' : ''}${done ? ' is-done' : ''}`}>
    <span className="gv2-context-journey-state">{done ? <Icon name="check" size={13} /> : <i />}</span>
    <span>{label}</span>
    <small>{done ? 'Disponible' : current ? 'En cours' : unavailable ? 'À lancer' : 'En attente'}</small>
  </div>;
}

/** La droite expose l’état réel du workspace ; le travail et les échanges
 * restent volontairement dans la colonne centrale. */
/* L'objectif du dossier se modifie sur place : on clique sur la phrase, on
   écrit, ça s'enregistre en sortant du champ. Pas de formulaire, pas de
   bouton « Modifier », pas d'écran intermédiaire — c'est le seul moyen de
   l'ajouter sans alourdir un parcours qui n'en demandait pas.

   Échap annule, Entrée valide, Maj+Entrée passe à la ligne. */
function ObjectifDuDossier({ workspace, onUpdateWorkspace }) {
  const objectif = workspace?.objective || '';
  const [edition, setEdition] = useState(false);
  const [texte, setTexte] = useState(objectif);

  if (!workspace) {
    return <p className="gv2-business-objective">Ajoutez votre contexte dans la conversation : Gabriel l’utilisera pour guider les trois spécialistes.</p>;
  }

  async function enregistrer() {
    setEdition(false);
    const propre = texte.trim().slice(0, 500);
    if (propre === objectif) return;
    await onUpdateWorkspace?.(workspace.folder_id, { objective: propre });
  }

  if (edition) {
    return <textarea
      className="gv2-business-objective gv2-business-objective--edit"
      value={texte}
      autoFocus
      rows={3}
      maxLength={500}
      aria-label="Objectif de ce dossier"
      placeholder="Ce que vous cherchez à accomplir dans ce dossier."
      onChange={event => setTexte(event.target.value)}
      onBlur={enregistrer}
      onKeyDown={event => {
        if (event.key === 'Escape') { setTexte(objectif); setEdition(false); }
        if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.blur(); }
      }} />;
  }

  return <button
    type="button"
    className={`gv2-business-objective gv2-business-objective--button${objectif ? '' : ' is-empty'}`}
    onClick={() => { setTexte(objectif); setEdition(true); }}
    title="Modifier l’objectif de ce dossier">
    {objectif || 'Quel est votre objectif ici ? Gabriel s’en sert dès la première réponse.'}
  </button>;
}

function BusinessContext({ workspace, activeAgent, onUpdateWorkspace }) {
  const hasAnalysis = Boolean(workspace?.analysis_id);
  const hasStrategy = Boolean(workspace?.strategy_id);
  const hasCreatorOutput = Boolean(workspace?.creator_output_id);
  const activeId = activeAgent?.id;

  return <section className="gv2-business-context" aria-label="Contexte business">
    <p className="gv2-panel-eyebrow"><Icon name="sparkle" size={16} />Contexte business</p>
    {activeAgent && <div className="gv2-context-agent">
      <img src={activeAgent.portrait} alt="" />
      <div><strong>{activeAgent.name}</strong><span>{activeAgent.contextLabel}</span></div>
    </div>}
    <h2>{workspace?.title || 'Workspace à définir'}</h2>
    <ObjectifDuDossier workspace={workspace} onUpdateWorkspace={onUpdateWorkspace} />
    <div className="gv2-context-source"><Icon name="link" size={15} /><span>{workspace?.source_type ? `Source : ${workspace.source_type}` : 'Aucune source connectée'}</span></div>
    <div className="gv2-context-journey" aria-label="Avancement des agents">
      <JourneyRow label="Psychologue" done={hasAnalysis} current={activeId === 'psychologue' && !hasAnalysis} />
      <JourneyRow label="Stratège" done={hasStrategy} current={activeId === 'stratege' && !hasStrategy} unavailable={!hasAnalysis} />
      <JourneyRow label="Créateur" done={hasCreatorOutput} current={activeId === 'createur' && !hasCreatorOutput} unavailable={!hasStrategy} />
    </div>
  </section>;
}

const creatorFormats = [
  ['script', 'Script court'], ['youtube', 'Script YouTube'], ['tiktok', 'TikTok / Reels'],
  ['linkedin', 'Post LinkedIn'], ['post', 'Thread'], ['email', 'Séquence email'], ['sales_page', 'Page de vente'],
];
const creatorTones = [
  ['expert', 'Expert'], ['premium', 'Premium'], ['educational', 'Pédagogique'],
  ['storytelling', 'Storytelling'], ['direct_response', 'Direct'], ['emotional', 'Émotionnel'],
];
const creatorObjectives = [
  ['', 'Selon la demande'], ['attention', 'Capter l’attention'], ['education', 'Éduquer'],
  ['conversion', 'Convertir'], ['autorite', 'Installer l’autorité'], ['sales', 'Vendre'], ['launch', 'Préparer un lancement'],
];
const creatorChannels = [['', 'Automatique'], ['tiktok', 'TikTok'], ['youtube', 'YouTube'], ['instagram', 'Instagram'], ['linkedin', 'LinkedIn'], ['email', 'Email'], ['website', 'Site web'], ['ads', 'Publicité']];
const creatorEmotions = [['', 'Aucune — facultatif'], ['confiance', 'Confiance'], ['curiosite', 'Curiosité'], ['inspiration', 'Inspiration'], ['motivation', 'Motivation'], ['urgence', 'Urgence'], ['empathie', 'Empathie'], ['autorite', 'Autorité']];

function CreatorSelect({ label, value, options, onChange }) {
  return <label className="gv2-creator-setting">
    <span>{label}</span>
    <select value={value || ''} onChange={event => onChange(event.target.value)}>
      {options.map(([optionValue, optionLabel]) => <option key={optionValue || 'default'} value={optionValue}>{optionLabel}</option>)}
    </select>
  </label>;
}

/** Les réglages ne coupent jamais la conversation : ils restent une aide
 * secondaire dans la troisième zone, comme le contexte business. */
function CreatorContextPanel({ workspace, settings, onSettingsChange, hasOutput, onRefinement, onClose }) {
  const hasAnalysis = Boolean(workspace?.analysis_id);
  const hasStrategy = Boolean(workspace?.strategy_id);
  return <div className="gv2-creator-context-panel">
    <header className="gv2-creator-atelier-head"><strong>Atelier</strong><button type="button" onClick={onClose} aria-label="Fermer l’Atelier" title="Fermer l’Atelier"><Icon name="close" size={18} /></button></header>
    <section className="gv2-creator-context-intro">
      <p className="gv2-panel-eyebrow"><Icon name="sparkle" size={16} />Atelier de création</p>
      <div className="gv2-context-agent">
        <img src={agents.createur.portrait} alt="" />
        <div><strong>Le Créateur</strong><span>Rédaction et formats de conversion</span></div>
      </div>
      <h2>Donnez le cap.<br />La discussion fait le reste.</h2>
      <p>Réglez ici le cadre de la création. Vous pouvez aussi ne rien choisir : le Créateur s’adapte à votre demande.</p>
    </section>

    <section className="gv2-creator-settings" aria-label="Paramètres de création">
      <p className="gv2-panel-label">Paramètres de création</p>
      <CreatorSelect label="Format" value={settings.contentType} options={creatorFormats} onChange={contentType => onSettingsChange({ contentType })} />
      <CreatorSelect label="Canal" value={settings.channel} options={creatorChannels} onChange={channel => onSettingsChange({ channel })} />
      <CreatorSelect label="Tonalité" value={settings.tone} options={creatorTones} onChange={tone => onSettingsChange({ tone })} />
      <CreatorSelect label="Objectif" value={settings.objective} options={creatorObjectives} onChange={objective => onSettingsChange({ objective })} />
      <label className="gv2-creator-setting gv2-creator-range"><span>Liberté créative <b>{settings.creativity || 50}</b></span><input type="range" min="0" max="100" value={settings.creativity || 50} onChange={event => onSettingsChange({ creativity: Number(event.target.value) })} /></label>
      <details className="gv2-creator-advanced-settings"><summary>Options avancées<Icon name="chevronDown" size={14} /></summary><div><CreatorSelect label="Émotion visée" value={settings.emotion} options={creatorEmotions} onChange={emotion => onSettingsChange({ emotion })} /><label className="gv2-creator-switch"><input type="checkbox" checked={Boolean(settings.generateVariant)} onChange={event => onSettingsChange({ generateVariant: event.target.checked })} /><span /><div><strong>Proposer une variante</strong><small>Une seconde piste si elle apporte une vraie différence.</small></div></label></div></details>
    </section>

    <section className="gv2-creator-linked-context">
      <p className="gv2-panel-label">Contexte relié</p>
      <div><span className={hasAnalysis ? 'is-ready' : ''}>{hasAnalysis ? <Icon name="check" size={12} /> : <i />}</span><p><strong>Audience</strong><small>{hasAnalysis ? 'Analyse disponible' : 'Aucune analyse reliée'}</small></p></div>
      <div><span className={hasStrategy ? 'is-ready' : ''}>{hasStrategy ? <Icon name="check" size={12} /> : <i />}</span><p><strong>Stratégie</strong><small>{hasStrategy ? 'Stratégie disponible' : 'Aucune stratégie reliée'}</small></p></div>
    </section>

    {hasOutput && <section className="gv2-creator-refinements">
      <p className="gv2-panel-label">Pistes de modification</p>
      <p>Facultatives : elles préparent simplement votre prochaine instruction.</p>
      <div>
        <button type="button" onClick={() => onRefinement('Raccourcis et clarifie le message, sans perdre l’idée principale.')}>Raccourcir et clarifier</button>
        <button type="button" onClick={() => onRefinement('Renforce le hook et les premières lignes pour retenir immédiatement l’attention.')}>Renforcer le hook</button>
        <button type="button" onClick={() => onRefinement('Propose un angle plus inattendu, tout en gardant l’objectif initial.')}>Changer l’angle</button>
      </div>
    </section>}
  </div>;
}

function ContextState({ done, label, detail }) {
  return <div className={`gv2-strategy-context-state${done ? ' is-done' : ''}`}>
    <span>{done ? <Icon name="check" size={12} /> : <i />}</span>
    <div><strong>{label}</strong>{detail && <small>{detail}</small>}</div>
  </div>;
}

/** Le Stratège ne prétend jamais connaître ce qui n'a pas été fourni. Cette
 * lecture transforme le contexte réel du workspace en niveau de clarté
 * actionnable, avant de prendre des décisions de positionnement. */
function StrategyContextPanel({ workspace, mission, onStart, isStarting }) {
  const [view, setView] = useState('progress');
  const known = {
    identity: Boolean(workspace?.title),
    objective: Boolean(workspace?.objective),
    source: Boolean(workspace?.source_type || workspace?.source_summary),
    audience: Boolean(workspace?.analysis_id),
    strategy: Boolean(workspace?.strategy_id),
  };
  const knownCount = Object.values(known).filter(Boolean).length;
  const isClear = knownCount >= 3;
  const progressItems = [
    { key: 'identity', label: 'Identité de l’entreprise', detail: workspace?.title || '' },
    { key: 'objective', label: 'Objectif actuel', detail: workspace?.objective || '' },
    { key: 'source', label: 'Signaux terrain', detail: workspace?.source_type ? `Source : ${workspace.source_type}` : '' },
    { key: 'audience', label: 'Audience', detail: workspace?.analysis_id ? 'Analyse disponible' : '' },
    { key: 'strategy', label: 'Décision stratégique', detail: workspace?.strategy_id ? 'Stratégie reliée' : '' },
  ];
  const missingItems = ['Vision et positionnement', 'Modèle économique', 'Ressources disponibles', 'Contraintes à respecter', 'Historique utile'];
  const historyItems = [
    workspace?.source_type && { label: 'Source reliée', detail: `${workspace.source_type}${workspace.source_summary ? ` · ${workspace.source_summary}` : ''}` },
    workspace?.analysis_id && { label: 'Analyse d’audience', detail: 'Disponible pour éclairer la décision.' },
    workspace?.strategy_id && { label: 'Stratégie enregistrée', detail: 'Une décision existe déjà dans ce workspace.' },
    mission?.title && { label: 'Mission Gabriel', detail: mission.title },
  ].filter(Boolean);

  return <div className="gv2-strategy-context-panel">
    <section className="gv2-strategy-context-intro">
      <p className="gv2-panel-eyebrow"><Icon name="sparkle" size={16} />Lecture stratégique</p>
      <div className="gv2-context-agent"><img src={agents.stratege.portrait} alt="" /><div><strong>{agents.stratege.name}</strong><span>Décision et positionnement</span></div></div>
      <div className={`gv2-strategy-clarity${isClear ? ' is-clear' : ''}`}><span /><p>{isClear ? 'Votre situation est suffisamment claire' : 'Le contexte est en cours de clarification'}</p></div>
      <div className="gv2-strategy-clarity-line"><i style={{ width: `${Math.max(16, knownCount * 20)}%` }} /></div>
      <h2>{isClear ? 'Compréhension suffisante' : 'Contexte à préciser'}</h2>
      <p>Ariane utilise uniquement les informations réellement reliées à ce workspace.</p>
    </section>

    <section className="gv2-strategy-context-body">
      <div className="gv2-strategy-context-tabs" role="tablist" aria-label="Lecture du contexte"><button type="button" role="tab" aria-selected={view === 'progress'} className={view === 'progress' ? 'is-active' : ''} onClick={() => setView('progress')}>Progression</button><button type="button" role="tab" aria-selected={view === 'history'} className={view === 'history' ? 'is-active' : ''} onClick={() => setView('history')}>Historique</button></div>
      {view === 'progress' ? <>
        <p className="gv2-strategy-context-label">Déjà compris</p>
        <div className="gv2-strategy-context-list">{progressItems.filter(item => known[item.key]).map(item => <ContextState key={item.key} done label={item.label} detail={item.detail} />)}</div>
        {missingItems.length > 0 && <><p className="gv2-strategy-context-label gv2-strategy-context-label--pending">À éclaircir</p><div className="gv2-strategy-context-list">{missingItems.map(label => <ContextState key={label} label={label} />)}</div></>}
      </> : <div className="gv2-strategy-history">{historyItems.length ? historyItems.map(item => <div key={item.label}><span /><p><strong>{item.label}</strong><small>{item.detail}</small></p></div>) : <p>Aucun événement lié pour le moment. Ajoutez des sources ou expliquez votre contexte dans la conversation.</p>}</div>}
      {mission?.execution && (mission.status === 'ready' || mission.status === 'failed') && <button type="button" className="gv2-strategy-context-launch" onClick={onStart} disabled={isStarting}><Icon name="sparkle" size={15} />{isStarting ? 'Lancement…' : mission.execution.label}</button>}
    </section>
  </div>;
}

function MissionPanel({ mission, onStart, isStarting }) {
  const isRunning = mission.status === 'running';
  const isDone = mission.status === 'completed';
  const isWaiting = mission.status === 'awaiting_input';
  return <div className="gv2-panel-stack">
    <section className="gv2-panel-card gv2-mission-card">
      <p className="gv2-panel-eyebrow"><Icon name="sparkle" size={16} />{isRunning ? 'Mission en cours' : isDone ? 'Mission terminée' : 'Mission Gabriel'}</p>
      <h2>{mission.title}</h2>
      {mission.objective && <p className="gv2-mission-objective">{mission.objective}</p>}
      <div className={`gv2-mission-status gv2-mission-status--${mission.status}`}><span />{missionStatusLabels[mission.status] || 'Mission'}</div>
      {isRunning && <div className="gv2-mission-progress" aria-label={`Progression : ${mission.progress || 0}%`}><i style={{ width: `${Math.max(3, Math.min(100, mission.progress || 0))}%` }} /><small>{mission.progress || 0}%</small></div>}
    </section>

    {mission.inputs?.length > 0 && <section className="gv2-panel-card">
      <p className="gv2-panel-label">{isWaiting ? 'Pour avancer' : 'Sources de la mission'}</p>
      <div className="gv2-mission-inputs">{mission.inputs.map(input => <div key={input.id}>
        <strong>{input.label}</strong>
        {input.value && <span title={input.value}>{input.value}</span>}
        {input.help && <small>{input.help}</small>}
      </div>)}</div>
      {isWaiting && <p className="gv2-panel-hint">Répondez dans la conversation : Gabriel mettra à jour la mission dès que la donnée est disponible.</p>}
    </section>}

    {mission.agents.length > 0 && <section className="gv2-panel-card">
      <p className="gv2-panel-label">Équipe mobilisée</p>
      <div className="gv2-agent-list">{mission.agents.map((agent, index) => <div className="gv2-agent-row" key={agent.id}>
        <span className={`gv2-agent-icon gv2-agent-icon--${agentColors[index % agentColors.length]}`}><Icon name="sparkle" size={15} /></span>
        <span className="gv2-agent-copy"><strong>{agent.name}</strong><small>{agent.description || 'Mobilisé par Gabriel'}</small></span>
        <span className={`gv2-agent-status gv2-agent-status--${agent.status}`} title={statusLabels[agent.status]} />
      </div>)}</div>
    </section>}

    {mission.deliverables.length > 0 && <section className="gv2-panel-card">
      <p className="gv2-panel-label">Livrables prévus</p>
      <div className="gv2-deliverable-list">{mission.deliverables.map((item, index) => <div key={`${item.title}-${index}`}><Icon name="file" size={17} /><span>{item.title}</span>{item.type && <small>{item.type}</small>}</div>)}</div>
    </section>}

    {(mission.execution && (mission.status === 'ready' || mission.status === 'failed')) && <button type="button" className="gv2-mission-launch" onClick={onStart} disabled={isStarting}><Icon name="sparkle" size={17} /><span>{isStarting ? 'Lancement…' : mission.execution.label}</span></button>}
    {mission.error && <section className="gv2-panel-card gv2-mission-error"><Icon name="close" size={16} /><p>{mission.error}</p></section>}

    <section className="gv2-panel-card gv2-guidance-card"><Icon name="message" size={18} /><p>Gabriel pilote cette étape. Continuez la conversation pour préciser le contexte ou les données nécessaires.</p></section>
  </div>;
}

/** Registre de panneaux. Le backend peut indiquer panel.type sans ajouter de logique dans la page. */
const panelRegistry = { empty: EmptyPanel, mission_summary: MissionPanel, youtube_analyzer: MissionPanel, document_analyzer: MissionPanel, offer_builder: MissionPanel, data_import: MissionPanel };

export function ContextPanel({ mission, workspace, activeAgent, onUpdateWorkspace, onStartMission, isStartingMission, creatorSettings, onCreatorSettingsChange, creatorHasOutput, onCreatorRefinement, onCreatorClose }) {
  if (activeAgent?.id === 'createur') return <aside className="gv2-context-panel gv2-context-panel--creator" aria-label="Paramètres de création">
    <CreatorContextPanel workspace={workspace} settings={creatorSettings} onSettingsChange={onCreatorSettingsChange} hasOutput={creatorHasOutput} onRefinement={onCreatorRefinement} onClose={onCreatorClose} />
  </aside>;
  if (activeAgent?.id === 'stratege') return <aside className="gv2-context-panel gv2-context-panel--strategy" aria-label="Clarté du contexte stratégique">
    <StrategyContextPanel workspace={workspace} mission={mission} onStart={onStartMission} isStarting={isStartingMission} />
  </aside>;
  const Panel = mission ? (panelRegistry[mission.panelType] || panelRegistry.mission_summary) : panelRegistry.empty;
  return <aside className="gv2-context-panel" aria-label="Contexte du workspace">
    <BusinessContext workspace={workspace} activeAgent={activeAgent} onUpdateWorkspace={onUpdateWorkspace} />
    <Panel mission={mission} onStart={onStartMission} isStarting={isStartingMission} />
  </aside>;
}
