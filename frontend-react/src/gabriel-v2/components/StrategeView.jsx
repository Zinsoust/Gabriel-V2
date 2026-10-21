import React, { useEffect, useRef, useState } from 'react';
import { Icon } from '../icons.jsx';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

const VOICE_MODE_KEY = 'gabriel_voice_mode';
const VOICE_ID_KEY = 'gabriel_voice_id';

/* ── StrategeView — Tranches A + B ────────────────────────────────────────
   Réimplémentation native (React) de l'agent Le Stratège, jusqu'ici
   encapsulé en <iframe> depuis templates/stratege.html (voir
   AgentWorkspace.jsx). Même contrat API — /strategize, /status/<jobId>,
   /strategies/<id>, /business-context, /context-chat — aucun changement
   backend. Contrat de l'entretien documenté dans
   docs/interview_frontend_contract.md : le frontend n'y déduit aucun fait
   business et ne recalcule pas la complétude, il affiche ce que le serveur
   renvoie (context_progress.understood/remaining notamment).

   Couvert : la reprise d'une stratégie déjà enregistrée
   (workspace.strategy_id), la génération classique à partir d'une analyse
   Psychologue existante (workspace.analysis_id → /strategize → /status),
   l'entretien textuel qui construit le contexte business depuis zéro
   (/business-context → /context-chat, tour par tour, jusqu'à is_ready),
   et le tableau de bord à 5 onglets une fois la stratégie prête. La
   bannière de passerelle Psychologue (sessionStorage gabriel_for_stratege,
   écrite par PsychologueView.jsx) est reprise ici, pas dans la tranche A :
   elle nourrit l'entretien, pas la génération classique seule.

   Hors périmètre, par construction : la couche vocale (micro, ElevenLabs,
   lecture audio) — l'entretien fonctionne entièrement en tapant, comme le
   permet déjà le contrat serveur. Sans micro, il ne manque rien de
   fonctionnel, seulement le confort de la voix.

   Simplification délibérée, actée avec l'utilisateur : les jauges SVG, le
   poster d'offre et l'échelle de prix animée de l'ancienne page laissent
   place à des cartes typographiques simples — même donnée, présentation
   sobre. Le design fin est délégué (GPT/Lovable) sur cette base fidèle. */

function esc(v) { return v == null ? '' : String(v); }

function Section({ title, hint, children }) {
  return <div className="gv2-strat-section">
    <div className="gv2-strat-section-title">{title}</div>
    {hint && <p className="gv2-strat-section-hint">{hint}</p>}
    {children}
  </div>;
}

function Card({ title, children, tone }) {
  return <div className={`gv2-strat-card${tone ? ` is-${tone}` : ''}`}>
    {title && <div className="gv2-strat-card-title">{title}</div>}
    {children}
  </div>;
}

function Row({ label, value }) {
  if (!value) return null;
  return <div className="gv2-strat-row"><span>{label}</span><p>{esc(value)}</p></div>;
}

function Metric({ label, value, suffix }) {
  if (value == null || value === '') return null;
  return <div className="gv2-strat-metric"><div className="gv2-strat-metric-val">{value}{suffix}</div><div className="gv2-strat-metric-lbl">{label}</div></div>;
}

function Chips({ items, tone }) {
  const clean = (Array.isArray(items) ? items : []).filter(Boolean);
  if (!clean.length) return null;
  return <div className={`gv2-strat-chips${tone ? ` is-${tone}` : ''}`}>{clean.map((c, i) => <span key={i}>{esc(c)}</span>)}</div>;
}

/* Onde décorative — même calcul que la maquette Ariane (aucune donnée
   micro réelle à visualiser ici : le navigateur ne l'expose pas). */
function Waveform({ active = true, bars = 26, height = 26, minimal = false }) {
  const items = Array.from({ length: minimal ? Math.min(bars, 14) : bars });
  return <div className="gv2-ariane-waveform" aria-hidden="true" style={{ height }}>
    {items.map((_, i) => {
      const seed = (Math.sin(i * 1.7) + 1) / 2;
      const base = minimal ? 0.18 + seed * 0.3 : 0.16 + seed * 0.84;
      return <span key={i} style={{
        height: `${Math.max(3, base * height)}px`,
        opacity: active ? 0.35 + base * 0.55 : 0.22,
        animation: active ? `gv2-ariane-wave-bar ${0.9 + (i % 5) * 0.16}s ease-in-out ${i * 0.045}s infinite` : 'none',
      }} />;
    })}
  </div>;
}

function formatTimer(seconds) {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

/* ── Synthèse ─────────────────────────────────────────────────────────── */
function TabSynthese({ d }) {
  const ed = d.executive_decision || {};
  const heroDecision = ed.one_sentence_decision || d.decision_centrale || d.message_central || '';
  const ap = d.audience_psychology_used;
  const apFields = ap && typeof ap === 'object' ? [
    ['Problème principal', ap.main_problem], ['Désir principal', ap.main_desire],
    ['Peur principale', ap.main_fear], ['Frustration clé', ap.main_frustration],
    ['Objection principale', ap.main_objection], ['Valeurs recherchées', ap.values_sought],
  ].filter(([, v]) => v) : [];
  const confRaw = Number(ed.confidence_score);
  const conf = Number.isFinite(confRaw) ? Math.round(confRaw <= 1 ? confRaw * 100 : confRaw) : null;
  const offre = d.offre_recommandee;

  return <>
    {heroDecision && <Section title="Décision prioritaire">
      <Card tone="priority">
        <p className="gv2-strat-hero-text">{esc(heroDecision)}</p>
        {ed.what_to_do_this_week && <Row label="Cette semaine" value={ed.what_to_do_this_week} />}
      </Card>
    </Section>}

    {(conf !== null || (offre && offre.prix_recommande) || ed.expected_business_impact) && (
      <Section title="Indicateurs">
        <div className="gv2-strat-metrics">
          <Metric label="Alignement audience" value={conf} suffix="%" />
          <Metric label="Prix recommandé" value={offre && offre.prix_recommande} />
          <Metric label="Impact attendu" value={ed.expected_business_impact} />
        </div>
      </Section>
    )}

    {d.decision_centrale && d.decision_centrale !== heroDecision && (
      <Section title="Décision centrale"><Card><p className="gv2-strat-hero-text">{esc(d.decision_centrale)}</p></Card></Section>
    )}

    {d.objectif_utilisateur_reformule && (
      <Section title="Objectif reformulé"><Card><Row label="" value={d.objectif_utilisateur_reformule} /></Card></Section>
    )}

    {apFields.length > 0 && (
      <Section title="Psychologie audience · signaux actifs">
        <Card>
          <div className="gv2-strat-metrics gv2-strat-metrics--text">
            {apFields.map(([label, val]) => <div className="gv2-strat-metric" key={label}><div className="gv2-strat-metric-val gv2-strat-metric-val--text">{esc(val)}</div><div className="gv2-strat-metric-lbl">{label}</div></div>)}
          </div>
          <Chips items={ap.decision_drivers} />
        </Card>
      </Section>
    )}
  </>;
}

/* ── Marketing ────────────────────────────────────────────────────────── */
function TabMarketing({ d }) {
  const vtc = d.value_to_create || {};
  const hasValue = vtc.core_value || vtc.why_this_value_matters || vtc.what_the_audience_is_really_buying || vtc.value_gap_in_current_business;
  const hasPositioning = d.message_central || d.angle_positionnel;
  const offre = d.offre_recommandee;
  const pricing = d.pricing_logic;
  const hasPricing = pricing && (pricing.fourchette || pricing.valeur_percue || pricing.niveau_douleur || pricing.capacite_paiement || pricing.justification);
  const imon = d.immediate_monetization_plan;
  const opps = Array.isArray(d.opportunites_marche) ? d.opportunites_marche : [];

  return <>
    {(hasValue || hasPositioning) && <Section title="Valeur à créer">
      <Card>
        {vtc.core_value && <p className="gv2-strat-hero-text">{esc(vtc.core_value)}</p>}
        <Row label="Pourquoi cette valeur compte" value={vtc.why_this_value_matters} />
        <Row label="Ce que l'audience achète vraiment" value={vtc.what_the_audience_is_really_buying} />
        <Row label="Écart à combler" value={vtc.value_gap_in_current_business} />
        <Row label="Message central" value={d.message_central} />
        <Row label="Angle positionnel" value={d.angle_positionnel} />
      </Card>
    </Section>}

    {offre && typeof offre === 'object' && <Section title="Offre recommandée">
      <Card tone="priority">
        {offre.nom && <p className="gv2-strat-hero-text">{esc(offre.nom)}</p>}
        <Row label="Cible précise" value={offre.cible_precise} />
        <Row label="Problème traité" value={offre.probleme_traite} />
        <Row label="Promesse" value={offre.promesse} />
        <Row label="Résultat attendu" value={offre.resultat_attendu} />
        <Row label="Format" value={offre.format} />
        {Array.isArray(offre.livrables) && offre.livrables.length > 0 && (
          <div className="gv2-strat-row"><span>Livrables</span><ul>{offre.livrables.map((l, i) => <li key={i}>{esc(l)}</li>)}</ul></div>
        )}
        <Row label="Message de vente" value={offre.message_de_vente} />
        {offre.prix_recommande && <div className="gv2-strat-metrics">
          <Metric label="Prix recommandé" value={offre.prix_recommande} />
        </div>}
        <Row label="Justification prix" value={offre.justification_prix} />
        <Chips items={offre.canaux_acquisition} />
        <Chips items={offre.objections_a_traiter} tone="neg" />
      </Card>
    </Section>}

    {hasPricing && <Section title="Logique de prix">
      <Card>
        <Row label="Fourchette" value={pricing.fourchette} />
        <div className="gv2-strat-metrics">
          <Metric label="Valeur perçue" value={pricing.valeur_percue} />
          <Metric label="Douleur marché" value={pricing.niveau_douleur} />
          <Metric label="Budget cible" value={pricing.capacite_paiement} />
        </div>
        <Row label="Justification" value={pricing.justification} />
      </Card>
    </Section>}

    {imon && (imon.next_24h_action || imon.next_7_days_action) && <Section title="Plan de monétisation immédiate">
      <Card tone="priority">
        <Row label="24 h" value={imon.next_24h_action} />
        <Row label="7 jours" value={imon.next_7_days_action} />
        <Row label="Offre à tester" value={imon.first_offer_to_test} />
        <Row label="Call to action" value={imon.first_call_to_action} />
        <Row label="Métrique clé" value={imon.metric_to_watch} />
      </Card>
    </Section>}

    {opps.length > 0 && <Section title="Opportunités de marché détectées">
      {opps.map((o, i) => o && typeof o === 'object' && (
        <Card key={i}>
          <Row label="Décision recommandée" value={o.recommandation} />
          <Row label="Action concrète" value={o.action_concrete} />
          <Row label="Mesure de succès" value={o.mesure_succes} />
          <Row label="Signal détecté" value={o.signal} />
          <Row label="Lecture" value={o.lecture_strategique} />
        </Card>
      ))}
    </Section>}
  </>;
}

/* ── Branding ─────────────────────────────────────────────────────────── */
function TabBranding({ d }) {
  const sm = d.social_media_decision;
  const contenu = d.strategie_contenu;
  return <>
    {sm && sm.best_platform && <Section title="Décision réseau social">
      <Card tone="priority">
        <p className="gv2-strat-hero-text">{esc(sm.best_platform)}</p>
        <Row label="Format" value={sm.best_content_format} />
        <Row label="Angle" value={sm.main_content_angle} />
        <Row label="Premier contenu à créer" value={sm.first_post_or_video_to_create} />
        <Row label="Priorité cette semaine" value={sm.posting_priority_this_week} />
      </Card>
    </Section>}
    {contenu && typeof contenu === 'object' && <Section title="Stratégie de contenu">
      <Card>
        <Row label="Format prioritaire" value={contenu.format_prioritaire} />
        <Row label="Fréquence" value={contenu.frequence} />
        <Row label="Tonalité" value={contenu.tonalite} />
        <Chips items={contenu.sujets_a_eviter} tone="neg" />
      </Card>
    </Section>}
  </>;
}

/* ── Plan d'action ────────────────────────────────────────────────────── */
function TabPlan({ d }) {
  const priorites = Array.isArray(d.recommandations_prioritaires) ? d.recommandations_prioritaires : [];
  const plan = d.plan_90_jours;
  const phases = plan && typeof plan === 'object'
    ? [['phase_1', 'Phase 1'], ['phase_2', 'Phase 2'], ['phase_3', 'Phase 3']].map(([key, label]) => [key, label, plan[key]]).filter(([, , ph]) => ph)
    : [];

  return <>
    {priorites.length > 0 && <Section title="Priorités, classées par impact">
      {priorites.map((r, i) => {
        const isObj = typeof r === 'object' && r;
        return <Card key={i}>
          <p className="gv2-strat-hero-text">{esc(isObj ? r.action : r)}</p>
          {isObj && <Row label="Signal" value={r.signal_source} />}
          {isObj && <Row label="Impact" value={r.impact} />}
          {isObj && <Row label="Délai" value={r.delai} />}
        </Card>;
      })}
    </Section>}

    {phases.length > 0 && <Section title="Plan d'action 90 jours">
      {phases.map(([key, label, ph]) => <Card key={key} title={ph.titre || label}>
        {ph.periode && <p className="gv2-strat-phase-period">{esc(ph.periode)}</p>}
        {Array.isArray(ph.objectifs) && ph.objectifs.length > 0 && <div className="gv2-strat-row"><span>Objectifs</span><ul>{ph.objectifs.map((o, i) => <li key={i}>{esc(o)}</li>)}</ul></div>}
        {Array.isArray(ph.taches) && ph.taches.length > 0 && <div className="gv2-strat-row"><span>Tâches</span><ul>{ph.taches.map((t, i) => <li key={i}>{esc(t)}</li>)}</ul></div>}
        {Array.isArray(ph.livrables) && ph.livrables.length > 0 && <div className="gv2-strat-row"><span>Livrables</span><ul>{ph.livrables.map((l, i) => <li key={i}>{esc(l)}</li>)}</ul></div>}
        <Chips items={ph.kpis} />
        {Array.isArray(ph.decisions_cles) && ph.decisions_cles.length > 0 && <div className="gv2-strat-row"><span>Décisions clés</span><ul>{ph.decisions_cles.map((dc, i) => <li key={i}>{esc(dc)}</li>)}</ul></div>}
      </Card>)}
    </Section>}
  </>;
}

/* ── Décision ─────────────────────────────────────────────────────────── */
function TabDecision({ d }) {
  const ed = d.executive_decision || {};
  const crit = d.critique_strategique;
  const stratConf = typeof ed.confidence_score === 'number' ? Math.round(ed.confidence_score * 100) : null;
  const critConf = crit && typeof crit.confidence_score_independant === 'number' ? Math.round(crit.confidence_score_independant * 100) : null;
  const risques = Array.isArray(d.risques) ? d.risques : [];
  const indicateurs = Array.isArray(d.indicateurs_succes) ? d.indicateurs_succes : [];
  const questions = Array.isArray(d.questions_a_clarifier) ? d.questions_a_clarifier : [];
  const verdict = (crit && crit.verdict || '').toLowerCase();
  const verdictLabel = verdict.includes('fragile') ? 'Fragile' : verdict.includes('ajust') ? 'À ajuster' : verdict ? 'Solide' : '';

  return <>
    {(stratConf !== null || critConf !== null) && <Section title="Deux lectures de la même décision"
      hint="L'écart entre les deux comptent plus que le premier chiffre seul.">
      <div className="gv2-strat-metrics">
        <Metric label="Score du Stratège" value={stratConf} suffix="%" />
        <Metric label="Relecture critique indépendante" value={critConf} suffix="%" />
      </div>
    </Section>}

    {crit && typeof crit === 'object' && (crit.point_faible_principal || crit.angle_contrarien) && (
      <Section title="Regard critique · 2ᵉ avis indépendant">
        <Card tone={verdict.includes('fragile') ? 'neg' : undefined}>
          {verdictLabel && <div className="gv2-strat-verdict">{verdictLabel}</div>}
          <Row label="Point faible principal" value={crit.point_faible_principal} />
          <Row label="Ce qu'un contrarien ferait" value={crit.angle_contrarien} />
          <Row label="Risque non couvert" value={crit.risque_non_couvert} />
          <Row label="Ajustement recommandé" value={crit.ajustement_recommande} />
        </Card>
      </Section>
    )}

    {risques.length > 0 && <Section title="Risques à surveiller">
      {risques.map((r, i) => {
        const isObj = typeof r === 'object' && r;
        return <Card key={i} tone="neg">
          <p>{esc(isObj ? r.risque : r)}</p>
          {isObj && r.mitigation && <Row label="Mitigation" value={r.mitigation} />}
        </Card>;
      })}
    </Section>}

    {indicateurs.length > 0 && <Section title="Indicateurs de succès"><Card><Chips items={indicateurs} /></Card></Section>}

    {questions.length > 0 && <Section title="Points à clarifier">
      <Card>{questions.map((q, i) => <p key={i} className="gv2-strat-question">{esc(q)}</p>)}</Card>
    </Section>}
  </>;
}

const SECTIONS = [
  { key: 'synthese', num: '01', label: 'Synthèse', Comp: TabSynthese },
  { key: 'marketing', num: '02', label: 'Marketing', Comp: TabMarketing },
  { key: 'branding', num: '03', label: 'Branding', Comp: TabBranding },
  { key: 'plan', num: '04', label: "Plan d'action", Comp: TabPlan },
  { key: 'decision', num: '05', label: 'Décision', Comp: TabDecision },
];

function downloadReport(strategy) {
  const blob = new Blob([JSON.stringify(strategy, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'strategie-gabriel.json';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

/* Rapport — document déroulant avec sommaire fixe (habillage « Ariane »).
   Mêmes cinq sections et mêmes données réelles que l'ancien tableau à
   onglets (TabSynthese…TabDecision, inchangés) : seule la présentation
   passe d'un aller-retour par clic à une lecture continue. */
function Report({ strategy, onGoToCreateur, onRestart }) {
  const [active, setActive] = useState(SECTIONS[0].key);
  const [scrollProgress, setScrollProgress] = useState(0);
  const containerRef = useRef(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    function onScroll() {
      const total = el.scrollHeight - el.clientHeight;
      setScrollProgress(total > 0 ? Math.min(100, Math.max(0, (el.scrollTop / total) * 100)) : 0);
    }
    onScroll();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(e => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (visible) setActive(visible.target.id.replace('gv2-ariane-report-', ''));
    }, { root: el, rootMargin: '-20% 0px -60% 0px', threshold: 0 });
    SECTIONS.forEach(s => {
      const node = el.querySelector(`#gv2-ariane-report-${s.key}`);
      if (node) observer.observe(node);
    });
    return () => observer.disconnect();
  }, []);

  return <div className="gv2-ariane-report" ref={containerRef}>
    <div className="gv2-ariane-report-progress"><div style={{ width: `${scrollProgress}%` }} /></div>
    <div className="gv2-ariane-report-wrap">
      <nav className="gv2-ariane-report-nav" aria-label="Sections de votre stratégie">
        <ul>
          {SECTIONS.map(s => <li key={s.key}>
            <a href={`#gv2-ariane-report-${s.key}`} className={active === s.key ? 'is-active' : ''}
              onClick={event => {
                event.preventDefault();
                containerRef.current?.querySelector(`#gv2-ariane-report-${s.key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }}>
              <span>{s.num}</span><span>{s.label}</span>
            </a>
          </li>)}
        </ul>
      </nav>
      <article className="gv2-ariane-report-article">
        <header className="gv2-ariane-report-header">
          <div>
            <span className="gv2-ariane-label" style={{ color: 'var(--muted)' }}>Ariane · Restitution</span>
            <h1>Votre stratégie</h1>
            <p>Diagnostic établi à partir de l'entretien stratégique conduit par Ariane.</p>
          </div>
          <div className="gv2-ariane-report-actions">
            <button type="button" onClick={() => downloadReport(strategy)}><Icon name="download" size={14} />Télécharger</button>
            {onRestart && <button type="button" onClick={onRestart}><Icon name="refresh" size={14} />Nouvelle analyse</button>}
          </div>
        </header>
        {SECTIONS.map(s => <section key={s.key} id={`gv2-ariane-report-${s.key}`} className="gv2-ariane-report-section">
          <div className="gv2-ariane-report-section-head"><span>{s.num}</span><h2>{s.label}</h2></div>
          <s.Comp d={strategy} />
        </section>)}
        {onGoToCreateur && <div className="gv2-ariane-report-to-createur">
          <button type="button" className="gv2-strat-to-createur" onClick={onGoToCreateur}>Le Créateur →</button>
        </div>}
      </article>
    </div>
  </div>;
}

function pause(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

/* Reprise du handoff écrit par PsychologueView.jsx avant de naviguer vers
   « stratege » (voir goToStratege) : {analysis_id, folder_id, psycho_brief,
   psycho_data}. N'existe que si l'utilisateur vient de cliquer « Stratège
   → » depuis une analyse — jamais lu ni écrit ailleurs. */
const PSYCHO_HANDOFF_MAX_AGE_MS = 10 * 60 * 1000;

function lireHandoffPsycho(activeFolderId) {
  try {
    const raw = window.sessionStorage.getItem('gabriel_for_stratege');
    if (!raw) return null;
    window.sessionStorage.removeItem('gabriel_for_stratege');
    const stored = JSON.parse(raw);
    const age = Date.now() - Number(stored?.created_at || 0);
    const valid = stored?.schema_version === 1
      && Boolean(stored.analysis_id)
      && Boolean(activeFolderId)
      && stored.folder_id === activeFolderId
      && age >= 0
      && age <= PSYCHO_HANDOFF_MAX_AGE_MS;
    return valid ? stored : null;
  } catch (_) { return null; }
}

function ChatMessage({ role, content, observation, hero }) {
  const isUser = role === 'user';
  const author = isUser ? 'Vous' : 'Ariane';
  if (hero) {
    return <div className="gv2-ariane-hero gv2-ariane-stream-in"><h1>{esc(content)}</h1></div>;
  }
  return <article className={`gv2-strat-msg gv2-strat-msg--${isUser ? 'user' : 'assistant'}`}>
    <header className="gv2-strat-msg-meta">
      <strong>{author}</strong>
    </header>
    {!isUser && observation && <aside className="gv2-strat-observation">
      <span>Observation stratégique</span>
      <p>{esc(observation)}</p>
    </aside>}
    <div className="gv2-strat-msg-body">{esc(content)}</div>
  </article>;
}

export function StrategeView({ workspace, onWorkspaceChange, onNavigateAgent, onInterviewChange }) {
  const [stage, setStage] = useState('loading'); // loading | need_analysis | need_profile | interview | generating | result | error
  const [strategy, setStrategy] = useState(null);
  const [activeStrategyId, setActiveStrategyId] = useState(workspace?.strategy_id || '');
  const [errorMsg, setErrorMsg] = useState('');
  const [missingFields, setMissingFields] = useState(null);
  const [progress, setProgress] = useState(0);
  const [messages, setMessages] = useState([]);
  const [contextProgress, setContextProgress] = useState(null);
  const [currentDimension, setCurrentDimension] = useState('');
  const [interviewReady, setInterviewReady] = useState(false);
  const [updatedContext, setUpdatedContext] = useState(null);
  const [interviewInput, setInterviewInput] = useState('');
  const [sending, setSending] = useState(false);
  const [psychoHandoff, setPsychoHandoff] = useState(null);

  /* Remonte l'état réel de l'entretien vers le panneau de contexte partagé
     (Progression/Historique, voir ContextPanel.jsx) — jamais un fait recalculé
     ou deviné là-bas, seulement ce que le serveur a renvoyé ici même. */
  useEffect(() => {
    onInterviewChange?.({ contextProgress, currentDimension, interviewReady, messages });
  }, [onInterviewChange, contextProgress, currentDimension, interviewReady, messages]);

  /* Couche vocale (Tranche C) — même patron que la dictée du composeur
     principal (Conversation.jsx:311-421), pas réinventé : reconnaissance du
     navigateur en priorité (gratuite, résultat immédiat dans le champ),
     repli sur MediaRecorder + /voice/transcribe (ElevenLabs) si le
     navigateur n'a pas SpeechRecognition (Firefox notamment). Contrairement
     à l'ancienne page, pas de sous-titrage plein écran séparé du texte
     réellement envoyé : le texte reconnu devient directement la réponse,
     modifiable avant l'envoi — plus simple, même résultat fonctionnel. */
  const [isRecording, setIsRecording] = useState(false);
  const [voiceError, setVoiceError] = useState('');
  const [voiceMode, setVoiceMode] = useState(false);
  const [voiceId, setVoiceId] = useState('');
  const [voices, setVoices] = useState(null);
  const [speaking, setSpeaking] = useState(false);
  const [speechPaused, setSpeechPaused] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const speechRecognitionRef = useRef(null);
  const speechBaseRef = useRef('');
  const speechFinalRef = useRef('');
  const speechHeardRef = useRef(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioStreamRef = useRef(null);
  const audioElRef = useRef(null);
  const aliveRef = useRef(true);
  const pollingRef = useRef(false);
  const chatEndRef = useRef(null);

  useEffect(() => { aliveRef.current = true; return () => { aliveRef.current = false; }; }, []);
  useEffect(() => {
    if (!workspace?.folder_id) return;
    setPsychoHandoff(lireHandoffPsycho(workspace.folder_id));
  }, [workspace?.folder_id]);

  useEffect(() => { setActiveStrategyId(workspace?.strategy_id || ''); }, [workspace?.strategy_id]);

  useEffect(() => {
    try {
      setVoiceMode(window.localStorage.getItem(VOICE_MODE_KEY) === '1');
      setVoiceId(window.localStorage.getItem(VOICE_ID_KEY) || '');
    } catch (_) { /* localStorage indisponible (navigation privée) */ }
  }, []);

  useEffect(() => () => {
    const recognition = speechRecognitionRef.current;
    if (recognition) { try { recognition.abort(); } catch (_) { /* déjà terminée */ } }
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    audioStreamRef.current?.getTracks().forEach(track => track.stop());
    audioElRef.current?.pause();
  }, []);

  /* Le catalogue des voix doit se charger dès que le mode vocal est actif —
     pas seulement au clic qui l'active. Un mode vocal déjà activé lors
     d'une session précédente (repris via localStorage à l'ouverture) doit
     lui aussi proposer le sélecteur ; sans cet effet séparé, la lecture
     fonctionnait déjà correctement (elle ne dépend que de voiceMode), mais
     le sélecteur de voix restait invisible tant qu'on ne rebasculait pas
     manuellement — trouvé en testant réellement une session reprise. */
  useEffect(() => {
    if (voiceMode && voices === null) {
      fetchV2('/voice/voices').then(async response => {
        const payload = await readApiPayload(response, 'Les voix disponibles').catch(() => null);
        setVoices(payload?.available ? (payload.voices || []) : []);
      }).catch(() => setVoices([]));
    }
  }, [voiceMode, voices]);

  /* Minuteur d'écoute — purement d'affichage, dérivé du vrai isRecording
     (pas une valeur simulée : il compte le temps réellement écoulé). */
  useEffect(() => {
    if (!isRecording) { setRecordingSeconds(0); return undefined; }
    const id = window.setInterval(() => setRecordingSeconds(s => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [isRecording]);

  function pauseSpeech() {
    audioElRef.current?.pause();
    setSpeechPaused(true);
  }
  function resumeSpeech() {
    audioElRef.current?.play().catch(() => {});
    setSpeechPaused(false);
  }
  function replaySpeech() {
    const audio = audioElRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    audio.play().catch(() => {});
    setSpeechPaused(false);
  }

  function toggleVoiceMode() {
    setVoiceMode(current => {
      const next = !current;
      try { window.localStorage.setItem(VOICE_MODE_KEY, next ? '1' : '0'); } catch (_) {}
      return next;
    });
  }

  function changerVoix(id) {
    setVoiceId(id);
    try { window.localStorage.setItem(VOICE_ID_KEY, id); } catch (_) {}
  }

  async function lire(texte, pace) {
    if (!texte || !voiceMode) return;
    try {
      const response = await fetchV2('/voice/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: texte, voice_id: voiceId || undefined, pace: pace || undefined }),
      });
      if (!response.ok) return; // le mode vocal reste actif, silencieux sur cette réponse
      const blob = await response.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audioElRef.current = audio;
      audio.onplay = () => { setSpeaking(true); setSpeechPaused(false); };
      audio.onended = () => { setSpeaking(false); setSpeechPaused(false); };
      audio.onerror = () => { setSpeaking(false); setSpeechPaused(false); };
      await audio.play();
    } catch (_) { setSpeaking(false); }
  }

  function mergeDictation(base, transcript) {
    const spoken = String(transcript || '').trim();
    if (!spoken) return base;
    return `${base}${base && !/\s$/.test(base) ? ' ' : ''}${spoken}`;
  }

  function startBrowserDictation(SpeechRecognition) {
    const recognition = new SpeechRecognition();
    speechBaseRef.current = interviewInput;
    speechFinalRef.current = '';
    speechHeardRef.current = false;
    recognition.lang = 'fr-FR';
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setIsRecording(true);
    recognition.onresult = event => {
      let interim = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = event.results[index]?.[0]?.transcript || '';
        if (event.results[index].isFinal) speechFinalRef.current += `${transcript} `;
        else interim += transcript;
      }
      const spoken = `${speechFinalRef.current}${interim}`.trim();
      if (!spoken) return;
      speechHeardRef.current = true;
      setInterviewInput(mergeDictation(speechBaseRef.current, spoken));
    };
    recognition.onerror = event => {
      const message = {
        'not-allowed': 'Autorisez le microphone dans votre navigateur pour utiliser la dictée.',
        'service-not-allowed': 'La reconnaissance vocale est bloquée par votre navigateur.',
        'audio-capture': 'Aucun microphone n’a été détecté.',
        network: 'La reconnaissance vocale nécessite une connexion internet.',
      }[event.error] || (event.error === 'no-speech' ? 'Je ne vous ai pas entendu. Réessayez en parlant un peu plus près du micro.' : 'La dictée a été interrompue. Réessayez dans un instant.');
      setVoiceError(message);
    };
    recognition.onend = () => {
      if (speechRecognitionRef.current === recognition) speechRecognitionRef.current = null;
      setIsRecording(false);
      if (!speechHeardRef.current) setVoiceError(current => current || 'Je ne vous ai pas entendu. Vérifiez votre microphone puis réessayez.');
    };
    speechRecognitionRef.current = recognition;
    try {
      recognition.start();
    } catch (_) {
      speechRecognitionRef.current = null;
      setVoiceError('La dictée ne peut pas démarrer. Réessayez dans un instant.');
    }
  }

  async function startServerDictation() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceError('La dictée n’est pas disponible dans ce navigateur. Utilisez une version récente de Chrome, Edge ou Safari.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(type => window.MediaRecorder.isTypeSupported?.(type));
      const recorder = preferredMimeType ? new MediaRecorder(stream, { mimeType: preferredMimeType }) : new MediaRecorder(stream);
      audioStreamRef.current = stream;
      audioChunksRef.current = [];
      recorder.ondataavailable = event => { if (event.data?.size) audioChunksRef.current.push(event.data); };
      recorder.onerror = () => { setIsRecording(false); setVoiceError('La dictée a été interrompue. Réessayez dans un instant.'); };
      recorder.onstop = async () => {
        const mimeType = recorder.mimeType || 'audio/webm';
        const audio = new Blob(audioChunksRef.current, { type: mimeType });
        audioStreamRef.current?.getTracks().forEach(track => track.stop());
        audioStreamRef.current = null;
        mediaRecorderRef.current = null;
        setIsRecording(false);
        if (!audio.size) return;
        const form = new FormData();
        form.append('audio', audio, `dictee-gabriel.${mimeType.includes('mp4') ? 'm4a' : 'webm'}`);
        try {
          const response = await fetchV2('/voice/transcribe', { method: 'POST', body: form });
          if (isLoginResponse(response)) { window.location.assign('/login'); return; }
          const payload = await readApiPayload(response, 'Le service de dictée');
          if (!response.ok || !payload?.text) throw new Error(response.status === 503 ? 'La transcription serveur n’est pas disponible. Essayez depuis Chrome pour utiliser la dictée intégrée.' : (payload?.error || 'La transcription est indisponible.'));
          setInterviewInput(current => `${current}${current && !/\s$/.test(current) ? ' ' : ''}${String(payload.text).trim()}`);
        } catch (error) {
          setVoiceError(error.message || 'La transcription est indisponible.');
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start(250);
      setIsRecording(true);
    } catch (error) {
      setVoiceError(error?.name === 'NotAllowedError' ? 'Autorisez le microphone dans votre navigateur pour utiliser la dictée.' : 'Le microphone est indisponible. Vérifiez qu’il est connecté puis réessayez.');
    }
  }

  function toggleDictation() {
    setVoiceError('');
    const activeRecognition = speechRecognitionRef.current;
    if (activeRecognition) { try { activeRecognition.stop(); } catch (_) {} return; }
    const activeRecorder = mediaRecorderRef.current;
    if (activeRecorder && activeRecorder.state !== 'inactive') { activeRecorder.stop(); return; }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) { startBrowserDictation(SpeechRecognition); return; }
    void startServerDictation();
  }

  useEffect(() => {
    let vivant = true;
    async function bootstrap() {
      if (!workspace) { setStage('interview'); return; }
      if (workspace.strategy_id) {
        setStage('loading');
        try {
          const response = await fetchV2(`/strategies/${encodeURIComponent(workspace.strategy_id)}`);
          if (isLoginResponse(response)) { window.location.assign('/login'); return; }
          const payload = await readApiPayload(response, 'La stratégie');
          if (!vivant) return;
          if (response.ok && payload?.success) {
            setActiveStrategyId(workspace.strategy_id);
            setStrategy(payload.strategy_result || {}); setStage('result'); return;
          }
        } catch (_) { /* on retombe sur les autres déclencheurs */ }
      }
      if (!vivant) return;
      if (workspace.analysis_id) { setStage('need_analysis'); return; }
      setStage('interview');
    }
    bootstrap();
    return () => { vivant = false; };
  }, [workspace?.folder_id, workspace?.strategy_id, workspace?.analysis_id]);

  useEffect(() => {
    if (stage !== 'interview' || messages.length > 0) return;
    let vivant = true;
    (async () => {
      try {
        const response = await fetchV2(`/business-context?folder_id=${encodeURIComponent(workspace?.folder_id || '')}`);
        if (isLoginResponse(response)) { window.location.assign('/login'); return; }
        const payload = await readApiPayload(response, 'L’entretien stratégique');
        if (!vivant) return;
        setMessages(Array.isArray(payload.messages) ? payload.messages : []);
        setContextProgress(payload.context_progress || null);
        setCurrentDimension(payload.current_dimension || '');
        setInterviewReady(Boolean(payload.is_ready));
        setUpdatedContext(payload.updated_context || {});
      } catch (_) {
        if (vivant) setMessages([{ role: 'assistant', content: 'Parlez-moi de votre entreprise — je pose une question à la fois.' }]);
      }
    })();
    return () => { vivant = false; };
  }, [stage, workspace?.folder_id]);

  /* À chaque réponse, le fil garde naturellement le dernier échange visible.
     Le défilement reste local au contenu : il ne déplace ni la navigation ni
     le panneau de contexte. */
  useEffect(() => {
    if (stage !== 'interview' || !messages.length) return;
    const revealLastMessage = () => chatEndRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
    if (typeof window.requestAnimationFrame === 'function') {
      const frame = window.requestAnimationFrame(revealLastMessage);
      return () => window.cancelAnimationFrame?.(frame);
    }
    revealLastMessage();
    return undefined;
  }, [stage, messages.length, sending]);

  async function envoyerReponse() {
    const message = interviewInput.trim();
    if (!message || sending) return;
    setSending(true); setInterviewInput('');
    setMessages(current => [...current, { role: 'user', content: message }]);
    try {
      const response = await fetchV2('/context-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const payload = await readApiPayload(response, 'L’entretien stratégique');
      if (payload?.error) { setMessages(current => [...current, { role: 'assistant', content: payload.error }]); return; }
      const texte = payload.reply?.display_text || (typeof payload.reply === 'string' ? payload.reply : '');
      if (texte) setMessages(current => [...current, {
        role: 'assistant',
        content: texte,
        observation: payload.reply?.strategic_observation || '',
      }]);
      const aLire = payload.reply?.speech_text || texte;
      lire(aLire, payload.reply?.speech_profile?.pace);
      setContextProgress(payload.context_progress || null);
      setCurrentDimension(payload.current_dimension || '');
      setInterviewReady(Boolean(payload.is_ready));
      setUpdatedContext(payload.updated_context || {});
    } catch (_) {
      setMessages(current => [...current, { role: 'assistant', content: 'Erreur réseau — réessayez.' }]);
    } finally {
      setSending(false);
    }
  }

  async function pollStrategize(jobId) {
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      for (let attempt = 0; attempt < 160; attempt += 1) {
        await pause(3000);
        if (!aliveRef.current) return;
        const response = await fetchV2(`/status/${encodeURIComponent(jobId)}`);
        if (isLoginResponse(response)) { window.location.assign('/login'); return; }
        const payload = await readApiPayload(response, 'Le suivi de la stratégie');
        if (payload.status === 'done') {
          const jobResult = payload.data || {};
          const strategyResult = jobResult.data?.strategie || jobResult;
          setActiveStrategyId(jobResult.strategy_id || jobResult.data?.strategy_id || '');
          setStrategy(strategyResult); setStage('result');
          await onWorkspaceChange?.();
          return;
        }
        if (['error', 'interrupted', 'not_found'].includes(payload.status)) {
          throw new Error(payload.error || 'La génération a été interrompue.');
        }
        setProgress(Math.min(95, Math.round(((attempt + 1) / 160) * 100)));
      }
      throw new Error('La génération prend plus de temps que prévu.');
    } catch (error) {
      if (!aliveRef.current) return;
      setStage('error'); setErrorMsg(error.message || 'Une erreur est survenue.');
    } finally {
      pollingRef.current = false;
    }
  }

  const dernierDeclencheurRef = useRef(null); // 'classique' | 'entretien' — pour le bouton Réessayer

  /* Deux formes de réponse possibles selon le flux emprunté côté serveur
     (app.py:/strategize) : un job_id à suivre (flux classique, asynchrone,
     même mécanisme que pollStrategize), ou — quand un entretien seul sans
     analyse liée aboutit — la stratégie renvoyée directement, de façon
     synchrone. Les deux sont légitimes, pas une erreur à normaliser. */
  async function lancerGeneration(payload) {
    setStage('generating'); setProgress(0); setErrorMsg(''); setMissingFields(null);
    try {
      const response = await fetchV2('/strategize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const body = await readApiPayload(response, 'La génération de la stratégie');
      if (response.status === 402 || body?.error === 'credits_insufficient') {
        setStage('error'); setErrorMsg(`Il vous faut ${body.cost} crédits pour une stratégie — il vous en reste ${body.credits}.`);
        return;
      }
      if (body?.missing_fields) {
        setMissingFields(body.missing_fields); setStage('need_profile');
        return;
      }
      if (body?.error) { setStage('error'); setErrorMsg(body.error); return; }
      if (body?.job_id) { await pollStrategize(body.job_id); return; }
      if (body?.success) {
        setActiveStrategyId(body.strategy_id || '');
        setStrategy(body); setStage('result'); await onWorkspaceChange?.(); return;
      }
      setStage('error'); setErrorMsg('Réponse inattendue du serveur.');
    } catch (error) {
      setStage('error'); setErrorMsg(error.message || 'Erreur réseau. Réessayez.');
    }
  }

  function generer() {
    dernierDeclencheurRef.current = 'classique';
    lancerGeneration({ analysis_id: workspace.analysis_id, folder_id: workspace.folder_id });
  }

  /* Une analyse Psychologue liée (bannière acceptée) fait basculer côté
     serveur sur le flux classique plutôt que Context Builder — même
     logique que l'ancienne page (_linkedAnalysisId) : le contexte de
     l'entretien enrichit alors brain_profile au lieu de context. */
  function genererDepuisEntretien() {
    dernierDeclencheurRef.current = 'entretien';
    const payload = psychoHandoff
      ? { analysis_id: psychoHandoff.analysis_id, brain_profile: updatedContext, folder_id: workspace?.folder_id }
      : { context: updatedContext, psycho_summary: psychoHandoff?.psycho_brief || '', folder_id: workspace?.folder_id };
    lancerGeneration(payload);
  }

  function reessayer() {
    if (dernierDeclencheurRef.current === 'entretien') genererDepuisEntretien();
    else generer();
  }

  if (stage === 'loading') {
    return <div className="gv2-strat-empty"><p>Chargement…</p></div>;
  }

  if (stage === 'need_analysis') {
    return <div className="gv2-strat-empty">
      <h2>Une analyse est disponible pour ce dossier</h2>
      <p>Gabriel peut générer une stratégie à partir de l'analyse d'audience déjà réalisée et de votre profil business.</p>
      <button type="button" onClick={generer}>Générer la stratégie</button>
      <button type="button" className="gv2-strat-secondary" onClick={() => setStage('interview')}>Ou décrivez-moi votre activité maintenant</button>
    </div>;
  }

  if (stage === 'need_profile') {
    return <div className="gv2-strat-empty">
      <h2>Votre profil business est incomplet</h2>
      <p>Gabriel a besoin de ces informations pour générer une stratégie fiable :</p>
      <ul className="gv2-strat-missing">{(missingFields || []).map(f => <li key={f.field}>{f.label}</li>)}</ul>
      <a href="/orchestrateur?section=settings">Compléter mon profil business</a>
      <button type="button" className="gv2-strat-secondary" onClick={() => setStage('interview')}>Ou décrivez-moi votre activité maintenant</button>
    </div>;
  }

  if (stage === 'generating') {
    const phases = ['Synthèse', 'Diagnostic', 'Priorités', "Plan d'action"];
    const phase = phases[Math.min(phases.length - 1, Math.floor((progress / 100) * phases.length))];
    return <div className="gv2-ariane-generating">
      <svg viewBox="0 0 240 60" aria-hidden="true">
        <line x1="4" y1="30" x2="236" y2="30" className="gv2-ariane-generating-line" />
        <line x1="4" y1="30" x2="236" y2="30" className="gv2-ariane-generating-line--fill" style={{ strokeDashoffset: 240 - (progress / 100) * 240 }} />
        {[60, 120, 180].map(x => <circle key={x} cx={x} cy="30" r="2" fill="var(--strategist-slate)" />)}
        <circle cx="4" cy="30" r="3" fill="var(--ink)" />
      </svg>
      <h2>Ariane structure votre stratégie</h2>
      <p key={phase} className="gv2-ariane-label gv2-ariane-generating-phase gv2-ariane-stream-in" aria-live="polite">
        {phase}<span className="gv2-ariane-caret">_</span>
      </p>
    </div>;
  }

  if (stage === 'error') {
    return <div className="gv2-strat-empty">
      <h2>Un problème est survenu</h2>
      <p>{errorMsg}</p>
      <button type="button" onClick={reessayer}>Réessayer</button>
    </div>;
  }

  if (stage === 'interview') {
    const dicteeDisponible = typeof window !== 'undefined'
      && (window.SpeechRecognition || window.webkitSpeechRecognition || (navigator.mediaDevices?.getUserMedia && window.MediaRecorder));
    const hasUserReply = messages.some(message => message.role === 'user');
    const voiceCardState = isRecording ? 'listening' : voiceError ? 'error' : speaking ? 'speaking' : null;
    return <div className={`gv2-strat-interview${hasUserReply ? ' has-replies' : ' is-opening'}`}>
      {psychoHandoff && <div className="gv2-strat-banner">Analyse Psychologue détectée — elle sera prise en compte dans la stratégie.</div>}
      <div className="gv2-strat-chat" role="log" aria-live="polite" aria-label="Conversation avec Ariane">
        {messages.map((m, i) => <ChatMessage key={i} role={m.role} content={m.content} observation={m.observation || m.strategic_observation}
          hero={!hasUserReply && i === 0 && m.role !== 'user'} />)}
        {sending && <article className="gv2-strat-msg gv2-strat-msg--assistant is-thinking"><span>Ariane structure votre réponse…</span></article>}

        {!hasUserReply && dicteeDisponible && !voiceCardState && <div className="gv2-ariane-hero-actions">
          <button type="button" className="gv2-ariane-hero-cta" onClick={toggleDictation}>Commencer l'entretien à la voix</button>
        </div>}

        {voiceCardState === 'listening' && <div className="gv2-ariane-voice-card gv2-ariane-stream-in">
          <div className="gv2-ariane-voice-head">
            <span className="gv2-ariane-label" style={{ color: 'var(--strategist-slate)' }}>Ariane · Écoute</span>
            <span className="gv2-ariane-voice-timer">{formatTimer(recordingSeconds)}</span>
          </div>
          <Waveform active />
          <p className={`gv2-ariane-voice-transcript${interviewInput ? '' : ' is-empty'}`}>
            {interviewInput || 'Parlez, je transcris au fil de l\'eau…'}
            <span className="gv2-ariane-caret">▍</span>
          </p>
          <div className="gv2-ariane-voice-actions">
            <button type="button" className="gv2-ariane-voice-btn gv2-ariane-voice-btn--primary" onClick={toggleDictation}>Terminer</button>
            <button type="button" className="gv2-ariane-voice-btn" onClick={() => { toggleDictation(); setInterviewInput(''); }}>Annuler</button>
          </div>
        </div>}

        {voiceCardState === 'error' && <div className="gv2-ariane-voice-card is-error gv2-ariane-stream-in">
          <span className="gv2-ariane-label gv2-ariane-voice-eyebrow--error">Ariane · Micro indisponible</span>
          <p className="gv2-ariane-voice-transcript" style={{ marginTop: 10 }}>{voiceError}</p>
          <div className="gv2-ariane-voice-actions">
            <button type="button" className="gv2-ariane-voice-btn" onClick={toggleDictation}>Réessayer le micro</button>
            <button type="button" className="gv2-ariane-voice-btn gv2-ariane-voice-btn--primary" onClick={() => setVoiceError('')}>Continuer par écrit</button>
          </div>
        </div>}

        {voiceCardState === 'speaking' && <div className="gv2-ariane-voice-card gv2-ariane-stream-in">
          <div className="gv2-ariane-voice-head">
            <span className="gv2-ariane-label gv2-ariane-voice-eyebrow--speaking">Ariane vous répond</span>
            <Icon name="volume" size={16} />
          </div>
          <Waveform active={!speechPaused} minimal />
          <div className="gv2-ariane-voice-actions">
            <button type="button" className="gv2-ariane-voice-btn" onClick={speechPaused ? resumeSpeech : pauseSpeech}>
              <Icon name={speechPaused ? 'play' : 'pause'} size={12} />{speechPaused ? 'Reprendre' : 'Pause'}
            </button>
            <button type="button" className="gv2-ariane-voice-btn" onClick={replaySpeech}><Icon name="refresh" size={12} />Réécouter</button>
          </div>
        </div>}

        {interviewReady && <div className="gv2-ariane-ready gv2-ariane-stream-in">
          <p>Votre situation est suffisamment claire. Ariane peut maintenant produire votre diagnostic.</p>
          <button type="button" className="gv2-ariane-ready-cta" onClick={genererDepuisEntretien}>Générer mon diagnostic stratégique →</button>
        </div>}

        <div ref={chatEndRef} aria-hidden="true" />
      </div>
      <div className="gv2-strat-composer-zone">
        <div className="gv2-strat-composer-tools">
          <button type="button" className={`gv2-strat-voice-toggle${voiceMode ? ' is-active' : ''}`} onClick={toggleVoiceMode}
            aria-pressed={voiceMode} title="Gabriel lit ses réponses à voix haute">
            <span className="gv2-strat-voice-dot" />Mode vocal
          </button>
          {voiceMode && voices && voices.length > 0 && (
            <select className="gv2-strat-voice-picker" value={voiceId} onChange={event => changerVoix(event.target.value)} aria-label="Voix de Gabriel">
              <option value="">Voix par défaut</option>
              {voices.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          )}
        </div>
        <div className="gv2-strat-composer">
          {dicteeDisponible && <button type="button" className={`gv2-strat-mic${isRecording ? ' is-recording' : ''}`}
            onClick={toggleDictation} disabled={sending} aria-label={isRecording ? 'Arrêter la dictée' : 'Répondre à la voix'} title="Parler">
            <Icon name={isRecording ? 'square' : 'mic'} size={isRecording ? 12 : 16} />
          </button>}
          <textarea rows={1} value={interviewInput} placeholder={voiceCardState === 'listening' ? 'Micro actif…' : 'Écrivez votre réponse…'} disabled={sending || voiceCardState === 'listening'}
            onChange={event => setInterviewInput(event.target.value)}
            onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); envoyerReponse(); } }} />
          <button type="button" className="gv2-strat-send" disabled={sending || !interviewInput.trim()} onClick={envoyerReponse} aria-label="Envoyer">Envoyer</button>
        </div>
        <p className="gv2-strat-composer-hint">Entrée pour envoyer <span>·</span> Maj + Entrée pour un saut de ligne</p>
      </div>
    </div>;
  }

  return <Report strategy={strategy || {}} onGoToCreateur={activeStrategyId ? () => onNavigateAgent?.('createur', {
    source: 'stratege', folder_id: workspace?.folder_id, strategy_id: activeStrategyId,
  }) : undefined} onRestart={() => { setStrategy(null); setMessages([]); setContextProgress(null); setInterviewReady(false); setStage('interview'); }} />;
}
