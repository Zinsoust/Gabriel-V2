import React, { useEffect, useRef, useState } from 'react';
import { Icon } from '../icons.jsx';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

/* ── StrategeView — Tranche A ─────────────────────────────────────────────
   Réimplémentation native (React) de l'agent Le Stratège, jusqu'ici
   encapsulé en <iframe> depuis templates/stratege.html (voir
   AgentWorkspace.jsx). Même contrat API — /strategize, /status/<jobId>,
   /strategies/<id>, /strategy_chat — aucun changement backend.

   Cette tranche couvre : la reprise d'une stratégie déjà enregistrée
   (workspace.strategy_id), la génération classique à partir d'une analyse
   Psychologue existante (workspace.analysis_id → /strategize → /status),
   et le tableau de bord à 5 onglets (Synthèse, Marketing, Branding, Plan
   d'action, Décision).

   Restent hors périmètre de cette tranche, par construction : l'entretien
   conversationnel qui construit le contexte business depuis zéro
   (/context-chat, 12 états d'entretien) et la couche vocale (micro,
   ElevenLabs). Sans l'un des deux déclencheurs ci-dessus, l'écran l'indique
   honnêtement plutôt que de simuler un entretien qui n'existe pas encore.

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

const TABS = [
  { key: 'synthese', label: 'Synthèse', Comp: TabSynthese },
  { key: 'marketing', label: 'Marketing', Comp: TabMarketing },
  { key: 'branding', label: 'Branding', Comp: TabBranding },
  { key: 'plan', label: "Plan d'action", Comp: TabPlan },
  { key: 'decision', label: 'Décision', Comp: TabDecision },
];

function Dashboard({ strategy, onGoToCreateur }) {
  const [tab, setTab] = useState('synthese');
  const active = TABS.find(t => t.key === tab) || TABS[0];
  return <div className="gv2-strat-dashboard">
    <div className="gv2-strat-tabs" role="tablist">
      {TABS.map(t => <button key={t.key} type="button" role="tab" aria-selected={t.key === tab}
        className={t.key === tab ? 'is-active' : ''} onClick={() => setTab(t.key)}>{t.label}</button>)}
    </div>
    <div className="gv2-strat-panel" role="tabpanel"><active.Comp d={strategy} /></div>
    {onGoToCreateur && <button type="button" className="gv2-strat-to-createur" onClick={onGoToCreateur}>Le Créateur →</button>}
  </div>;
}

function pause(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

export function StrategeView({ workspace, onWorkspaceChange, onNavigateAgent }) {
  const [stage, setStage] = useState('loading'); // loading | need_analysis | no_context | generating | result | error
  const [strategy, setStrategy] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [missingFields, setMissingFields] = useState(null);
  const [progress, setProgress] = useState(0);
  const aliveRef = useRef(true);
  const pollingRef = useRef(false);

  useEffect(() => { aliveRef.current = true; return () => { aliveRef.current = false; }; }, []);

  useEffect(() => {
    let vivant = true;
    async function bootstrap() {
      if (!workspace) { setStage('no_context'); return; }
      if (workspace.strategy_id) {
        setStage('loading');
        try {
          const response = await fetchV2(`/strategies/${encodeURIComponent(workspace.strategy_id)}`);
          if (isLoginResponse(response)) { window.location.assign('/login'); return; }
          const payload = await readApiPayload(response, 'La stratégie');
          if (!vivant) return;
          if (response.ok && payload?.success) { setStrategy(payload.strategy_result || {}); setStage('result'); return; }
        } catch (_) { /* on retombe sur les autres déclencheurs */ }
      }
      if (!vivant) return;
      if (workspace.analysis_id) { setStage('need_analysis'); return; }
      setStage('no_context');
    }
    bootstrap();
    return () => { vivant = false; };
  }, [workspace?.folder_id, workspace?.strategy_id, workspace?.analysis_id]);

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

  async function generer() {
    setStage('generating'); setProgress(0); setErrorMsg(''); setMissingFields(null);
    try {
      const response = await fetchV2('/strategize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analysis_id: workspace.analysis_id, folder_id: workspace.folder_id }),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const payload = await readApiPayload(response, 'La génération de la stratégie');
      if (response.status === 402 || payload?.error === 'credits_insufficient') {
        setStage('error'); setErrorMsg(`Il vous faut ${payload.cost} crédits pour une stratégie — il vous en reste ${payload.credits}.`);
        return;
      }
      if (payload?.missing_fields) {
        setMissingFields(payload.missing_fields); setStage('need_profile');
        return;
      }
      if (payload?.error) { setStage('error'); setErrorMsg(payload.error); return; }
      if (payload?.job_id) { await pollStrategize(payload.job_id); return; }
      setStage('error'); setErrorMsg('Réponse inattendue du serveur.');
    } catch (error) {
      setStage('error'); setErrorMsg(error.message || 'Erreur réseau. Réessayez.');
    }
  }

  if (stage === 'loading') {
    return <div className="gv2-strat-empty"><p>Chargement…</p></div>;
  }

  if (stage === 'no_context') {
    return <div className="gv2-strat-empty">
      <h2>Aucune analyse liée à ce dossier</h2>
      <p>Le Stratège construit sa décision à partir d'une analyse d'audience. Lancez d'abord Le Psychologue sur ce dossier, puis revenez ici.</p>
      <button type="button" onClick={() => onNavigateAgent?.('psychologue')}>Ouvrir Le Psychologue</button>
    </div>;
  }

  if (stage === 'need_analysis') {
    return <div className="gv2-strat-empty">
      <h2>Une analyse est disponible pour ce dossier</h2>
      <p>Gabriel peut générer une stratégie à partir de l'analyse d'audience déjà réalisée et de votre profil business.</p>
      <button type="button" onClick={generer}>Générer la stratégie</button>
    </div>;
  }

  if (stage === 'need_profile') {
    return <div className="gv2-strat-empty">
      <h2>Votre profil business est incomplet</h2>
      <p>Gabriel a besoin de ces informations pour générer une stratégie fiable :</p>
      <ul className="gv2-strat-missing">{(missingFields || []).map(f => <li key={f.field}>{f.label}</li>)}</ul>
      <a href="/orchestrateur?section=settings">Compléter mon profil business</a>
    </div>;
  }

  if (stage === 'generating') {
    return <div className="gv2-strat-empty">
      <h2>Gabriel construit votre stratégie…</h2>
      <div className="gv2-strat-progress-track"><div className="gv2-strat-progress-fill" style={{ width: `${progress}%` }} /></div>
    </div>;
  }

  if (stage === 'error') {
    return <div className="gv2-strat-empty">
      <h2>Un problème est survenu</h2>
      <p>{errorMsg}</p>
      {workspace?.analysis_id && <button type="button" onClick={generer}>Réessayer</button>}
    </div>;
  }

  return <Dashboard strategy={strategy || {}} onGoToCreateur={() => onNavigateAgent?.('createur')} />;
}
