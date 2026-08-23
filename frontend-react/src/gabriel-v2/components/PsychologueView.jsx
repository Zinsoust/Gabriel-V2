import React, { useEffect, useMemo, useRef, useState } from 'react';
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
   positions, personas), et la Cross Analyse complète (espace de saisie
   intégré pour 2-5 vidéos + écran de résultat : conclusion générale, vidéos comparées,
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

function youtubeIdFromUrl(raw) {
  const value = String(raw || '').trim();
  return value.match(/[?&]v=([\w-]{6,})/)?.[1]
    || value.match(/youtu\.be\/([\w-]{6,})/)?.[1]
    || value.match(/\/shorts\/([\w-]{6,})/)?.[1]
    || null;
}

function makeSourcePreview(raw, platform) {
  const url = String(raw || '').trim();
  if (!url) return null;
  const config = LINK_SOURCES[platform];
  if (!config) return null;

  if (platform === 'youtube') {
    const id = youtubeIdFromUrl(url);
    if (!id) return null;
    return {
      url, source: config.label, title: `Vidéo YouTube · ${id}`,
      subtitle: 'Commentaires et discussions publiques',
      thumbnail: `https://i.ytimg.com/vi/${id}/hqdefault.jpg`,
    };
  }

  const looksLikeUrl = /^(https?:\/\/)?[\w-]+(\.[\w-]+)+\S*$/i.test(url);
  if (!looksLikeUrl) return null;
  return {
    url, source: config.label, title: config.label === 'Instagram' ? 'Publication Instagram' : 'Vidéo TikTok',
    subtitle: 'Commentaires et discussions publiques', thumbnail: null,
  };
}

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
  onLaunch,
  crossMode, crossSources, onToggleCross, onAddCrossSource,
  onRemoveCrossSource, onMoveCrossSource, onClearCrossSources, onLaunchCross,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const linkReady = Boolean(LINK_SOURCES[platform]) && previewCount > 0;
  const manualCount = manualText.trim().split('\n').filter(Boolean).length;
  const canLaunch = tab === 'link' ? linkReady
    : tab === 'manual' ? manualCount >= 3
    : Boolean(file && file.count >= 3);
  const config = LINK_SOURCES[platform];
  const sourcePreview = useMemo(() => tab === 'link' ? makeSourcePreview(url, platform) : null, [tab, url, platform]);
  const duplicateCrossSource = Boolean(sourcePreview && crossSources.some(source => source.url === sourcePreview.url));
  const canAddCrossSource = Boolean(crossMode && sourcePreview && !duplicateCrossSource && crossSources.length < CROSS_MAX_SOURCES);
  const canLaunchCross = crossMode && crossSources.length >= CROSS_MIN_SOURCES;
  const currentLabel = tab === 'manual' ? 'Commentaires'
    : tab === 'file' ? 'Fichier'
    : (config?.label || 'Google');
  const currentMark = tab === 'manual' ? '≡'
    : tab === 'file' ? '↥'
    : (config?.mark || 'G');
  const canSubmit = crossMode
    ? canAddCrossSource || (canLaunchCross && !url.trim())
    : tab === 'link' ? Boolean(config && url.trim()) : canLaunch;
  const submitLabel = crossMode
    ? (canAddCrossSource ? 'Ajouter cette audience' : `Comparer ${crossSources.length} audiences`)
    : tab === 'link' && !linkReady ? 'Vérifier le lien' : "Lancer l'analyse";

  function selectSource(next) {
    setMenuOpen(false);
    if (next === 'manual') { onTabChange('manual'); return; }
    if (next === 'file') { onTabChange('file'); return; }
    onTabChange('link');
    onPlatformChange(next);
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (crossMode) {
      if (canAddCrossSource) onAddCrossSource(sourcePreview);
      else if (canLaunchCross && !url.trim()) onLaunchCross();
      return;
    }
    if (tab === 'link') {
      if (linkReady) onLaunch();
      else if (config && url.trim()) onCheck();
      return;
    }
    if (canLaunch) onLaunch();
  }

  return <section className="gv2-psy-input gv2-psy-landing">
    <div className="gv2-psy-landing-copy">
      <span className="gv2-psy-eyebrow">Le Psychologue</span>
      <h1>Découvrez la psychologie de votre marché.</h1>
      <p>Comprenez ce qui pousse vos clients à acheter, hésiter ou partir. Décidez avec une longueur d’avance.</p>
    </div>

    <div className={`gv2-psy-workspace${crossMode ? ' is-cross' : ''}${sourcePreview ? ' has-preview' : ''}${crossSources.length ? ' has-sources' : ''}`}>
      {crossMode && crossSources.length > 0 && <div className="gv2-psy-queue" aria-label="Audiences à comparer">
        <div className="gv2-psy-queue-items">
          {crossSources.map((source, index) => <div className="gv2-psy-queue-chip" key={source.url}>
            <strong>Audience {index + 1}</strong>
            <span>{source.source || 'YouTube'}</span>
            <span className="gv2-psy-queue-title" title={source.title || source.label || source.url}>{source.title || source.label || source.url}</span>
            <button type="button" onClick={() => onMoveCrossSource(index, -1)} disabled={index === 0} aria-label={`Déplacer l’audience ${index + 1} vers la gauche`} title="Déplacer vers la gauche">‹</button>
            <button type="button" onClick={() => onMoveCrossSource(index, 1)} disabled={index === crossSources.length - 1} aria-label={`Déplacer l’audience ${index + 1} vers la droite`} title="Déplacer vers la droite">›</button>
            <button type="button" onClick={() => onRemoveCrossSource(index)} aria-label={`Retirer l’audience ${index + 1}`} title="Retirer cette audience"><Icon name="close" size={13} /></button>
          </div>)}
        </div>
        <button type="button" className="gv2-psy-queue-clear" onClick={onClearCrossSources}>Tout effacer</button>
      </div>}

      <form className={`gv2-psy-composer${menuOpen ? ' is-menu-open' : ''}`} onSubmit={handleSubmit}>
        <div className="gv2-psy-source-picker">
          <button type="button" className="gv2-psy-source-trigger" onClick={() => setMenuOpen(open => !open)} aria-haspopup="listbox" aria-expanded={menuOpen} aria-label={`Source d'analyse : ${currentLabel}. Changer de source`}>
            <span className="gv2-psy-source-mark" aria-hidden="true">{currentMark}</span>
            <span>{currentLabel}</span>
            <Icon name="chevronDown" size={15} className={menuOpen ? 'is-open' : ''} />
          </button>
          {menuOpen && <div className="gv2-psy-source-menu" role="listbox" aria-label="Choisir une source">
            {Object.entries(LINK_SOURCES).map(([key, meta]) => <button key={key} type="button" role="option" aria-selected={tab === 'link' && platform === key} onClick={() => selectSource(key)}>
              <span className="gv2-psy-source-mark" aria-hidden="true">{meta.mark}</span>{meta.label}
              {tab === 'link' && platform === key && <Icon name="check" size={14} />}
            </button>)}
            <button type="button" role="option" aria-selected={tab === 'link' && platform === 'google'} onClick={() => selectSource('google')}><span className="gv2-psy-source-mark" aria-hidden="true">G</span>Google</button>
            <div className="gv2-psy-source-menu-separator" />
            <button type="button" role="option" aria-selected={tab === 'manual'} onClick={() => selectSource('manual')}><span className="gv2-psy-source-mark" aria-hidden="true">≡</span>Commentaires</button>
            <button type="button" role="option" aria-selected={tab === 'file'} onClick={() => selectSource('file')}><span className="gv2-psy-source-mark" aria-hidden="true">↥</span>Fichier</button>
          </div>}
        </div>

        <button type="button" className={`gv2-psy-cross-trigger${crossMode ? ' is-active' : ''}`} onClick={onToggleCross} aria-pressed={crossMode} aria-label="Cross Analyse — comparer plusieurs audiences">
          <Icon name="activity" size={15} />
          <span>Cross{crossSources.length ? ` ${crossSources.length}` : ''}</span>
        </button>
        <span className="gv2-psy-composer-separator" aria-hidden="true" />

        {tab === 'link' && <input className="gv2-psy-composer-field" type="url" value={url} disabled={!config}
          onChange={event => onUrlChange(event.target.value)}
          placeholder={crossMode ? 'Ajoutez une audience à comparer…' : (config ? config.placeholder : 'La collecte Google arrive prochainement…')} />}
        {tab === 'manual' && <textarea className="gv2-psy-composer-field gv2-psy-composer-textarea" value={manualText} onChange={event => onManualTextChange(event.target.value)} placeholder="Collez vos commentaires ici, un par ligne…" rows={1} />}
        {tab === 'file' && <label className="gv2-psy-composer-file">
          <input type="file" accept=".csv,.xlsx,.xls,.json,.txt" hidden onChange={event => onFilePick(event.target.files && event.target.files[0])} />
          <Icon name="paperclip" size={17} />
          <span>{uploading ? 'Lecture du fichier…' : file ? file.name : 'Ajoutez un fichier de commentaires'}</span>
        </label>}
        {tab === 'link' && crossMode && sourcePreview && <span className={`gv2-psy-inline-recognized${duplicateCrossSource ? ' is-duplicate' : ''}`}><Icon name={duplicateCrossSource ? 'close' : 'check'} size={16} />{duplicateCrossSource ? 'Déjà ajoutée' : 'Lien reconnu'}</span>}

        <button type="submit" className={`gv2-psy-composer-submit${crossMode && canSubmit ? ' is-cross-add' : ''}`} disabled={checking || uploading || !canSubmit} aria-label={submitLabel} title={submitLabel}>
          <Icon name={checking || uploading ? 'refresh' : crossMode && canAddCrossSource ? 'plus' : 'send'} size={20} className={checking || uploading ? 'gv2-spin' : ''} />
        </button>
      </form>

      {sourcePreview && <div className="gv2-psy-preview" aria-live="polite">
        {sourcePreview.thumbnail ? <img src={sourcePreview.thumbnail} alt={`Vignette de ${sourcePreview.title}`} /> : <span className="gv2-psy-preview-fallback">{sourcePreview.source}</span>}
        <div><strong>{sourcePreview.title}</strong><span>{sourcePreview.source} — {sourcePreview.subtitle}</span></div>
      </div>}
      {crossMode && crossSources.length > 0 && <div className="gv2-psy-cross-ready" role="status">
        <span>{crossSources.length < CROSS_MIN_SOURCES ? `Ajoutez encore ${CROSS_MIN_SOURCES - crossSources.length} audience pour lancer la Cross Analyse.` : `Cross Analyse prête — ${crossSources.length} audiences à croiser.`}</span>
        {canLaunchCross && <button type="button" onClick={onLaunchCross}><Icon name="activity" size={16} />Comparer {crossSources.length} audiences <span aria-hidden="true">→</span></button>}
      </div>}
    </div>

    {tab === 'manual' && <div className="gv2-psy-composer-meta"><span>Un commentaire par ligne · Minimum 3</span><span>{manualCount}</span></div>}
    {tab === 'file' && <>
      {file && file.columns && file.columns.length > 1 && <label className="gv2-psy-column-picker">
        <span>Colonne à analyser</span>
        <select value={file.column || ''} onChange={event => onColumnChange(event.target.value)}>{file.columns.map(col => <option key={col} value={col}>{col}</option>)}</select>
      </label>}
      <div className="gv2-psy-composer-meta"><span>{file ? (file.warning || `${file.count} commentaire${file.count === 1 ? '' : 's'} lu${file.count === 1 ? '' : 's'}`) : 'CSV, Excel, JSON ou TXT · 5 Mo maximum'}</span>{file && <span>{file.count}</span>}</div>
    </>}

    <div className="gv2-psy-composer-status" role="status">
      <span className={statusTone ? `is-${statusTone}` : ''}>{tab === 'link' ? statusMsg : (statusMsg || 'Prêt à analyser votre audience.')}</span>
      {!crossMode && <button type="button" onClick={onToggleCross}><Icon name="activity" size={16} />Comparer plusieurs audiences <span aria-hidden="true">→</span></button>}
    </div>
  </section>;
}

/* ── Chargement / Erreur ─────────────────────────────────────────────── */

function PsychoLoading({ progress, step, isCross, crossSources }) {
  const phase = progress < 35 ? 0 : progress < 70 ? 1 : 2;
  const loadingSources = isCross ? crossSources : [];
  return <section className="gv2-psy-input gv2-psy-landing gv2-psy-loading-workspace">
    <div className="gv2-psy-workspace is-cross is-loading">
      {loadingSources.length > 0 && <div className="gv2-psy-queue" aria-label="Audiences en cours d’analyse">
        <div className="gv2-psy-queue-items">{loadingSources.map((source, index) => <div className="gv2-psy-queue-chip is-static" key={source.url}>
          <strong>Audience {index + 1}</strong><span>{source.source || 'YouTube'}</span><span className="gv2-psy-queue-title">{source.title || source.label || source.url}</span>
        </div>)}</div>
      </div>}
      <div className="gv2-psy-composer gv2-psy-composer-loading" aria-busy="true">
        <div className="gv2-psy-source-trigger"><span className="gv2-psy-source-mark">▶</span><span>YouTube</span><Icon name="chevronDown" size={15} /></div>
        {isCross && <div className="gv2-psy-cross-trigger is-active"><Icon name="activity" size={15} /><span>Cross {crossSources.length}</span></div>}
        <span className="gv2-psy-composer-separator" aria-hidden="true" />
        <span className="gv2-psy-composer-field">{isCross ? 'Les audiences sont en cours de comparaison…' : 'Votre audience est en cours de lecture…'}</span>
        <span className="gv2-psy-composer-submit gv2-psy-loading-submit"><span className="gv2-psy-loading-spinner" /></span>
      </div>
      <div className="gv2-psy-analysis-stages" aria-label="Étapes de l’analyse">
        {['Collecte', 'Analyse', 'Interprétation'].map((label, index) => <span key={label} className={index === phase ? 'is-active' : index < phase ? 'is-complete' : ''}>{label}</span>)}
      </div>
    </div>
    <div className="gv2-psy-loading-status" role="status">
      <div><strong>{isCross ? `Cross Analyse en cours — ${crossSources.length} audiences comparées.` : 'Analyse en cours — lecture des commentaires.'}</strong><span>{step || 'Gabriel analyse votre audience…'}</span></div>
      <span className="gv2-psy-loading-pct">{progress}%</span>
    </div>
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

/* ── Blocs de restitution ─────────────────────────────────────────────
 *
 * Le backend produit bien plus que ce que l'écran montrait : interprétations
 * psychologique et socio-culturelle, réalité intérieure de l'audience,
 * aspirations, signaux marketing, personas complets. Tout arrivait déjà dans
 * la réponse — seul l'affichage manquait.
 *
 * Chaque bloc s'efface s'il n'a pas de donnée : un rapport pauvre reste
 * lisible au lieu d'afficher une section à trous.
 */

function Section({ title, hint, children }) {
  return <div className="gv2-psy-section">
    <div className="gv2-psy-section-title">{title}</div>
    {hint && <p className="gv2-psy-section-hint">{hint}</p>}
    {children}
  </div>;
}

/** Liste de traits courts — frustrations, peurs, désirs… */
function TraitList({ items, tone }) {
  const clean = (Array.isArray(items) ? items : []).filter(Boolean);
  if (!clean.length) return null;
  return <ul className={`gv2-psy-traits${tone ? ` is-${tone}` : ''}`}>
    {clean.map((item, i) => <li key={i}>{esc(String(item))}</li>)}
  </ul>;
}

/** Un groupe de traits, masqué si vide. */
function TraitGroup({ label, items, tone }) {
  const clean = (Array.isArray(items) ? items : []).filter(Boolean);
  if (!clean.length) return null;
  return <div className="gv2-psy-trait-group">
    <div className="gv2-psy-trait-label">{label}</div>
    <TraitList items={clean} tone={tone} />
  </div>;
}

/** Une phrase attribuée à un champ nommé. */
function Statement({ label, text }) {
  const value = String(text || '').trim();
  if (!value) return null;
  return <div className="gv2-psy-statement">
    <div className="gv2-psy-statement-label">{label}</div>
    <p>{esc(value)}</p>
  </div>;
}

/** Bloc d'interprétation — psychologique ou socio-culturelle. */
function Interpretation({ title, data }) {
  const d = data || {};
  const insight = String(d.main_insight || '').trim();
  const mecanismes = Array.isArray(d.detected_mechanisms) ? d.detected_mechanisms : [];
  const rien = !insight && !mecanismes.length && !(d.fears || []).length
    && !(d.desires || []).length && !(d.beliefs || []).length
    && !(d.decision_drivers || []).length;
  if (rien) return null;

  return <div className="gv2-psy-card gv2-psy-interp">
    <div className="gv2-psy-interp-head">
      <span className="gv2-psy-interp-title">{title}</span>
      {typeof d.confidence_score === 'number' && (
        <span className="gv2-psy-interp-conf">
          confiance {Math.round(d.confidence_score * 100)}%
        </span>
      )}
    </div>
    {insight && <p className="gv2-psy-interp-insight">{esc(insight)}</p>}

    {mecanismes.length > 0 && <div className="gv2-psy-mechanisms">
      {mecanismes.filter(m => m && m.mechanism).map((m, i) => <div className="gv2-psy-mechanism" key={i}>
        <div className="gv2-psy-mechanism-head">
          <strong>{esc(m.mechanism)}</strong>
          {typeof m.confidence === 'number' && <span>{Math.round(m.confidence * 100)}%</span>}
        </div>
        {m.evidence && <p>{esc(m.evidence)}</p>}
      </div>)}
    </div>}

    <div className="gv2-psy-trait-cols">
      <TraitGroup label="Peurs" items={d.fears} tone="neg" />
      <TraitGroup label="Désirs" items={d.desires} tone="pos" />
      <TraitGroup label="Frustrations" items={d.frustrations} tone="neg" />
      <TraitGroup label="Croyances actives" items={d.beliefs} />
      <TraitGroup label="Facteurs de décision" items={d.decision_drivers} tone="pos" />
    </div>
  </div>;
}

/* ── Blocs mesurés du tableau de bord ─────────────────────────────────── */

/** Une métrique chiffrée avec sa lecture en clair. */
function Metric({ label, value, hint, tone }) {
  if (value == null || value === '') return null;
  return <div className="gv2-psy-metric">
    <div className="gv2-psy-metric-lbl">{label}</div>
    <div className={`gv2-psy-metric-val${tone ? ` is-${tone}` : ''}`}>{value}</div>
    {hint && <div className="gv2-psy-metric-hint">{esc(hint)}</div>}
  </div>;
}

/** Signaux fréquents : frustrations, attentes, objections. */
function SignalColumn({ title, items, tone }) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!list.length) return null;
  return <div className={`gv2-psy-signal-col is-${tone}`}>
    <div className="gv2-psy-signal-col-title">{title}</div>
    {list.map((item, i) => <div className="gv2-psy-signal-item" key={i}>
      <div className="gv2-psy-signal-head">
        <span>{esc(item.signal || item.label || '')}</span>
        <span className="gv2-psy-signal-num">{item.pct != null ? `${item.pct}%` : ''} {item.count != null ? `· ${item.count} cmnt` : ''}</span>
      </div>
      {(item.examples || []).slice(0, 1).map((ex, j) => <p key={j}>{esc(ex)}</p>)}
    </div>)}
  </div>;
}

/** Un groupe détecté dans l'audience (cluster). */
function AudienceGroup({ groupe }) {
  const tokens = Array.isArray(groupe.top_tokens) ? groupe.top_tokens : [];
  const samples = Array.isArray(groupe.samples) ? groupe.samples : [];
  return <div className="gv2-psy-group">
    <div className="gv2-psy-group-head">
      <span className="gv2-psy-group-pct">{groupe.pct != null ? `${groupe.pct}%` : ''}</span>
      <span className="gv2-psy-group-count">{groupe.size != null ? `${groupe.size} commentaires` : ''}</span>
      <div className="gv2-psy-group-tags">
        {groupe.likes_pct != null && <span>♥ {groupe.likes_pct}%</span>}
        {groupe.stance && <span>{esc(String(groupe.stance))}</span>}
        {groupe.emotion && <span>{esc(String(groupe.emotion))}</span>}
      </div>
    </div>
    {tokens.length > 0 && <div className="gv2-psy-group-tokens">
      {tokens.map((t, i) => <span key={i}>{esc(String(t))}</span>)}
    </div>}
    {samples.slice(0, 2).map((sample, i) => <blockquote key={i}>{esc(String(sample))}</blockquote>)}
  </div>;
}

/** Un livrable statistique : conclusion, données, signaux, sens, confiance. */
function DataInsight({ title, data }) {
  const d = data || {};
  const conclusion = String(d.conclusion || '').trim();
  if (!conclusion) return null;
  const signaux = Array.isArray(d.signaux) ? d.signaux.filter(Boolean) : [];
  const conf = typeof d.score_confiance === 'number' ? d.score_confiance : null;

  return <div className="gv2-psy-card gv2-psy-insight">
    <div className="gv2-psy-insight-title">{title}</div>
    <p className="gv2-psy-insight-conclusion">{esc(conclusion)}</p>
    {d.indicateur_statistique && <div className="gv2-psy-insight-row">
      <span className="gv2-psy-insight-key">Données</span>
      <span>{esc(String(d.indicateur_statistique))}</span>
    </div>}
    {signaux.length > 0 && <div className="gv2-psy-insight-row">
      <span className="gv2-psy-insight-key">Signaux</span>
      <span className="gv2-psy-insight-tokens">
        {signaux.map((t, i) => <span key={i}>{esc(String(t))}</span>)}
      </span>
    </div>}
    {d.interpretation && <div className="gv2-psy-insight-row">
      <span className="gv2-psy-insight-key">Sens</span>
      <span>{esc(String(d.interpretation))}</span>
    </div>}
    {conf != null && <div className="gv2-psy-conf">
      <span>Confiance</span>
      <div className="gv2-psy-conf-track"><div className="gv2-psy-conf-fill" style={{ width: `${Math.round(conf * 100)}%` }} /></div>
      <span className="gv2-psy-conf-val">{conf.toFixed(2)}</span>
    </div>}
  </div>;
}

/** Une entrée de la grille psychologique : observation → sens → action. */
function GridEntry({ label, data }) {
  const d = data || {};
  if (!d.observation && !d.interpretation && !d.implication) return null;
  return <div className="gv2-psy-card gv2-psy-grid-entry">
    <div className="gv2-psy-grid-title">{label}</div>
    {d.observation && <div className="gv2-psy-grid-row">
      <span className="gv2-psy-grid-key">Obs.</span><span>{esc(String(d.observation))}</span>
    </div>}
    {d.interpretation && <div className="gv2-psy-grid-row">
      <span className="gv2-psy-grid-key">Sens</span><span>{esc(String(d.interpretation))}</span>
    </div>}
    {d.implication && <div className="gv2-psy-grid-row">
      <span className="gv2-psy-grid-key">Action</span><span>{esc(String(d.implication))}</span>
    </div>}
  </div>;
}

// Ordre et libellés repris du livrable d'origine, sans réinvention.
const LIVRABLES = [
  ['lecture_sujet', 'Lecture du sujet'],
  ['ce_qui_rassemble', 'Ce qui rassemble'],
  ['ce_qui_divise', 'Ce qui divise'],
  ['tension_centrale', 'Tension centrale'],
  ['synthese_psychologique', 'Synthèse psychologique'],
];

const GRILLE = [
  ['ce_qu_ils_ressentent', "Ce qu'ils ressentent"],
  ['ce_qu_ils_veulent', "Ce qu'ils veulent"],
  ['ce_qu_ils_refusent', "Ce qu'ils refusent"],
  ['ce_qui_les_bloque', 'Ce qui les bloque'],
  ['ce_qui_les_rassure', 'Ce qui les rassure'],
  ['ce_qui_les_divise', 'Ce qui les divise'],
  ['ce_qui_les_unit', 'Ce qui les unit'],
  ['ce_qu_ils_valorisent', "Ce qu'ils valorisent"],
  ['ce_qu_ils_attendent_comme_preuve', 'Preuve attendue'],
  ['quelle_opportunite_emerge', 'Opportunité émergente'],
];

/** Onglets de résultat — même découpage que le livrable d'origine. */
function ResultTabs({ active, onChange, tabs }) {
  return <div className="gv2-psy-result-tabs" role="tablist">
    {tabs.map(tab => <button
      key={tab.id}
      type="button"
      role="tab"
      aria-selected={active === tab.id}
      className={active === tab.id ? 'is-active' : ''}
      onClick={() => onChange(tab.id)}
    >{tab.label}</button>)}
  </div>;
}

function PsychoResult({ data, onReset, onGoToStratege }) {
  const [tab, setTab] = useState('dashboard');

  const db = data.dashboard || {};
  const meta = data.meta || {};
  const brief = data.brief || {};
  const psy = data.psychologie || {};
  const asp = data.aspirations || {};
  const mkt = data.marketing || {};
  const interp = data.interpretation || {};
  const kpis = data.kpis || {};
  const livr = data.livrables_statistiques || {};
  const grille = data.grille_psychologique || {};
  const recos = data.recommandations || {};

  // Blocs mesurés du dashboard — tous produits par le backend, aucun inventé.
  const sf = db.signaux_frequents || {};
  const groupes = Array.isArray(db.groupes) ? db.groupes : [];
  const sujets = Array.isArray(db.sujets_recurrents) ? db.sujets_recurrents : [];
  const lexique = db.lexique || {};
  const champs = Array.isArray(db.lexical_fields) ? db.lexical_fields : [];
  const pol = db.polarisation_detail || {};
  const fib = db.fiabilite || {};
  const ws = db.weighted_sentiment || {};
  const wp = db.weighted_polarization || {};
  const res = db.resonance_by_stance || {};
  const ard = db.argument_density || {};
  const mok = db.mockery_signals || {};
  const iry = db.irony_signals || {};
  const rt = db.resume_tendances || {};

  // Les commentaires les plus amplifiés : reconstitués depuis les exemples
  // déjà présents dans les signaux, faute d'un bloc dédié côté backend.
  const topComments = Array.isArray(db.top_comments) ? db.top_comments : [];

  const pos = db.positions || {};
  const emotions = Array.isArray(db.emotion_distribution)
    ? db.emotion_distribution
    : Object.entries(db.emotion_distribution || {}).map(([emotion, pct]) => ({ emotion, pourcentage: pct }));
  const personas = Array.isArray(data.personas) ? data.personas : [];
  const synthese = brief.qui || brief.synthese || '';
  const insight = brief.insight || brief.insight_cle || '';
  const action = brief.action || brief.action_prioritaire || '';

  // Un onglet vide ne doit pas être proposé : mieux vaut deux onglets pleins
  // que trois dont un déçoit.
  const aInterpretation = Boolean(
    interp.psychologique || interp.socio_culturelle ||
    Object.keys(psy).length || Object.keys(asp).length || Object.keys(mkt).length);
  const tabs = [
    { id: 'dashboard', label: 'Tableau de bord' },
    ...(aInterpretation ? [{ id: 'interpretation', label: 'Interprétation' }] : []),
    ...(personas.length ? [{ id: 'personas', label: `Personas (${personas.length})` }] : []),
  ];
  const actif = tabs.some(t => t.id === tab) ? tab : 'dashboard';

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
      <div className="gv2-psy-hero-label">Ce que dit cette audience</div>
      <p className="gv2-psy-hero-text">{synthese}</p>
      <div className="gv2-psy-hero-pills">
        {insight && <span><strong>Insight ·</strong> {insight}</span>}
        {action && <span><strong>Action ·</strong> {action}</span>}
      </div>
    </div>}

    {tabs.length > 1 && <ResultTabs active={actif} onChange={setTab} tabs={tabs} />}

    {actif === 'dashboard' && <>
      <div className="gv2-psy-stats-grid">
        <StatChip value={meta.total_commentaires || 0} count={`${meta.commentaires_analyses || 0} qualifiés`} label="Collectés" />
        <StatChip value={`${(pos.favorable || {}).pct || 0}%`} count={`${(pos.favorable || {}).count || 0} cmnt`} label="Favorables" tone="pos" />
        <StatChip value={`${(pos.oppose || {}).pct || 0}%`} count={`${(pos.oppose || {}).count || 0} cmnt`} label="Négatifs" tone="neg" />
        <StatChip value={`${(pos.neutre || {}).pct || 0}%`} count={`${(pos.neutre || {}).count || 0} cmnt`} label="Neutres" />
      </div>

      {Object.keys(kpis).length > 0 && <Section title="Indicateurs">
        <div className="gv2-psy-kpis">
          {Object.entries(kpis).map(([nom, valeur]) => {
            const score = valeur && typeof valeur === 'object' ? valeur.score : valeur;
            if (typeof score !== 'number') return null;
            return <div className="gv2-psy-kpi" key={nom}>
              <div className="gv2-psy-kpi-score">{Math.round(score)}</div>
              <div className="gv2-psy-kpi-name">{esc(nom)}</div>
              {valeur && valeur.lecture && <p>{esc(valeur.lecture)}</p>}
            </div>;
          })}
        </div>
      </Section>}

      {emotions.length > 0 && <Section title="Émotions détectées">
        <div className="gv2-psy-card gv2-psy-card--plain">
          {emotions.slice(0, 8).map((item, index) => <Bar key={index} label={item.emotion} pct={Math.round(item.pourcentage || item.pct || 0)} />)}
        </div>
      </Section>}

      {Object.keys(pos).length > 0 && <Section title="Répartition des positions">
        <div className="gv2-psy-card gv2-psy-card--plain">
          {Object.entries(pos).map(([key, value]) => <Bar key={key} label={key} pct={Math.round(value.pct || 0)} count={value.count} />)}
        </div>
      </Section>}

      {(db.tension_principale || db.tendance_dominante || db.dominant_desire) && (
        <Section title="Lecture d'ensemble">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <Statement label="Tension principale" text={db.tension_principale} />
            <Statement label="Tendance dominante" text={db.tendance_dominante} />
            <Statement label="Désir dominant" text={db.dominant_desire} />
            <Statement label="Signal dominant" text={db.signal_dominant} />
          </div>
        </Section>
      )}

      {topComments.length > 0 && (
        <Section title="Commentaires les plus likés"
                 hint="Les plus amplifiés par l'audience elle-même.">
          <div className="gv2-psy-quotes">
            {topComments.slice(0, 10).map((c, i) => <blockquote className="gv2-psy-quote" key={i}>
              <p>{esc(typeof c === 'string' ? c : (c.text || ''))}</p>
              {c && c.likes != null && <cite>♥ {c.likes}{c.author ? ` · ${esc(c.author)}` : ''}</cite>}
            </blockquote>)}
          </div>
        </Section>
      )}

      {(Object.keys(ws).length > 0 || Object.keys(wp).length > 0 || Object.keys(fib).length > 0) && (
        <Section title="Métriques pondérées par engagement"
                 hint="Un commentaire très liké pèse plus qu'un commentaire isolé.">
          <div className="gv2-psy-metrics">
            <Metric label="Sentiment pondéré" value={ws.score} hint={ws.interpretation} tone="pos" />
            <Metric label="Sentiment brut" value={ws.score_raw} hint="non pondéré (moyenne)" />
            <Metric label="Polarisation pondérée" value={wp.score} hint={wp.label} />
            <Metric label="Likes analysés" value={ws.total_likes} hint="engagement total mesuré" />
            <Metric label="Confiance" value={fib.label_confiance} hint={fib.commentaires_analyses != null ? `${fib.commentaires_analyses} commentaires retenus` : ''} />
            <Metric label="Hors sujet" value={fib.pct_hors_sujet != null ? `${fib.pct_hors_sujet}%` : null} hint={`${fib.commentaires_hors_sujet || 0} écartés`} />
          </div>
        </Section>
      )}

      {Object.keys(res).length > 0 && (
        <Section title="Résonance par camp & densité argumentative"
                 hint="Qui fait réagir, et qui argumente.">
          <div className="gv2-psy-card gv2-psy-card--plain">
            {Object.entries(res).map(([camp, v]) => <div className="gv2-psy-resonance" key={camp}>
              <span className="gv2-psy-resonance-camp">{esc(camp)}</span>
              <div className="gv2-psy-bar-track"><div className="gv2-psy-bar-fill" style={{ width: `${Math.min(100, v.pct || 0)}%` }} /></div>
              <span className="gv2-psy-resonance-pct">{v.pct}%</span>
              <span className="gv2-psy-resonance-likes">{v.likes} ♥</span>
              <span className="gv2-psy-resonance-words">
                {(ard[camp] || {}).avg_words != null ? `${ard[camp].avg_words} mots · ${ard[camp].label || ''}` : ''}
              </span>
            </div>)}
          </div>
        </Section>
      )}

      {groupes.length > 0 && (
        <Section title="Groupes détectés dans l'audience"
                 hint="Des sous-ensembles qui parlent de la même chose, avec les mêmes mots.">
          <div className="gv2-psy-groups">
            {groupes.map((g, i) => <AudienceGroup groupe={g} key={i} />)}
          </div>
        </Section>
      )}

      {sujets.length > 0 && (
        <Section title="Sujets récurrents">
          <div className="gv2-psy-card gv2-psy-card--plain">
            {sujets.map((sujet, i) => <div className="gv2-psy-topic" key={i}>
              <div className="gv2-psy-topic-id">
                <strong>{esc(String(sujet.theme || sujet.mot || ''))}</strong>
                <span>{sujet.pct != null ? `${sujet.pct}%` : ''} {sujet.count != null ? `· ${sujet.count} occurrences` : ''}</span>
              </div>
              {sujet.exemple && <p>{esc(String(sujet.exemple))}</p>}
            </div>)}
          </div>
        </Section>
      )}

      {(sf.frustrations || sf.attentes || sf.objections) && (
        <Section title="Frustrations · Attentes · Objections"
                 hint="Ce que l'audience exprime le plus souvent, avec ses mots.">
          <div className="gv2-psy-signal-cols">
            <SignalColumn title="Frustrations" items={sf.frustrations} tone="neg" />
            <SignalColumn title="Attentes & désirs" items={sf.attentes} tone="pos" />
            <SignalColumn title="Objections" items={sf.objections} tone="neg" />
          </div>
        </Section>
      )}

      {(Object.keys(mok).length > 0 || Object.keys(iry).length > 0) && (
        <Section title="Signaux de moquerie & ironie"
                 hint="Un enthousiasme ironique n'est pas de l'adhésion.">
          <div className="gv2-psy-metrics">
            <Metric label="Moquerie" value={`${mok.count || 0} (${mok.pct || 0}%)`} hint={mok.level} />
            <Metric label="Ironie" value={`${iry.count || 0} (${iry.pct || 0}%)`} hint={iry.level} />
          </div>
        </Section>
      )}

      {(Array.isArray(lexique.top_mots) && lexique.top_mots.length > 0) && (
        <Section title="Mots et expressions fréquents">
          <div className="gv2-psy-lex-cols">
            <div className="gv2-psy-card gv2-psy-card--plain">
              <div className="gv2-psy-trait-label">Mots les plus significatifs</div>
              <div className="gv2-psy-tokens">
                {lexique.top_mots.slice(0, 14).map((m, i) => <span key={i}>{esc(String(m.mot || m))}</span>)}
              </div>
            </div>
            {Array.isArray(lexique.top_bigrams) && lexique.top_bigrams.length > 0 && (
              <div className="gv2-psy-card gv2-psy-card--plain">
                <div className="gv2-psy-trait-label">Expressions fréquentes</div>
                <div className="gv2-psy-tokens">
                  {lexique.top_bigrams.slice(0, 12).map((b, i) => <span key={i}>
                    {esc(String(b.bigram || b.mot || b))}{b.count != null ? ` · ${b.count}` : ''}
                  </span>)}
                </div>
              </div>
            )}
          </div>
        </Section>
      )}

      {champs.length > 0 && (
        <Section title="Champs lexicaux détectés">
          <div className="gv2-psy-fields">
            {champs.map((champ, i) => <div className="gv2-psy-card gv2-psy-field" key={i}>
              <strong>{esc(String(champ.field || champ.nom || ''))}</strong>
              <div className="gv2-psy-field-meta">
                {champ.pct != null ? `${champ.pct}% des commentaires` : ''}
                {champ.count != null ? ` · ${champ.count} occurrences` : ''}
              </div>
              {Array.isArray(champ.tokens) && <div className="gv2-psy-tokens">
                {champ.tokens.slice(0, 5).map((t, j) => <span key={j}>{esc(String(t))}</span>)}
              </div>}
              {champ.exemple && <p>{esc(String(champ.exemple))}</p>}
            </div>)}
          </div>
        </Section>
      )}

      {pol.phrase && (
        <Section title="Polarisation de l'audience">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <p className="gv2-psy-polar-phrase">{esc(String(pol.phrase))}</p>
            {pol.label && <div className="gv2-psy-metric-hint">{esc(String(pol.label))}{pol.score != null ? ` · score ${pol.score}` : ''}</div>}
          </div>
        </Section>
      )}
    </>}

    {actif === 'interpretation' && <>
      {(recos.verite_de_l_audience || recos.message_central || recos.prochaines_etapes) && (
        <Section title="Recommandations stratégiques">
          <div className="gv2-psy-reco-cols">
            <div className="gv2-psy-card gv2-psy-card--plain">
              <Statement label="Vérité de l'audience" text={recos.verite_de_l_audience} />
              {recos.message_central && <div className="gv2-psy-reco-message">
                <div className="gv2-psy-statement-label">Message central</div>
                <blockquote>{esc(String(recos.message_central))}</blockquote>
              </div>}
              <Statement label="Insight stratégique" text={recos.insight_strategique_cle} />
            </div>
            {Array.isArray(recos.prochaines_etapes) && recos.prochaines_etapes.length > 0 && (
              <div className="gv2-psy-card gv2-psy-card--plain">
                <div className="gv2-psy-statement-label">Prochaines étapes</div>
                <ul className="gv2-psy-steps">
                  {recos.prochaines_etapes.map((etape, i) => <li key={i}>
                    {esc(typeof etape === 'string' ? etape
                        : [etape.horizon, etape.action].filter(Boolean).join(' : '))}
                  </li>)}
                </ul>
              </div>
            )}
          </div>
        </Section>
      )}

      {(brief.qui || brief.insight || brief.action) && (
        <Section title="Lecture instantanée">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <Statement label="Qui" text={brief.qui || brief.synthese} />
            <div className="gv2-psy-reco-cols">
              <Statement label="Insight clé" text={brief.insight || brief.insight_cle} />
              <Statement label="Action prioritaire" text={brief.action || brief.action_prioritaire} />
            </div>
          </div>
        </Section>
      )}

      {LIVRABLES.some(([cle]) => (livr[cle] || {}).conclusion) && (
        <Section title="Insights fondés sur données"
                 hint="Chaque lecture s'appuie sur un chiffre mesuré, pas sur une impression.">
          {LIVRABLES.map(([cle, titre]) => <DataInsight key={cle} title={titre} data={livr[cle]} />)}
        </Section>
      )}

      <Interpretation title="Lecture psychologique" data={interp.psychologique} />
      <Interpretation title="Lecture socio-culturelle" data={interp.socio_culturelle} />

      {GRILLE.some(([cle]) => grille[cle]) && (
        <Section title="Grille psychologique"
                 hint="Dix angles, chacun de l'observation mesurée jusqu'à l'action qu'elle appelle.">
          <div className="gv2-psy-grid">
            {GRILLE.map(([cle, label]) => <GridEntry key={cle} label={label} data={grille[cle]} />)}
          </div>
        </Section>
      )}

      {Object.keys(psy).length > 0 && <Section
        title="La réalité intérieure"
        hint="Ce que l'audience porte, au-delà de ce qu'elle dit.">
        <div className="gv2-psy-card gv2-psy-card--plain">
          <div className="gv2-psy-trait-cols">
            <TraitGroup label="Frustrations" items={psy.frustrations} tone="neg" />
            <TraitGroup label="Peurs implicites" items={psy.peurs_implicites} tone="neg" />
            <TraitGroup label="Désirs cachés" items={psy.desirs_caches} tone="pos" />
            <TraitGroup label="Motivations profondes" items={psy.motivations_profondes} tone="pos" />
            <TraitGroup label="Croyances limitantes" items={psy.croyances_limitantes} tone="neg" />
            <TraitGroup label="Croyances mobilisatrices" items={psy.croyances_mobilisatrices} tone="pos" />
            <TraitGroup label="Valeurs dominantes" items={psy.valeurs_dominantes} />
          </div>
          <Statement label="Mécanismes psychologiques" text={psy.mecanismes_psychologiques} />
          <Statement label="Tensions internes" text={psy.tensions_internes} />
          <Statement label="Besoins identitaires" text={psy.besoins_identitaires} />
          <Statement label="Rapport à l'argent" text={psy.rapport_argent} />
          <Statement label="Rapport au succès" text={psy.rapport_succes} />
          <Statement label="Rapport à l'autorité" text={psy.rapport_autorite} />
        </div>
      </Section>}

      {Object.keys(asp).length > 0 && <Section
        title="Aspirations"
        hint="Ce vers quoi cette audience tend, même sans le formuler.">
        <div className="gv2-psy-card gv2-psy-card--plain">
          <Statement label="Ce qu'ils veulent devenir" text={asp.ce_qu_ils_veulent_devenir} />
          <Statement label="Ce qu'ils veulent construire" text={asp.ce_qu_ils_veulent_construire} />
          <Statement label="Ce qu'ils veulent transmettre" text={asp.ce_qu_ils_veulent_transmettre} />
          <Statement label="Ce qu'ils veulent protéger" text={asp.ce_qu_ils_veulent_proteger} />
          <Statement label="Ce qu'ils veulent éviter" text={asp.ce_qu_ils_veulent_eviter} />
          <Statement label="Appel intérieur" text={asp.appel_interieur} />
          <Statement label="Vision de leur meilleur moi" text={asp.vision_de_leur_meilleur_moi} />
          <div className="gv2-psy-trait-cols">
            <TraitGroup label="Ambitions" items={asp.ambitions} tone="pos" />
            <TraitGroup label="Freins" items={asp.freins_aux_aspirations} tone="neg" />
          </div>
        </div>
      </Section>}

      {Object.keys(mkt).length > 0 && <Section
        title="Signaux exploitables"
        hint="Ce que cette lecture ouvre comme prises concrètes.">
        <div className="gv2-psy-card gv2-psy-card--plain">
          <Statement label="Positionnement recommandé" text={mkt.positionnement_recommande} />
          <div className="gv2-psy-trait-cols">
            <TraitGroup label="Objections visibles" items={mkt.objections_visibles} tone="neg" />
            <TraitGroup label="Objections invisibles" items={mkt.objections_invisibles} tone="neg" />
            <TraitGroup label="Déclencheurs émotionnels" items={mkt.declencheurs_emotionnels} tone="pos" />
            <TraitGroup label="Leviers de conversion" items={mkt.leviers_de_conversion} tone="pos" />
            <TraitGroup label="Opportunités d'offre" items={mkt.opportunites_offre} tone="pos" />
            <TraitGroup label="Opportunités de contenu" items={mkt.opportunites_contenu} tone="pos" />
            <TraitGroup label="Sujets qui attirent" items={mkt.sujets_qui_attirent} />
            <TraitGroup label="Sujets qui divisent" items={mkt.sujets_qui_divisent} tone="neg" />
            <TraitGroup label="Risques de communication" items={mkt.risques_communication} tone="neg" />
          </div>
          <TraitGroup label="Accroches performantes" items={mkt.hooks_performants} tone="pos" />
        </div>
      </Section>}
    </>}

    {actif === 'personas' && <div className="gv2-psy-persona-grid is-full">
      {personas.map((persona, index) => <div className="gv2-psy-persona-card" key={index}>
        <div className="gv2-psy-persona-head">
          <div className="gv2-psy-persona-name">{persona.nom || `Persona ${index + 1}`}</div>
          {persona.poids && <span className="gv2-psy-persona-weight">{esc(String(persona.poids))}</span>}
        </div>
        {(persona.age || persona.genre || persona.metier) && <div className="gv2-psy-persona-meta">{[persona.age ? `${persona.age} ans` : '', persona.genre, persona.metier].filter(Boolean).join(' · ')}</div>}
        {persona.emotion_dominante_mesuree && <div className="gv2-psy-persona-emo">{esc(persona.emotion_dominante_mesuree)}</div>}
        {persona.histoire_interieure && <p className="gv2-psy-persona-quote">"{esc(persona.histoire_interieure)}"</p>}
        <Statement label="État d'esprit" text={persona.etat_esprit} />
        <Statement label="Vision du monde" text={persona.vision_monde} />
        <div className="gv2-psy-trait-cols">
          <TraitGroup label="Frustrations" items={persona.frustrations} tone="neg" />
          <TraitGroup label="Peurs" items={persona.peurs} tone="neg" />
          <TraitGroup label="Désirs" items={persona.desirs} tone="pos" />
          <TraitGroup label="Aspirations" items={persona.aspirations} tone="pos" />
        </div>
        <Statement label="Objection principale" text={persona.objection_principale} />
        <Statement label="Ce qui le ferait acheter" text={persona.ce_qui_le_ferait_acheter} />
        <Statement label="Message à lui adresser" text={persona.message_a_lui_dire} />
      </div>)}
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

  const [crossMode, setCrossMode] = useState(false);
  const [crossSources, setCrossSources] = useState([]);

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
    if (next !== 'link') setCrossMode(false);
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
    if (next !== 'youtube') setCrossMode(false);
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

  function changeUrl(next) {
    setUrl(next);
    setPreviewCount(0);
    setStatusTone('');
    if (crossMode) {
      setStatusMsg('Le lien est reconnu dès que son identifiant vidéo est complet.');
      return;
    }
    const config = LINK_SOURCES[platform];
    if (config) setStatusMsg(`Collez le lien ${config.label}, puis vérifiez les commentaires disponibles.`);
  }

  function toggleCrossMode() {
    const next = !crossMode;
    setCrossMode(next);
    setTab('link');
    setPlatform('youtube');
    setUrl('');
    setPreviewCount(0);
    setStatusTone('');
    setStatusMsg(next
      ? 'Ajoutez 2 à 5 audiences YouTube pour comparer leurs conversations.'
      : 'Collez le lien d’une vidéo YouTube.');
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

  function addCrossSource(preview) {
    if (!preview || crossSources.length >= CROSS_MAX_SOURCES || crossSources.some(source => source.url === preview.url)) return;
    setCrossSources(current => [...current, { ...preview, label: preview.title }]);
    setUrl('');
    setPreviewCount(0);
    setStatusTone('');
    setStatusMsg('Audience ajoutée. Collez une autre vidéo ou lancez la comparaison.');
  }

  function removeCrossSource(index) {
    setCrossSources(current => current.filter((_, i) => i !== index));
  }

  function moveCrossSource(index, direction) {
    setCrossSources(current => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.length) return current;
      const next = current.slice();
      [next[index], next[destination]] = [next[destination], next[index]];
      return next;
    });
  }

  function clearCrossSources() {
    setCrossSources([]);
    setUrl('');
    setPreviewCount(0);
    setStatusTone('');
    setStatusMsg('Ajoutez 2 à 5 audiences YouTube pour comparer leurs conversations.');
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
    if (sources.length < CROSS_MIN_SOURCES || sources.length > CROSS_MAX_SOURCES) return;

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
    setCrossMode(false); setCrossSources([]);
  }

  let content = <PsychoInput
      tab={tab} onTabChange={changeTab}
      platform={platform} onPlatformChange={changePlatform}
      url={url} onUrlChange={changeUrl}
      manualText={manualText} onManualTextChange={setManualText}
      checking={checking} onCheck={checkLink}
      statusMsg={statusMsg} statusTone={statusTone}
      previewCount={previewCount}
      file={file} uploading={uploading}
      onFilePick={picked => uploadFile(picked)}
      onColumnChange={column => uploadFile(file?.raw, column)}
      onLaunch={launch}
      crossMode={crossMode} crossSources={crossSources}
      onToggleCross={toggleCrossMode}
      onAddCrossSource={addCrossSource}
      onRemoveCrossSource={removeCrossSource}
      onMoveCrossSource={moveCrossSource}
      onClearCrossSources={clearCrossSources}
      onLaunchCross={launchCrossAnalysis}
    />;

  if (stage === 'loading') content = <PsychoLoading progress={progress} step={step} isCross={resultKind === 'cross'} crossSources={crossSources} />;
  if (stage === 'error') content = <PsychoError message={errorMsg} onRetry={reset} />;
  if (stage === 'result' && resultKind === 'cross' && crossResult) content = <PsychoCrossResult data={crossResult} onReset={reset} />;
  if (stage === 'result' && result) content = <PsychoResult data={result} onReset={reset} onGoToStratege={goToStratege} />;

  return <div className="gv2-psy-view">{content}</div>;
}
