import React, { useEffect, useRef, useState } from 'react';
import { Icon } from '../icons.jsx';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

/* ── PsychologueView ────────────────────────────────────────────────────
   Réimplémentation native (React) de l'agent Le Psychologue, jusqu'ici
   encapsulé en <iframe> depuis templates/psychologue.html (voir
   AgentWorkspace.jsx). Même contrat API que la page classique — /analyze,
   /status/<jobId>, /api/v2/agents/psychologue/cross-analyses* — aucun
   changement backend nécessaire.

   Périmètre couvert : saisie YouTube/manuel, lancement + suivi de
   l'analyse simple, tableau de résultat (synthèse, stats, émotions,
   positions, personas), et la Cross Analyse complète (panneau flottant
   2-5 vidéos + écran de résultat : conclusion générale, vidéos comparées,
   convergences/divergences/oppositions, personas croisés, détails
   techniques). Restent hors périmètre : quelques sections secondaires du
   dashboard classique (démographie, résonance argumentative,
   moquerie/ironie, champs lexicaux) — non portées pour garder ce jalon
   vérifiable de bout en bout plutôt que de tout faire à moitié. */

const PENDING_JOB_KEY = 'gabriel_pending_job';

// Contrat repris de la page historique : ces trois plateformes ont une vraie
// collecte de commentaires. Google est annoncé mais pas encore connecté ;
// « Autre source » bascule simplement vers la saisie manuelle.
const LINK_SOURCES = {
  youtube: { label: 'YouTube', mark: '▶', placeholder: 'Collez le lien de la vidéo YouTube ici…', example: 'Exemple : youtube.com/watch?v=…' },
  instagram: { label: 'Instagram', mark: '◎', placeholder: 'Collez le lien de la publication Instagram ici…', example: 'Exemple : instagram.com/reel/…' },
  tiktok: { label: 'TikTok', mark: '♪', placeholder: 'Collez le lien de la vidéo TikTok ici…', example: 'Exemple : tiktok.com/@compte/video/…' },
};
const CROSS_MIN_SOURCES = 2;
const CROSS_MAX_SOURCES = 5;

function pause(ms) {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

function esc(value) {
  return String(value ?? '');
}

// Le texte long généré par le LLM (executive_summary, noyau psychologique,
// descriptions de persona) utilise du markdown gras/italique léger.
function formatInline(value) {
  const text = esc(value);
  const chunks = text.split(/(\*\*[^*\n]+?\*\*|\*[^*\n]+?\*)/g);
  return chunks.map((chunk, index) => {
    if (/^\*\*[^*]+\*\*$/.test(chunk)) return <strong key={index}>{chunk.slice(2, -2)}</strong>;
    if (/^\*[^*]+\*$/.test(chunk)) return <em key={index}>{chunk.slice(1, -1)}</em>;
    return chunk;
  });
}

function fmtCount(value) {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  if (n >= 1000000) return (n / 1000000).toFixed(n % 1000000 === 0 ? 0 : 1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(n % 1000 === 0 ? 0 : 1) + 'k';
  return String(n);
}

function fmtDuration(iso) {
  if (!iso || typeof iso !== 'string') return null;
  const m = iso.match(/^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/);
  if (!m || (!m[1] && !m[2] && !m[3])) return null;
  const h = parseInt(m[1] || '0', 10), mi = parseInt(m[2] || '0', 10), s = parseInt(m[3] || '0', 10);
  const pad = v => String(v).padStart(2, '0');
  return h > 0 ? `${h}:${pad(mi)}:${pad(s)}` : `${mi}:${pad(s)}`;
}

const QUALITY_META = {
  strong: { cls: 'is-strong', label: 'Solide' },
  moderate: { cls: 'is-moderate', label: 'Modérée' },
  exploratory: { cls: 'is-exploratory', label: 'Exploratoire' },
  insufficient: { cls: 'is-insufficient', label: 'Insuffisante' },
};
function qualityMeta(level) {
  return QUALITY_META[level] || { cls: 'is-exploratory', label: level || '—' };
}
const CONFIDENCE_LABELS = { high: 'Élevée', medium: 'Moyenne', low: 'Faible' };
const CATEGORY_LABELS = {
  emotions: 'Émotions', themes: 'Thèmes', behavioral_signals: 'Signaux comportementaux',
  fears: 'Peurs', aspirations: 'Aspirations', frustrations: 'Frustrations',
  beliefs: 'Croyances', motivations: 'Motivations', objections: 'Objections',
};
function categoryLabel(cat) {
  return CATEGORY_LABELS[cat] || (cat ? cat.charAt(0).toUpperCase() + cat.slice(1) : 'Signal');
}

/* ── Saisie ──────────────────────────────────────────────────────────── */

function PsychoInput({
  tab, onTabChange, platform, onPlatformChange,
  url, onUrlChange, manualText, onManualTextChange,
  checking, onCheck, statusMsg, statusTone, previewCount,
  file, onFilePick, onColumnChange, uploading,
  onLaunch, onOpenCross,
}) {
  const linkReady = Boolean(LINK_SOURCES[platform]) && previewCount > 0;
  const manualCount = manualText.trim().split('\n').filter(Boolean).length;
  const canLaunch = tab === 'link' ? linkReady
    : tab === 'manual' ? manualCount >= 3
    : Boolean(file && file.count >= 3);
  const config = LINK_SOURCES[platform];

  return <section className="gv2-psy-input">
    <div className="gv2-psy-input-head">
      <div>
        <span className="gv2-psy-eyebrow">Le Psychologue</span>
        <h1>Analyse factuelle des commentaires</h1>
      </div>
      <button type="button" className="gv2-psy-cross-trigger" onClick={onOpenCross}>
        <Icon name="activity" size={13} />
        Cross Analyse
      </button>
    </div>
    <div className="gv2-psy-card">
      <div className="gv2-psy-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === 'link'} className={tab === 'link' ? 'is-active' : ''} onClick={() => onTabChange('link')}>Sources</button>
        <button type="button" role="tab" aria-selected={tab === 'manual'} className={tab === 'manual' ? 'is-active' : ''} onClick={() => onTabChange('manual')}>Commentaires</button>
        <button type="button" role="tab" aria-selected={tab === 'file'} className={tab === 'file' ? 'is-active' : ''} onClick={() => onTabChange('file')}>Fichier</button>
      </div>
      <div className="gv2-psy-card-body">
        {tab === 'link' && <>
          <div className="gv2-psy-platforms" role="tablist" aria-label="Plateforme à analyser">
            {Object.entries(LINK_SOURCES).map(([key, meta]) => (
              <button key={key} type="button" role="tab" aria-selected={platform === key}
                      className={`gv2-psy-platform${platform === key ? ' is-active' : ''}`}
                      onClick={() => onPlatformChange(key)}>
                <span className="gv2-psy-platform-mark">{meta.mark}</span>{meta.label}
              </button>
            ))}
            <button type="button" className={`gv2-psy-platform${platform === 'google' ? ' is-active' : ''}`}
                    aria-selected={platform === 'google'} onClick={() => onPlatformChange('google')}>
              <span className="gv2-psy-platform-mark">G</span>Google
            </button>
            <button type="button" className="gv2-psy-platform" onClick={() => onTabChange('manual')}>
              <span className="gv2-psy-platform-mark">+</span>Autre source
            </button>
          </div>
          <div className="gv2-psy-link-row">
            <Icon name="link" size={16} />
            <input type="url" value={url} disabled={!config}
                   onChange={event => onUrlChange(event.target.value)}
                   placeholder={config ? config.placeholder : 'La collecte Google arrive prochainement…'}
                   onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); onCheck(); } }} />
            <button type="button" className="gv2-psy-check-btn" disabled={checking || !config} onClick={onCheck} aria-label="Vérifier le lien" title="Vérifier le lien">
              <Icon name={checking ? 'refresh' : 'send'} size={16} className={checking ? 'gv2-spin' : ''} />
            </button>
          </div>
          <p className="gv2-psy-example">{config ? config.example : 'Pour l’instant, collez les avis dans « Commentaires ».'}</p>
          {statusMsg && <p className={`gv2-psy-status${statusTone ? ` is-${statusTone}` : ''}`} role="status">{statusMsg}</p>}
        </>}

        {tab === 'manual' && <>
          <textarea value={manualText} onChange={event => onManualTextChange(event.target.value)} placeholder="Collez vos commentaires ici, un par ligne…" rows={7} />
          <div className="gv2-psy-comment-meta">
            <span>Un commentaire par ligne · Min. 3</span>
            <span className="gv2-psy-comment-count">{manualCount}</span>
          </div>
        </>}

        {tab === 'file' && <>
          <label className="gv2-psy-dropzone">
            <input type="file" accept=".csv,.xlsx,.xls,.json,.txt" hidden
                   onChange={event => onFilePick(event.target.files && event.target.files[0])} />
            <Icon name="file" size={20} />
            <span className="gv2-psy-dropzone-title">
              {uploading ? 'Lecture du fichier…' : file ? file.name : 'Choisir un fichier de commentaires'}
            </span>
            <span className="gv2-psy-dropzone-hint">CSV, Excel, JSON ou TXT · 5 Mo maximum</span>
          </label>
          {file && file.columns && file.columns.length > 1 && (
            <label className="gv2-psy-column-picker">
              <span>Colonne à analyser</span>
              <select value={file.column || ''} onChange={event => onColumnChange(event.target.value)}>
                {file.columns.map(col => <option key={col} value={col}>{col}</option>)}
              </select>
            </label>
          )}
          {file && <div className="gv2-psy-comment-meta">
            <span>{file.warning || `${file.count} commentaire${file.count === 1 ? '' : 's'} lu${file.count === 1 ? '' : 's'}`}</span>
            <span className="gv2-psy-comment-count">{file.count}</span>
          </div>}
          {statusMsg && statusTone !== 'success' && <p className={`gv2-psy-status${statusTone ? ` is-${statusTone}` : ''}`} role="status">{statusMsg}</p>}
        </>}
      </div>
      <div className="gv2-psy-card-footer">
        <span className="gv2-psy-hint">Minimum 3 commentaires</span>
        <button type="button" className="gv2-psy-launch-btn" disabled={!canLaunch} onClick={onLaunch}>
          <Icon name="sparkle" size={14} />
          Lancer l'analyse
        </button>
      </div>
    </div>
  </section>;
}


/* ── Panneau flottant Cross Analyse ──────────────────────────────────── */

function PsychoCrossModal({
  sources, url, onUrlChange, checking, onCheck, statusMsg, statusTone, previewCount,
  onAddSource, onRemoveSource, onLaunch, onClose,
}) {
  const pendingReady = previewCount > 0 && url.trim();
  const total = sources.length + (pendingReady ? 1 : 0);
  const canAdd = pendingReady && sources.length < CROSS_MAX_SOURCES;
  const canLaunch = total >= CROSS_MIN_SOURCES && total <= CROSS_MAX_SOURCES;

  return <div className="gv2-psy-cross-backdrop" onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="gv2-psy-cross-panel" role="dialog" aria-modal="true" aria-labelledby="gv2-cross-title">
      <div className="gv2-psy-cross-head">
        <div>
          <div className="gv2-psy-cross-title" id="gv2-cross-title">Cross Analyse</div>
          <div className="gv2-psy-cross-sub">Comparez 2 à 5 audiences YouTube en une seule lecture</div>
        </div>
        <button type="button" className="gv2-psy-cross-close" onClick={onClose} aria-label="Fermer"><Icon name="close" size={13} /></button>
      </div>
      <div className="gv2-psy-cross-body">
        <div className="gv2-psy-link-row">
          <Icon name="link" size={16} />
          <input type="url" value={url} onChange={event => onUrlChange(event.target.value)} placeholder="Collez le lien de la vidéo YouTube ici…" onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); onCheck(); } }} />
          <button type="button" className="gv2-psy-check-btn" disabled={checking} onClick={onCheck} aria-label="Vérifier le lien" title="Vérifier le lien">
            <Icon name={checking ? 'refresh' : 'send'} size={16} className={checking ? 'gv2-spin' : ''} />
          </button>
        </div>
        <p className="gv2-psy-example">Exemple : youtube.com/watch?v=…</p>
        {statusMsg && <p className={`gv2-psy-status${statusTone ? ` is-${statusTone}` : ''}`} role="status">{statusMsg}</p>}

        {sources.length > 0 && <div className="gv2-psy-cross-list">
          {sources.map((source, index) => <div className="gv2-psy-cross-row" key={source.url}>
            <span className="gv2-psy-cross-row-index">{index + 1}</span>
            <span className="gv2-psy-cross-row-label">{source.label || source.url}</span>
            <button type="button" onClick={() => onRemoveSource(index)} aria-label="Retirer cette vidéo"><Icon name="close" size={11} /></button>
          </div>)}
        </div>}

        {canAdd && <button type="button" className="gv2-psy-cross-add" onClick={onAddSource}><Icon name="plus" size={13} />Ajouter une autre vidéo</button>}
      </div>
      <div className="gv2-psy-cross-foot">
        <span className="gv2-psy-hint">{total < CROSS_MIN_SOURCES ? `Ajoutez au moins ${CROSS_MIN_SOURCES} vidéos pour comparer` : `${total} vidéo${total > 1 ? 's' : ''} prête${total > 1 ? 's' : ''} à être comparée${total > 1 ? 's' : ''}`}</span>
        <button type="button" className="gv2-psy-launch-btn" disabled={!canLaunch} onClick={onLaunch}>
          <Icon name="sparkle" size={14} />
          Comparer {total || ''} audience{total > 1 ? 's' : ''}
        </button>
      </div>
    </div>
  </div>;
}

/* ── Chargement / Erreur ─────────────────────────────────────────────── */

function PsychoLoading({ progress, step }) {
  return <section className="gv2-psy-loading">
    <div className="gv2-psy-loading-ring" />
    <div className="gv2-psy-loading-pct">{progress}%</div>
    <p className="gv2-psy-loading-title">Gabriel analyse votre audience…</p>
    <p className="gv2-psy-loading-step">{step || 'Lecture des réactions du marché…'}</p>
  </section>;
}

function PsychoError({ message, onRetry }) {
  return <section className="gv2-psy-error">
    <p>{message || 'Une erreur est survenue.'}</p>
    <button type="button" onClick={onRetry}><Icon name="refresh" size={14} />Réessayer</button>
  </section>;
}

/* ── Résultat — analyse simple ───────────────────────────────────────── */

function StatChip({ value, count, label, tone }) {
  return <div className="gv2-psy-stat-chip">
    <div className={`gv2-psy-stat-val${tone ? ` is-${tone}` : ''}`}>{value}</div>
    {count != null && <div className="gv2-psy-stat-count">{count}</div>}
    <div className="gv2-psy-stat-lbl">{label}</div>
  </div>;
}

function Bar({ label, pct, count }) {
  return <div className="gv2-psy-bar-row">
    <span className="gv2-psy-bar-label">{esc(label)}</span>
    <div className="gv2-psy-bar-track"><div className="gv2-psy-bar-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} /></div>
    <span className="gv2-psy-bar-pct">{pct}%</span>
    {count != null && <span className="gv2-psy-bar-count">{count} cmnt</span>}
  </div>;
}

function PsychoResult({ data, onReset, onGoToStratege }) {
  const db = data.dashboard || {};
  const meta = data.meta || {};
  const brief = data.brief || {};
  const pos = db.positions || {};
  const emotions = Array.isArray(db.emotion_distribution)
    ? db.emotion_distribution
    : Object.entries(db.emotion_distribution || {}).map(([emotion, pct]) => ({ emotion, pourcentage: pct }));
  const personas = Array.isArray(data.personas) ? data.personas : [];
  const synthese = brief.qui || brief.synthese || '';
  const insight = brief.insight || brief.insight_cle || '';
  const action = brief.action || brief.action_prioritaire || '';

  return <section className="gv2-psy-result">
    <div className="gv2-psy-result-head">
      <div>
        <span className="gv2-psy-eyebrow">Le Psychologue</span>
        <h1>Résultats</h1>
      </div>
      <div className="gv2-psy-result-actions">
        <button type="button" className="gv2-psy-ghost-btn" onClick={onReset}>← Nouvelle analyse</button>
        {data.analysis_id && <button type="button" className="gv2-psy-primary-btn" onClick={() => onGoToStratege(data)}>Stratège →</button>}
      </div>
    </div>

    {synthese && <div className="gv2-psy-hero">
      <div className="gv2-psy-hero-label">Interprétation psychologique</div>
      <p className="gv2-psy-hero-text">{synthese}</p>
      <div className="gv2-psy-hero-pills">
        {insight && <span><strong>Insight ·</strong> {insight}</span>}
        {action && <span><strong>Action ·</strong> {action}</span>}
      </div>
    </div>}

    <div className="gv2-psy-stats-grid">
      <StatChip value={meta.total_commentaires || 0} count={`${meta.commentaires_analyses || 0} qualifiés`} label="Collectés" />
      <StatChip value={`${(pos.favorable || {}).pct || 0}%`} count={`${(pos.favorable || {}).count || 0} cmnt`} label="Favorables" tone="pos" />
      <StatChip value={`${(pos.oppose || {}).pct || 0}%`} count={`${(pos.oppose || {}).count || 0} cmnt`} label="Négatifs" tone="neg" />
      <StatChip value={`${(pos.neutre || {}).pct || 0}%`} count={`${(pos.neutre || {}).count || 0} cmnt`} label="Neutres" />
    </div>

    {emotions.length > 0 && <div className="gv2-psy-section">
      <div className="gv2-psy-section-title">Émotions détectées</div>
      <div className="gv2-psy-card gv2-psy-card--plain">
        {emotions.slice(0, 6).map((item, index) => <Bar key={index} label={item.emotion} pct={Math.round(item.pourcentage || item.pct || 0)} />)}
      </div>
    </div>}

    {Object.keys(pos).length > 0 && <div className="gv2-psy-section">
      <div className="gv2-psy-section-title">Répartition des positions</div>
      <div className="gv2-psy-card gv2-psy-card--plain">
        {Object.entries(pos).map(([key, value]) => <Bar key={key} label={key} pct={Math.round(value.pct || 0)} count={value.count} />)}
      </div>
    </div>}

    {personas.length > 0 && <div className="gv2-psy-section">
      <div className="gv2-psy-section-title">Personas</div>
      <div className="gv2-psy-persona-grid">
        {personas.map((persona, index) => <div className="gv2-psy-persona-card" key={index}>
          <div className="gv2-psy-persona-name">{persona.nom || `Persona ${index + 1}`}</div>
          {(persona.age || persona.genre || persona.metier) && <div className="gv2-psy-persona-meta">{[persona.age ? `${persona.age} ans` : '', persona.genre, persona.metier].filter(Boolean).join(' · ')}</div>}
          {persona.histoire_interieure && <p className="gv2-psy-persona-quote">"{persona.histoire_interieure}"</p>}
        </div>)}
      </div>
    </div>}
  </section>;
}

/* ── Résultat — Cross Analyse ─────────────────────────────────────────── */

function groupByCategory(items) {
  const map = {};
  items.forEach(item => { const cat = item.category || 'autre'; (map[cat] = map[cat] || []).push(item); });
  return map;
}

function CrossSignalList({ items, emptyText }) {
  if (!items.length) return <p className="gv2-psy-cross-empty">{emptyText}</p>;
  const grouped = groupByCategory(items);
  return Object.keys(grouped).sort().map(cat => <div className="gv2-psy-cross-cat" key={cat}>
    <div className="gv2-psy-cross-cat-title">{categoryLabel(cat)}</div>
    {grouped[cat].map((item, index) => <div className="gv2-psy-cross-signal-row" key={index}>
      <span>{esc(item.label)}</span>
      <div className="gv2-psy-cross-tags">{(item.sources || []).map((source, i) => <span key={i} className="gv2-psy-cross-tag">{esc(source.label || source.source_id)}</span>)}</div>
    </div>)}
  </div>);
}

function PsychoCrossResult({ data, onReset }) {
  const result = data.result || {};
  const crossId = data.cross_analysis_id || '';
  const status = data.status || '';
  const sources = Array.isArray(result.sources) ? result.sources : [];
  const failedSources = Array.isArray(result.failed_sources) ? result.failed_sources : [];
  const confidence = result.confidence || {};
  const dataQuality = result.data_quality || {};
  const execSummary = result.executive_summary || {};
  const psychoCore = result.common_psychological_core || {};
  const coreText = psychoCore.interpretation && typeof psychoCore.interpretation === 'object'
    ? psychoCore.interpretation.interpretation
    : (typeof psychoCore.interpretation === 'string' ? psychoCore.interpretation : null);
  const personas = Array.isArray(result.cross_personas) ? result.cross_personas : [];
  const scoreVal = Math.round(Number(confidence.score) || 0);
  const convergences = Array.isArray(result.convergences) ? result.convergences : [];
  const divergences = Array.isArray(result.divergences) ? result.divergences : [];
  const oppositions = Array.isArray(result.oppositions) ? result.oppositions : [];
  const specific = Array.isArray(result.source_specific_signals) ? result.source_specific_signals : [];
  const specificSorted = specific.slice().sort((a, b) => {
    const wa = (a.sources && a.sources[0] && a.sources[0].weight) || 0;
    const wb = (b.sources && b.sources[0] && b.sources[0].weight) || 0;
    return wb - wa;
  });
  const SPECIFIC_CAP = 12;
  const specificShown = specificSorted.slice(0, SPECIFIC_CAP);
  const specificMore = specificSorted.length - specificShown.length;

  return <section className="gv2-psy-result gv2-psy-cross-result">
    <div className="gv2-psy-result-head">
      <div>
        <span className="gv2-psy-eyebrow">Le Psychologue</span>
        <h1>Cross Analyse — {sources.length} audience{sources.length === 1 ? '' : 's'} comparée{sources.length === 1 ? '' : 's'}</h1>
      </div>
      <button type="button" className="gv2-psy-ghost-btn" onClick={onReset}>← Nouvelle analyse</button>
    </div>

    {(status === 'partial_success' || failedSources.length > 0) && <div className="gv2-psy-cross-warn">
      <strong>Analyse partielle.</strong> {failedSources.length} source{failedSources.length === 1 ? '' : 's'} n'{failedSources.length === 1 ? 'a' : 'ont'} pas pu être analysée{failedSources.length === 1 ? '' : 's'}. Les résultats portent sur {sources.length} source{sources.length === 1 ? '' : 's'} exploitable{sources.length === 1 ? '' : 's'}.
    </div>}

    <div className="gv2-psy-cross-hero">
      <div className="gv2-psy-cross-hero-score">
        <div className="gv2-psy-cross-hero-num">{scoreVal}<span>/100</span></div>
        <div className="gv2-psy-cross-hero-level">{CONFIDENCE_LABELS[confidence.level] || confidence.level || ''}</div>
      </div>
      <div className="gv2-psy-cross-hero-body">
        <div className="gv2-psy-hero-label">Conclusion générale</div>
        <p className="gv2-psy-hero-text">{formatInline(execSummary.text || 'Analyse terminée.')}</p>
        {Array.isArray(execSummary.caveats) && execSummary.caveats.length > 0 && <div className="gv2-psy-cross-caveats">
          <div className="gv2-psy-cross-caveats-lbl">Points de prudence</div>
          {execSummary.caveats.map((caveat, index) => <div key={index} className="gv2-psy-cross-caveat">— {formatInline(caveat)}</div>)}
        </div>}
      </div>
    </div>

    <div className="gv2-psy-cross-meta">
      <span><strong>{sources.length}</strong> audience{sources.length === 1 ? '' : 's'} comparée{sources.length === 1 ? '' : 's'}</span>
      {confidence.total_comments ? <span><strong>{confidence.total_comments}</strong> commentaires analysés</span> : null}
      {dataQuality.level ? <span>Qualité des données : <strong>{qualityMeta(dataQuality.level).label}</strong></span> : null}
    </div>

    {coreText && <div className="gv2-psy-section">
      <div className="gv2-psy-section-title">Noyau psychologique commun</div>
      <div className="gv2-psy-cross-quote">{formatInline(coreText)}</div>
    </div>}

    <div className="gv2-psy-section">
      <div className="gv2-psy-section-title">Vidéos comparées</div>
      <div className="gv2-psy-cross-video-grid">
        {sources.map((source, index) => {
          const metaInfo = source.metadata || {};
          const initial = (metaInfo.channel || metaInfo.title || '?').trim().charAt(0).toUpperCase() || '?';
          const views = fmtCount(metaInfo.view_count), likes = fmtCount(metaInfo.like_count), comments = fmtCount(metaInfo.comment_count), duration = fmtDuration(metaInfo.duration);
          const quality = source.data_quality && source.data_quality.level ? qualityMeta(source.data_quality.level) : null;
          return <div className="gv2-psy-cross-video-card" key={source.source_id || index}>
            <div className="gv2-psy-cross-video-head">
              <div className="gv2-psy-cross-video-mark">{initial}</div>
              <div className="gv2-psy-cross-video-info">
                <div className="gv2-psy-cross-video-title">{metaInfo.title || `Vidéo ${index + 1}`}</div>
                <div className="gv2-psy-cross-video-channel">{metaInfo.channel || ''}</div>
              </div>
              {quality && <span className={`gv2-psy-cross-quality ${quality.cls}`}>{quality.label}</span>}
            </div>
            <div className="gv2-psy-cross-video-stats">
              {views !== null && <span><strong>{views}</strong> vues</span>}
              {likes !== null && <span><strong>{likes}</strong> likes</span>}
              {comments !== null && <span><strong>{comments}</strong> commentaires</span>}
              {duration && <span>{duration}</span>}
            </div>
            {metaInfo.canonical_url && <a className="gv2-psy-cross-video-link" href={metaInfo.canonical_url} target="_blank" rel="noopener noreferrer">Voir la vidéo ↗</a>}
          </div>;
        })}
      </div>
    </div>

    <div className="gv2-psy-section">
      <div className="gv2-psy-section-title">Analyse croisée</div>
      <div className="gv2-psy-cross-snap-grid">
        <div className="gv2-psy-cross-snap"><div className="gv2-psy-cross-snap-lbl">Convergences</div><div className="gv2-psy-cross-snap-val">{convergences.length}</div><div className="gv2-psy-cross-snap-sub">signaux partagés</div></div>
        <div className="gv2-psy-cross-snap"><div className="gv2-psy-cross-snap-lbl">Divergences</div><div className="gv2-psy-cross-snap-val">{divergences.length}</div><div className="gv2-psy-cross-snap-sub">signaux qui varient</div></div>
        <div className="gv2-psy-cross-snap"><div className="gv2-psy-cross-snap-lbl">Oppositions</div><div className="gv2-psy-cross-snap-val">{oppositions.length}</div><div className="gv2-psy-cross-snap-sub">positions contraires</div></div>
      </div>
      <div className="gv2-psy-card gv2-psy-card--plain gv2-psy-cross-block">
        <div className="gv2-psy-cross-block-title">Convergences — signaux partagés par plusieurs audiences</div>
        <CrossSignalList items={convergences} emptyText="Aucune convergence détectée entre ces audiences." />
      </div>
      <div className="gv2-psy-card gv2-psy-card--plain gv2-psy-cross-block">
        <div className="gv2-psy-cross-block-title">Divergences — signaux qui varient d'une audience à l'autre</div>
        <CrossSignalList items={divergences} emptyText="Aucune divergence détectée : les audiences se recoupent fortement." />
      </div>
      <div className="gv2-psy-card gv2-psy-card--plain gv2-psy-cross-block">
        <div className="gv2-psy-cross-block-title">Oppositions — positions contraires entre audiences</div>
        <CrossSignalList items={oppositions} emptyText="Aucune opposition détectée." />
      </div>
      <div className="gv2-psy-card gv2-psy-card--plain gv2-psy-cross-block">
        <div className="gv2-psy-cross-block-title">Signaux propres à une seule audience</div>
        <CrossSignalList items={specificShown} emptyText="Aucun signal isolé détecté." />
        {specificMore > 0 && <p className="gv2-psy-cross-more">+ {specificMore} autre{specificMore === 1 ? '' : 's'} signal{specificMore === 1 ? '' : 'aux'} spécifique{specificMore === 1 ? '' : 's'} non affiché{specificMore === 1 ? '' : 's'}.</p>}
      </div>
    </div>

    {personas.length > 0 && <div className="gv2-psy-section">
      <div className="gv2-psy-section-title">Personas croisés</div>
      <div className="gv2-psy-persona-grid">
        {personas.map((persona, index) => <div className="gv2-psy-persona-card" key={index}>
          <div className="gv2-psy-cross-persona-head">
            <div className="gv2-psy-persona-name">{persona.name || 'Persona'}</div>
            {persona.confidence_level && <span className="gv2-psy-cross-persona-conf">{persona.confidence_level}</span>}
          </div>
          {persona.description && <p className="gv2-psy-persona-quote">{formatInline(persona.description)}</p>}
          <div className="gv2-psy-cross-tags">
            {(Array.isArray(persona.signals) ? persona.signals : []).map((signal, i) => <span key={i} className="gv2-psy-cross-tag">{typeof signal === 'string' ? signal : signal.label || ''}</span>)}
          </div>
        </div>)}
      </div>
    </div>}

    <details className="gv2-psy-cross-tech">
      <summary>Détails techniques</summary>
      <div className="gv2-psy-cross-tech-body">
        {[
          ['cross_analysis_id', crossId],
          ['job_id', result.job_id],
          ['schema_version', result.schema_version],
          ['pipeline_version', result.pipeline_version],
          ['model_version', result.model_version],
          ['embedding_version', result.embedding_version],
          ['analysis_mode', result.analysis_mode],
        ].filter(([, value]) => value !== undefined && value !== null && value !== '').map(([key, value]) => `${key} : ${value}`).join('\n')}
      </div>
    </details>
  </section>;
}

/* ── Racine ──────────────────────────────────────────────────────────── */

export function PsychologueView({ workspace, onWorkspaceChange, onNavigateAgent }) {
  const [tab, setTab] = useState('link');
  const [platform, setPlatform] = useState('youtube');
  const [url, setUrl] = useState('');
  const [manualText, setManualText] = useState('');
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [previewCount, setPreviewCount] = useState(0);
  const [checking, setChecking] = useState(false);
  const [statusMsg, setStatusMsg] = useState('Collez le lien d’une vidéo YouTube.');
  const [statusTone, setStatusTone] = useState('');
  const [stage, setStage] = useState('input');
  const [resultKind, setResultKind] = useState('single');
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [result, setResult] = useState(null);
  const [crossResult, setCrossResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const pollingRef = useRef(false);
  const crossPollingRef = useRef(false);
  // Les boucles de suivi durent plusieurs minutes : sans ce drapeau, changer
  // d'onglet laisse la boucle interroger le serveur indéfiniment en arrière-
  // plan et écrire dans l'état d'un composant démonté.
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; };
  }, []);

  const [crossModalOpen, setCrossModalOpen] = useState(false);
  const [crossSources, setCrossSources] = useState([]);
  const [crossUrl, setCrossUrl] = useState('');
  const [crossPreviewCount, setCrossPreviewCount] = useState(0);
  const [crossChecking, setCrossChecking] = useState(false);
  const [crossStatusMsg, setCrossStatusMsg] = useState('Collez le lien d’une vidéo YouTube.');
  const [crossStatusTone, setCrossStatusTone] = useState('');

  useEffect(() => {
    let stored = null;
    try { stored = JSON.parse(window.localStorage.getItem(PENDING_JOB_KEY) || 'null'); } catch (_) { stored = null; }
    if (stored?.crossId) {
      setStage('loading'); setResultKind('cross');
      pollCrossAnalysis(stored.crossId);
      return;
    }
    if (stored?.id) {
      setStage('loading'); setResultKind('single');
      pollAnalysis(stored.id);
      return;
    }
    // Pas de job en cours : si ce workspace a déjà une analyse enregistrée
    // (même mécanisme que Le Créateur avec creator_output_id), on la
    // recharge directement plutôt que de repartir d'un écran de saisie vide.
    let live = true;
    if (workspace?.analysis_id) {
      fetchV2(`/history/${encodeURIComponent(workspace.analysis_id)}/load`).then(async response => {
        if (isLoginResponse(response)) { window.location.assign('/login'); return null; }
        const payload = await readApiPayload(response, 'L’analyse enregistrée');
        return response.ok && payload.success ? payload : null;
      }).then(payload => {
        if (!live || !payload?.full_result) return;
        setResult(payload.full_result); setResultKind('single'); setStage('result');
      }).catch(() => {});
    }
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace?.folder_id, workspace?.analysis_id]);

  function goToStratege(data) {
    const brief = data.brief || {};
    const psycho = data.psychologie || {};
    const marketing = data.marketing || {};
    const lines = [];
    if (brief.synthese) lines.push('Audience : ' + brief.synthese);
    if (brief.insight_cle) lines.push('Insight clé : ' + brief.insight_cle);
    if (brief.action_prioritaire) lines.push('Action : ' + brief.action_prioritaire);
    const motiv = (psycho.motivations_profondes || []).slice(0, 2).map(m => typeof m === 'string' ? m : JSON.stringify(m));
    if (motiv.length) lines.push('Motivations : ' + motiv.join(', '));
    const frustr = (psycho.frustrations || []).slice(0, 2).map(f => typeof f === 'string' ? f : JSON.stringify(f));
    if (frustr.length) lines.push('Frustrations : ' + frustr.join(', '));
    const hooks = (marketing.hooks_performants || []).slice(0, 2);
    if (hooks.length) lines.push('Hooks : ' + hooks.join(' | '));
    try {
      window.sessionStorage.setItem('gabriel_for_stratege', JSON.stringify({
        analysis_id: data.analysis_id,
        folder_id: workspace?.folder_id || '',
        psycho_brief: lines.join('\n'),
        psycho_data: {
          brief, psychologie: psycho, emotions: data.emotions || {}, marketing,
          kpis: data.kpis || {}, aspirations: data.aspirations || {},
          personas: data.personas || [], distribution: data.distribution || {},
        },
      }));
    } catch (_) { /* sessionStorage peut être indisponible (navigation privée) */ }
    onNavigateAgent?.('stratege');
  }

  async function checkLink() {
    const config = LINK_SOURCES[platform];
    if (!config) return;
    const trimmed = url.trim();
    if (!trimmed) { setStatusMsg(`Collez d’abord le lien ${config.label}.`); setStatusTone('error'); return; }
    setChecking(true);
    setStatusMsg('Vérification du lien et détection des commentaires…');
    setStatusTone('busy');
    try {
      const response = await fetchV2('/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: platform, content: trimmed, preview_only: true }),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const data = await readApiPayload(response, 'La vérification du lien');
      if (data.comments_preview) {
        const count = Number(data.comments_count || data.comments_preview.length || 0);
        setPreviewCount(count);
        setStatusMsg(`${count} commentaire${count === 1 ? '' : 's'} détecté${count === 1 ? '' : 's'}. Le lien est prêt à analyser.`);
        setStatusTone('success');
      } else if (data.error) {
        setStatusMsg(data.error); setStatusTone('error'); setPreviewCount(0);
      } else {
        setStatusMsg('Lien enregistré. Vous pouvez lancer l’analyse.'); setStatusTone('success');
      }
    } catch (_) {
      setStatusMsg('Impossible de vérifier le lien. Vérifiez votre connexion.'); setStatusTone('error');
    } finally {
      setChecking(false);
    }
  }

  async function pollAnalysis(jobId) {
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      for (let attempt = 0; attempt < 160; attempt += 1) {
        await pause(3000);
        if (!aliveRef.current) return;
        const response = await fetchV2(`/status/${encodeURIComponent(jobId)}`);
        if (isLoginResponse(response)) { window.location.assign('/login'); return; }
        const payload = await readApiPayload(response, 'Le suivi de l’analyse');
        if (payload.status === 'done') {
          setResult(payload.data); setResultKind('single'); setStage('result');
          try { window.localStorage.removeItem(PENDING_JOB_KEY); } catch (_) {}
          await onWorkspaceChange?.();
          return;
        }
        if (['error', 'interrupted', 'not_found'].includes(payload.status)) {
          throw new Error(payload.error || 'L’analyse a été interrompue.');
        }
        setProgress(Math.min(95, Math.round(((attempt + 1) / 160) * 100)));
        if (payload.step) setStep(payload.step);
      }
      throw new Error('L’analyse prend plus de temps que prévu.');
    } catch (error) {
      try { window.localStorage.removeItem(PENDING_JOB_KEY); } catch (_) {}
      if (!aliveRef.current) return;
      setStage('error'); setErrorMsg(error.message || 'Une erreur est survenue.');
    } finally {
      pollingRef.current = false;
    }
  }

  function changeTab(next) {
    setTab(next);
    if (next === 'link') {
      const config = LINK_SOURCES[platform];
      setStatusMsg(config ? `Collez le lien ${config.label}, puis vérifiez les commentaires disponibles.` : '');
    } else {
      // Le statut est partagé entre onglets : sans ce nettoyage, le message du
      // lien restait affiché sous la zone de dépôt de fichier.
      setStatusMsg('');
    }
    setStatusTone('');
  }

  function changePlatform(next) {
    setPlatform(next);
    setUrl('');
    setPreviewCount(0);
    const config = LINK_SOURCES[next];
    if (config) {
      setStatusMsg(`Collez le lien ${config.label}, puis vérifiez les commentaires disponibles.`);
      setStatusTone('');
    } else {
      // Google est annoncé dans l'interface mais pas encore collecté : le dire
      // franchement plutôt que de laisser l'utilisateur essayer dans le vide.
      setStatusMsg('Google sera connecté dès que cette source sera disponible dans votre workspace.');
      setStatusTone('busy');
    }
  }

  async function uploadFile(picked, forcedColumn = null) {
    if (!picked) return;
    setUploading(true);
    setStatusMsg('Lecture du fichier…');
    setStatusTone('busy');
    try {
      const form = new FormData();
      form.append('file', picked);
      if (forcedColumn) form.append('column', forcedColumn);
      const response = await fetchV2('/upload-comments-file', { method: 'POST', body: form });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const data = await readApiPayload(response, 'L’import du fichier');
      if (!response.ok || !data.success) throw new Error(data.error || 'Impossible de lire ce fichier.');
      setFile({
        name: picked.name,
        raw: picked,
        count: data.comments_count || 0,
        columns: data.detected_columns || [],
        column: data.selected_column || '',
        warning: data.warning || '',
        comments: data.normalized_comments || [],
      });
      setStatusMsg(`${data.comments_count} commentaire${data.comments_count === 1 ? '' : 's'} lu${data.comments_count === 1 ? '' : 's'}.`);
      setStatusTone('success');
    } catch (error) {
      setFile(null);
      setStatusMsg(error.message || 'Impossible de lire ce fichier.');
      setStatusTone('error');
    } finally {
      setUploading(false);
    }
  }

  async function launch() {
    const comments = manualText.split('\n').map(line => line.trim()).filter(Boolean);
    if (tab === 'manual' && comments.length < 3) { setStatusMsg('Ajoutez au moins 3 commentaires.'); setStatusTone('error'); return; }
    if (tab === 'link' && previewCount <= 0) { setStatusMsg('Vérifiez d’abord le lien.'); setStatusTone('error'); return; }
    if (tab === 'file' && !(file && file.count >= 3)) { setStatusMsg('Importez d’abord un fichier d’au moins 3 commentaires.'); setStatusTone('error'); return; }

    setStage('loading'); setResultKind('single'); setProgress(0); setStep('Lecture des réactions du marché…'); setErrorMsg('');
    const folder_id = workspace?.folder_id || undefined;
    const body = tab === 'manual'
      ? { source: 'text', content: manualText, comments, folder_id }
      : tab === 'file'
        ? { source: 'file', content: file.name, comments: file.comments, folder_id }
        : { source: platform, content: url.trim(), folder_id };

    try {
      const response = await fetchV2('/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const data = await readApiPayload(response, 'Le lancement de l’analyse');
      if (!response.ok || data?.error) throw new Error(data?.error || 'Le lancement a échoué.');
      try { window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: data.job_id, t0: Date.now() })); } catch (_) {}
      await pollAnalysis(data.job_id);
    } catch (error) {
      setStage('error'); setErrorMsg(error.message || 'Une erreur est survenue.');
    }
  }

  /* ── Cross Analyse ──────────────────────────────────────────────────── */

  async function checkCrossLink() {
    const trimmed = crossUrl.trim();
    if (!trimmed) { setCrossStatusMsg('Collez d’abord le lien YouTube.'); setCrossStatusTone('error'); return; }
    if (crossSources.some(source => source.url === trimmed)) { setCrossStatusMsg('Cette vidéo est déjà dans la liste.'); setCrossStatusTone('error'); return; }
    setCrossChecking(true);
    setCrossStatusMsg('Vérification du lien et détection des commentaires…');
    setCrossStatusTone('busy');
    try {
      const response = await fetchV2('/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'youtube', content: trimmed, preview_only: true }),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const data = await readApiPayload(response, 'La vérification du lien');
      if (data.comments_preview) {
        const count = Number(data.comments_count || data.comments_preview.length || 0);
        setCrossPreviewCount(count);
        setCrossStatusMsg(`${count} commentaire${count === 1 ? '' : 's'} détecté${count === 1 ? '' : 's'}. Le lien est prêt à analyser.`);
        setCrossStatusTone('success');
      } else if (data.error) {
        setCrossStatusMsg(data.error); setCrossStatusTone('error'); setCrossPreviewCount(0);
      } else {
        setCrossStatusMsg('Lien enregistré.'); setCrossStatusTone('success');
      }
    } catch (_) {
      setCrossStatusMsg('Impossible de vérifier le lien. Vérifiez votre connexion.'); setCrossStatusTone('error');
    } finally {
      setCrossChecking(false);
    }
  }

  function addCrossSource() {
    const trimmed = crossUrl.trim();
    if (!trimmed || crossPreviewCount <= 0 || crossSources.length >= CROSS_MAX_SOURCES) return;
    setCrossSources(current => [...current, { url: trimmed, label: trimmed.replace(/^https?:\/\/(www\.)?/, '') }]);
    setCrossUrl(''); setCrossPreviewCount(0);
    setCrossStatusMsg('Collez le lien de la vidéo suivante.'); setCrossStatusTone('');
  }

  function removeCrossSource(index) {
    setCrossSources(current => current.filter((_, i) => i !== index));
  }

  function closeCrossModal() {
    setCrossModalOpen(false);
  }

  async function pollCrossAnalysis(crossId) {
    if (crossPollingRef.current) return;
    crossPollingRef.current = true;
    try {
      for (let attempt = 0; attempt < 160; attempt += 1) {
        await pause(3000);
        if (!aliveRef.current) return;
        const response = await fetchV2(`/api/v2/agents/psychologue/cross-analyses/${encodeURIComponent(crossId)}/status`);
        if (isLoginResponse(response)) { window.location.assign('/login'); return; }
        const payload = await readApiPayload(response, 'Le suivi de la Cross Analyse');
        if (payload.status === 'completed' || payload.status === 'partial_success') {
          const fullResponse = await fetchV2(`/api/v2/agents/psychologue/cross-analyses/${encodeURIComponent(crossId)}`);
          if (isLoginResponse(fullResponse)) { window.location.assign('/login'); return; }
          const fullData = await readApiPayload(fullResponse, 'Le résultat de la Cross Analyse');
          if (!fullResponse.ok || !fullData.success || !fullData.result) throw new Error(fullData.error || 'Impossible de charger le résultat.');
          setCrossResult(fullData); setResultKind('cross'); setStage('result');
          try { window.localStorage.removeItem(PENDING_JOB_KEY); } catch (_) {}
          await onWorkspaceChange?.();
          return;
        }
        if (['error', 'failed', 'interrupted'].includes(payload.status)) {
          throw new Error(payload.error || 'La Cross Analyse a été interrompue.');
        }
        setProgress(Math.min(95, Math.round(((attempt + 1) / 160) * 100)));
        if (payload.step) setStep(payload.step);
      }
      throw new Error('La Cross Analyse prend plus de temps que prévu.');
    } catch (error) {
      try { window.localStorage.removeItem(PENDING_JOB_KEY); } catch (_) {}
      if (!aliveRef.current) return;
      setStage('error'); setErrorMsg(error.message || 'Une erreur est survenue.');
    } finally {
      crossPollingRef.current = false;
    }
  }

  async function launchCrossAnalysis() {
    const sources = crossSources.slice();
    const pendingUrl = crossUrl.trim();
    if (pendingUrl && crossPreviewCount > 0 && !sources.some(source => source.url === pendingUrl)) {
      sources.push({ url: pendingUrl });
    }
    if (sources.length < CROSS_MIN_SOURCES || sources.length > CROSS_MAX_SOURCES) return;

    setCrossModalOpen(false);
    setStage('loading'); setResultKind('cross'); setProgress(0); setStep('Lecture des réactions du marché…'); setErrorMsg('');

    try {
      const response = await fetchV2('/api/v2/agents/psychologue/cross-analyses', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sources: sources.map(source => ({ url: source.url })), folder_id: workspace?.folder_id || undefined }),
      });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const data = await readApiPayload(response, 'Le lancement de la Cross Analyse');
      if (!response.ok || data?.error) throw new Error(data?.error || 'Le lancement a échoué.');
      try { window.localStorage.setItem(PENDING_JOB_KEY, JSON.stringify({ id: data.job_id, crossId: data.cross_analysis_id, t0: Date.now() })); } catch (_) {}
      await pollCrossAnalysis(data.cross_analysis_id);
    } catch (error) {
      setStage('error'); setErrorMsg(error.message || 'Une erreur est survenue.');
    }
  }

  function reset() {
    setStage('input'); setResult(null); setCrossResult(null); setErrorMsg('');
    setUrl(''); setManualText(''); setPreviewCount(0);
    setTab('link'); setPlatform('youtube'); setFile(null); setUploading(false);
    setStatusMsg('Collez le lien d’une vidéo YouTube.'); setStatusTone('');
    setCrossSources([]); setCrossUrl(''); setCrossPreviewCount(0);
    setCrossStatusMsg('Collez le lien d’une vidéo YouTube.'); setCrossStatusTone('');
  }

  if (stage === 'loading') return <PsychoLoading progress={progress} step={step} />;
  if (stage === 'error') return <PsychoError message={errorMsg} onRetry={reset} />;
  if (stage === 'result' && resultKind === 'cross' && crossResult) return <PsychoCrossResult data={crossResult} onReset={reset} />;
  if (stage === 'result' && result) return <PsychoResult data={result} onReset={reset} onGoToStratege={goToStratege} />;

  return <>
    <PsychoInput
      tab={tab} onTabChange={changeTab}
      platform={platform} onPlatformChange={changePlatform}
      url={url} onUrlChange={setUrl}
      manualText={manualText} onManualTextChange={setManualText}
      checking={checking} onCheck={checkLink}
      statusMsg={statusMsg} statusTone={statusTone}
      previewCount={previewCount}
      file={file} uploading={uploading}
      onFilePick={picked => uploadFile(picked)}
      onColumnChange={column => uploadFile(file?.raw, column)}
      onLaunch={launch}
      onOpenCross={() => setCrossModalOpen(true)}
    />
    {crossModalOpen && <PsychoCrossModal
      sources={crossSources}
      url={crossUrl} onUrlChange={setCrossUrl}
      checking={crossChecking} onCheck={checkCrossLink}
      statusMsg={crossStatusMsg} statusTone={crossStatusTone}
      previewCount={crossPreviewCount}
      onAddSource={addCrossSource} onRemoveSource={removeCrossSource}
      onLaunch={launchCrossAnalysis} onClose={closeCrossModal}
    />}
  </>;
}
