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
// Durées mesurées le 24/09/2026 : une Cross Analyse de deux vidéos a pris plus de
// 9 minutes, alors que l'écran abandonnait à 8. On attend au temps, pas au nombre d'essais.
const ANALYSIS_MAX_WAIT_MS = 20 * 60 * 1000;
const CROSS_MAX_WAIT_MS = 40 * 60 * 1000;
const ANALYSIS_EXPECTED_MS = 4 * 60 * 1000;
const CROSS_EXPECTED_MS = 10 * 60 * 1000;
const POLL_MS = 3000;
const MAX_NETWORK_FAILURES = 8;

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

/* Texte affiché tel quel : les marqueurs markdown (* et **) que le modèle
   laisse dans ses phrases n'ont aucun sens à l'écran, on les retire. Une liste
   arrivée là où une phrase était attendue est lue en entier. */
function esc(value) {
  if (Array.isArray(value)) return value.map(esc).filter(Boolean).join(' · ');
  return String(value ?? '').replace(/\*+/g, '');
}

// Le texte long généré par le LLM (executive_summary, noyau psychologique,
// descriptions de persona) utilise du markdown gras/italique léger.
function formatInline(value) {
  const text = (Array.isArray(value) ? value.map(v => String(v ?? '')).join(' · ') : String(value ?? ''))
    // Identifiants internes de signaux (« (cross:emotions:frustration) ») : du
    // bruit technique pour le lecteur, jamais une information.
    .replace(/\s*\((?:cross|signal|psy):[\w:.-]+\)/g, '');
  const chunks = text.split(/(\*\*[^*\n]+?\*\*|\*[^*\n]+?\*)/g);
  return chunks.map((chunk, index) => {
    if (/^\*\*[^*]+\*\*$/.test(chunk)) return <strong key={index}>{chunk.slice(2, -2)}</strong>;
    if (/^\*[^*]+\*$/.test(chunk)) return <em key={index}>{chunk.slice(1, -1)}</em>;
    // Un astérisque orphelin (marqueur jamais refermé par le modèle) n'a
    // aucun sens pour le lecteur : on le retire plutôt que de l'afficher.
    return chunk.replace(/\*+/g, '');
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
  recentAnalyses = [], onOpenAnalysis, onSuggest, onNavigateAgent,
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
    {/* Scène d'entrée : fond sombre qui se fond vers la page, titre sur deux
        lignes au plus, une phrase, une barre compacte centrée. */}
    <div className="gv2-psy-stage">
    <div className="gv2-psy-landing-copy">
      {/* Animation d'entrée : les mots du titre se révèlent un à un (flou →
          net), puis les trois objets de l'analyse s'allument tour à tour. */}
      <h1 className="gv2-psy-title-reveal">
        <span style={{ '--i': 0 }}>Psychologie</span> <span style={{ '--i': 1 }}>avancée.</span>
      </h1>
      <p className="gv2-psy-landing-subtitle">Découvrez <em style={{ '--k': 0 }}>le marché caché</em>, <em style={{ '--k': 1 }}>les peurs</em> et <em style={{ '--k': 2 }}>les aspirations</em> de votre audience.</p>
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

    <p className="gv2-psy-trust"><Icon name="check" size={14} />Aucune pensée devinée. Chaque lecture part de signaux observables.</p>
    </div>

    {onSuggest && <section className="gv2-psy-intents" aria-labelledby="gv2-psy-intents-title">
      <h2 id="gv2-psy-intents-title" className="gv2-psy-mono-label">Que voulez-vous comprendre ?</h2>
      <div className="gv2-psy-intents-grid">
        {INTENTIONS.map(intent => <button key={intent.id} type="button" className="gv2-psy-intent"
          onClick={() => onSuggest(intent.mode)}>
          <strong>{intent.titre}</strong>
          <span>{intent.detail}</span>
          <em>{intent.action} <span aria-hidden="true">→</span></em>
        </button>)}
      </div>
    </section>}

    {recentAnalyses.length > 0 && <section className="gv2-psy-recents" aria-labelledby="gv2-psy-recents-title">
      <h2 id="gv2-psy-recents-title" className="gv2-psy-mono-label">Analyses récentes</h2>
      <ul>
        {recentAnalyses.slice(0, 4).map(item => <li key={item.analysis_id}>
          <button type="button" onClick={() => onOpenAnalysis(item.analysis_id)}>
            <strong>{item.title || item.source || 'Analyse'}</strong>
            <span>{[item.source && item.source !== item.title ? item.source : '',
              item.nb_commentaires ? `${item.nb_commentaires} commentaires` : '',
              dateCourte(item.created_at)].filter(Boolean).join(' · ')}</span>
            <em>Rouvrir <span aria-hidden="true">→</span></em>
          </button>
        </li>)}
      </ul>
    </section>}

    {onNavigateAgent && <section className="gv2-psy-extensions" aria-label="Prolonger l’analyse">
      <span className="gv2-psy-mono-label">Après la lecture</span>
      <button type="button" onClick={() => onNavigateAgent('stratege')}><strong>Transformer en stratégie</strong><span>Ariane, stratège</span><span aria-hidden="true">→</span></button>
      <button type="button" onClick={() => onNavigateAgent('createur')}><strong>Transformer en contenu</strong><span>Le Créateur</span><span aria-hidden="true">→</span></button>
    </section>}
  </section>;
}

/* « Que voulez-vous comprendre ? » — chaque entrée correspond à une capacité
   réellement exécutée par le backend, et prépare la bonne source. Aucune
   promesse sans moteur derrière. */
const INTENTIONS = [
  { id: 'audience', mode: 'link', titre: 'Comprendre une audience',
    detail: 'Émotions et motivations derrière les commentaires d’une vidéo YouTube, Instagram ou TikTok.', action: 'Coller un lien' },
  { id: 'cross', mode: 'cross', titre: 'Comparer plusieurs audiences',
    detail: 'Ce que 2 à 5 communautés partagent, et ce qui les sépare.', action: 'Ajouter des audiences' },
  { id: 'freins', mode: 'link', titre: 'Identifier peurs et objections',
    detail: 'Ce qui freine l’adhésion, avec les verbatims qui le montrent.', action: 'Coller un lien' },
  { id: 'avis', mode: 'manual', titre: 'Analyser des avis clients',
    detail: 'Collez au moins 3 avis, réponses ou messages, un par ligne.', action: 'Coller des commentaires' },
  { id: 'enquete', mode: 'file', titre: 'Importer une enquête ou un export',
    detail: 'Tableur, JSON ou texte brut, jusqu’à 5 Mo.', action: 'Choisir un fichier' },
  { id: 'personas', mode: 'link', titre: 'Construire des personas',
    detail: 'Des profils issus des groupes réellement observés, avec leur fiabilité.', action: 'Coller un lien' },
];

function dateCourte(iso) {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
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

function Bar({ label, pct, count, tone }) {
  return <div className={`gv2-psy-bar-row is-${tone || 'neu'}`}>
    <span className="gv2-psy-bar-label">{esc(label)}</span>
    <div className="gv2-psy-bar-track"><div className="gv2-psy-bar-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} /></div>
    <span className="gv2-psy-bar-pct">{pct}%</span>
    {count != null && <span className="gv2-psy-bar-count">{count} cmnt</span>}
  </div>;
}

/** Répartition homme/femme — deux segments sur une seule piste. */
function GenderSplitBar({ hommes, femmes }) {
  const h = Math.max(0, Number(hommes) || 0);
  const f = Math.max(0, Number(femmes) || 0);
  const total = h + f;
  if (!total) return null;
  return <div className="gv2-psy-gender-bar">
    <div className="gv2-psy-gender-track">
      <div style={{ width: `${(h / total) * 100}%`, background: 'var(--psy-pos)' }} />
      <div style={{ width: `${(f / total) * 100}%`, background: 'var(--champagne)' }} />
    </div>
    <div className="gv2-psy-gender-legend">
      <span><i style={{ background: 'var(--psy-pos)' }} />{h}% hommes</span>
      <span><i style={{ background: 'var(--champagne)' }} />{f}% femmes</span>
    </div>
  </div>;
}

// Palette réservée aux visualisations de données — mêmes teintes de marque
// que le reste de Gabriel (champagne, sauge, ardoise, terracotta), jamais de
// couleur inventée. Pas de surface pleine : réservé aux graphiques.
const DONUT_COLORS = [
  'var(--champagne)', 'var(--psychologist-sage)', 'var(--strategist-slate)',
  'var(--creator-terracotta)', 'var(--champagne-deep)', 'var(--rose)',
  'var(--core-champagne)', 'var(--muted)',
];

/** Camembert évidé — jusqu'à 8 tranches, légende chiffrée en dessous. */
function Donut({ slices, size = 128 }) {
  const clean = (Array.isArray(slices) ? slices : [])
    .filter(s => s && typeof s.value === 'number' && s.value > 0);
  const total = clean.reduce((sum, s) => sum + s.value, 0);
  if (!total) return null;
  const r = 42;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return <div className="gv2-psy-donut">
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <circle cx="50" cy="50" r={r} fill="none" stroke="var(--line)" strokeWidth="14" />
      {clean.map((s, i) => {
        const length = (s.value / total) * c;
        const el = <circle key={i} cx="50" cy="50" r={r} fill="none"
          stroke={DONUT_COLORS[i % DONUT_COLORS.length]} strokeWidth="14"
          strokeDasharray={`${length} ${c - length}`} strokeDashoffset={-offset}
          transform="rotate(-90 50 50)" />;
        offset += length;
        return el;
      })}
    </svg>
    <ul className="gv2-psy-donut-legend">
      {clean.map((s, i) => <li key={i}>
        <i style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
        <span>{esc(s.label)}</span>
        <span className="gv2-psy-donut-pct">{Math.round(s.value)}%</span>
      </li>)}
    </ul>
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
/* Le backend renvoie tantôt une chaîne, tantôt un objet ({label}, {token}…).
   Sans ce passage, l'écran affiche « [object Object] ». Repris tel quel de
   l'ancienne page. */
function itemText(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'string' || typeof v === 'number') return String(v);
  if (Array.isArray(v)) return v.map(itemText).filter(Boolean).join(' · ');
  return v.token || v.bigram || v.emotion || v.label || v.nom || v.name || v.signal || '';
}

function TraitList({ items, tone }) {
  const clean = (Array.isArray(items) ? items : []).filter(Boolean);
  if (!clean.length) return null;
  return <ul className={`gv2-psy-traits${tone ? ` is-${tone}` : ''}`}>
    {clean.map((item, i) => <li key={i}>{formatInline(itemText(item))}</li>)}
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
    <p>{formatInline(value)}</p>
  </div>;
}

/** Bloc d'interprétation — psychologique ou socio-culturelle. */
function Interpretation({ title, data }) {
  const d = data || {};
  const insight = String(d.main_insight || '').trim();
  const mecanismes = Array.isArray(d.detected_mechanisms) ? d.detected_mechanisms : [];
  const rien = !insight && !mecanismes.length && !(d.fears || []).length
    && !(d.desires || []).length && !(d.beliefs || []).length
    && !(d.decision_drivers || []).length
    && !(d.group_dynamics || []).length && !(d.cultural_codes || []).length
    && !(d.social_tensions || []).length && !(d.collective_beliefs || []).length
    && !(d.community_markers || []).length;
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
    {insight && <p className="gv2-psy-interp-insight">{formatInline(insight)}</p>}

    {mecanismes.length > 0 && <div className="gv2-psy-mechanisms">
      {mecanismes.filter(m => m && m.mechanism).map((m, i) => <div className="gv2-psy-mechanism" key={i}>
        <div className="gv2-psy-mechanism-head">
          <strong>{esc(m.mechanism)}</strong>
          {typeof m.confidence === 'number' && <span>{Math.round(m.confidence * 100)}%</span>}
        </div>
        {m.evidence && <p>{formatInline(m.evidence)}</p>}
      </div>)}
    </div>}

    <div className="gv2-psy-trait-cols">
      <TraitGroup label="Peurs" items={d.fears} tone="neg" />
      <TraitGroup label="Désirs" items={d.desires} tone="pos" />
      <TraitGroup label="Frustrations" items={d.frustrations} tone="neg" />
      <TraitGroup label="Croyances actives" items={d.beliefs} />
      <TraitGroup label="Facteurs de décision" items={d.decision_drivers} tone="pos" />
      <TraitGroup label="Dynamiques de groupe" items={d.group_dynamics} />
      <TraitGroup label="Codes culturels" items={d.cultural_codes} />
      <TraitGroup label="Tensions sociales" items={d.social_tensions} tone="neg" />
      <TraitGroup label="Croyances collectives" items={d.collective_beliefs} />
      <TraitGroup label="Marqueurs communautaires" items={d.community_markers} />
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
/* Le camp ou l'émotion décide de la couleur. Une barre champagne partout
   ne dit rien ; du vert sur « favorable » et de l'ambre sur « opposé » se
   lisent avant même le pourcentage. Un mot inconnu reste neutre — mieux
   vaut ne pas colorer que colorer faux. */
const TONS_POS = ['favorable', 'positif', 'admiration', 'enthousiasme', 'joie',
                  'gratitude', 'confiance', 'espoir', 'soulagement', 'fierte'];
const TONS_NEG = ['oppose', 'opposé', 'negatif', 'négatif', 'colere', 'colère',
                  'frustration', 'peur', 'deception', 'déception', 'mepris',
                  'mépris', 'tristesse', 'anxiete', 'anxiété', 'doute'];

function ton(label) {
  const mot = String(label || '').toLowerCase().trim();
  if (TONS_POS.some((t) => mot.includes(t))) return 'pos';
  if (TONS_NEG.some((t) => mot.includes(t))) return 'neg';
  return 'neu';
}

/* Le backend renvoie des clés techniques (« oppose », « mefiance »,
   « positive », « preuve_demandée ») : un expert lit « Opposé », « Méfiance »,
   « Positif ». Un mot inconnu garde sa forme, simplement capitalisé. */
const LIBELLES = {
  favorable: 'Favorable', oppose: 'Opposé', 'opposé': 'Opposé', neutre: 'Neutre',
  nuance: 'Nuancé', hors_sujet: 'Hors sujet', ironique: 'Ironique',
  positive: 'Positif', neutral: 'Neutre', negative: 'Négatif',
  colere: 'Colère', mefiance: 'Méfiance', curiosite: 'Curiosité', fierte: 'Fierté',
  deception: 'Déception', anxiete: 'Anxiété', mepris: 'Mépris', gratitude: 'Gratitude',
  alignement: 'Alignement', authenticite: 'Authenticité', engagement: 'Engagement',
  opportunite: 'Opportunité', persistance: 'Persistance', polarisation: 'Polarisation',
  preuve_demandee: 'Preuve demandée', 'preuve_demandée': 'Preuve demandée',
  desir: 'Désir', besoin: 'Besoin',
};

function libelle(raw) {
  const texte = String(raw == null ? '' : raw).trim();
  const connu = LIBELLES[texte.toLowerCase()];
  if (connu) return connu;
  const lisible = texte.replace(/_/g, ' ');
  return lisible.charAt(0).toUpperCase() + lisible.slice(1);
}

/* Le lexique arrive sous plusieurs formes selon l'étape qui l'a produit :
   ['merci', 3.2], { mot: 'merci' }, { token: 'merci' } ou simplement 'merci'.
   Sans ce tri, l'écran affichait « merci,3.219 ». */
/* Le LLM met parfois lui-même des guillemets autour d'une citation :
   sans ce nettoyage, l'écran affichait « « … » ». */
function citation(texte) {
  const brut = esc(texte).trim().replace(/^[«"“\s]+|[»"”\s]+$/g, '');
  return brut ? `« ${brut} »` : '';
}

function motLexical(entree) {
  if (Array.isArray(entree)) return String(entree[0] ?? '');
  if (entree && typeof entree === 'object') return String(entree.mot || entree.token || entree.bigram || '');
  return String(entree ?? '');
}

/* Copier dans le presse-papiers, avec un retour visible. Le navigateur peut
   refuser (contexte non sécurisé, permission) : on le dit plutôt que de
   laisser croire que c'est fait. */
function CopyButton({ getText, label = 'Copier', className = 'gv2-psy-ghost-btn' }) {
  const [etat, setEtat] = useState('');
  async function copier() {
    try {
      await navigator.clipboard.writeText(getText());
      setEtat('ok');
    } catch (_) {
      setEtat('echec');
    }
    window.setTimeout(() => setEtat(''), 2400);
  }
  return <button type="button" className={className} onClick={copier} aria-live="polite">
    {etat === 'ok' ? 'Copié ✓' : etat === 'echec' ? 'Copie impossible' : label}
  </button>;
}

/** Un indicateur : score, verdict, lecture en clair, et la méthode de calcul
 *  pour qui veut vérifier — un expert ne signe pas un chiffre opaque. */
function KpiCard({ nom, valeur }) {
  const v = valeur && typeof valeur === 'object' ? valeur : { score: valeur };
  if (typeof v.score !== 'number') return null;
  const variables = v.variables && typeof v.variables === 'object'
    ? Object.entries(v.variables).map(([k, val]) => `${k} = ${val}`).join(' · ') : '';
  return <div className="gv2-psy-kpi">
    <div className="gv2-psy-kpi-top">
      <div className="gv2-psy-kpi-score">{Math.round(v.score)}</div>
      {v.label && <span className="gv2-psy-kpi-verdict">{esc(String(v.label))}</span>}
    </div>
    <div className="gv2-psy-kpi-name">{libelle(nom)}</div>
    {(v.description || v.lecture) && <p>{esc(String(v.description || v.lecture))}</p>}
    {(v.formule || v.interpretation) && <details className="gv2-psy-kpi-method">
      <summary>Méthode de calcul</summary>
      {v.interpretation && <p>{esc(String(v.interpretation))}</p>}
      {v.formule && <code>{String(v.formule)}</code>}
      {variables && <small>{esc(variables)}</small>}
    </details>}
  </div>;
}

/** Fin d'onglet : la suite logique du parcours, pour ne jamais laisser
 *  le lecteur en bout de page sans direction. */
function NextStep({ label, hint, onClick, primary }) {
  return <div className="gv2-psy-next">
    {hint && <span className="gv2-psy-next-hint">{hint}</span>}
    <button type="button" className={primary ? 'gv2-psy-primary-btn' : 'gv2-psy-ghost-btn'} onClick={onClick}>{label}</button>
  </div>;
}

/* Un persona sans visage reste une fiche. La teinte vient du nom (toujours
   la même pour le même persona), l'anneau vient de son émotion dominante. */
function PersonaAvatar({ nom, emotion, large }) {
  const texte = String(nom || '').trim();
  const initiales = texte.split(/\s+/).slice(0, 2).map((m) => m[0] || '')
    .join('').toUpperCase() || '?';
  let empreinte = 0;
  for (let i = 0; i < texte.length; i += 1) empreinte = (empreinte * 31 + texte.charCodeAt(i)) % 360;
  return <div className={`gv2-psy-avatar is-${ton(emotion)}${large ? ' is-large' : ''}`} aria-hidden="true"
              style={{ '--avatar-teinte': empreinte }}>
    <span>{initiales}</span>
  </div>;
}

/* Le portrait vient de randomuser.me, comme sur l'ancienne page : même
   graine (nom + rang), donc le même persona garde le même visage d'une
   analyse à l'autre. Si la requête échoue — hors ligne, blocage réseau —
   le visage généré prend le relais : la fiche n'a jamais de trou. */
function personaPhotoUrl(nom, index, genre) {
  let h = 5381;
  const graine = `${nom || ''}${index}`;
  for (let i = 0; i < graine.length; i += 1) h = ((h << 5) + h) ^ graine.charCodeAt(i);
  const rang = Math.abs(h) % 70;
  const femme = /femme|woman|^f$/i.test(String(genre || '').trim());
  return `https://randomuser.me/api/portraits/${femme ? 'women' : 'men'}/${rang}.jpg`;
}

function PersonaPortrait({ nom, index, genre, emotion }) {
  const [echec, setEchec] = useState(false);
  if (echec) return <PersonaAvatar nom={nom} emotion={emotion} large />;
  return <img className={`gv2-psy-portrait is-${ton(emotion)}`} alt=""
              src={personaPhotoUrl(nom, index, genre)}
              onError={() => setEchec(true)} />;
}

/* Une donnée du volet droit. Absente, elle ne laisse pas de case vide. */
function Stat({ label, value }) {
  if (!value) return null;
  return <div className="gv2-psy-stat">
    <div className="gv2-psy-stat-lbl">{label}</div>
    <div className="gv2-psy-stat-val">{formatInline(value)}</div>
  </div>;
}

function PersonaListe({ titre, items }) {
  const liste = Array.isArray(items) ? items.filter(Boolean) : [];
  if (liste.length === 0) return null;
  return <div className="gv2-psy-pc-block">
    <div className="gv2-psy-pc-ttl">{titre}</div>
    {liste.map((item, i) => <div className="gv2-psy-pc-li" key={i}>{formatInline(itemText(item))}</div>)}
  </div>;
}

/* Texte brut prêt à coller dans un brief, un deck ou un message à l'équipe. */
function lignesListe(titre, items) {
  const liste = (Array.isArray(items) ? items : []).map(itemText).filter(Boolean);
  return liste.length ? [`${titre} :`, ...liste.map((x) => `- ${x}`)] : [];
}

function personaEnTexte(p, nom) {
  const ligne = (label, val) => (val ? [`${label} : ${itemText(val)}`] : []);
  return [
    `PERSONA — ${nom}`,
    [p.age ? `${p.age} ans` : '', p.genre, p.metier].filter(Boolean).join(' · '),
    ...ligne('Poids dans l\'audience', p.poids),
    ...ligne('Émotion dominante', p.emotion_dominante_mesuree),
    ...ligne('Archétype', p.archetype_jungien),
    ...ligne('Vision du monde', p.vision_monde),
    ...ligne('Situation de vie', p.situation_vie),
    ...ligne('État d\'esprit', p.etat_esprit),
    ...ligne('Ce qu\'il écrirait', p.langage_typique),
    ...lignesListe('Frustrations', p.frustrations),
    ...lignesListe('Aspirations', p.aspirations),
    ...lignesListe('Peurs', p.peurs),
    ...lignesListe('Désirs cachés', p.desirs),
    ...lignesListe('Déclencheurs émotionnels', p.declencheurs_emotionnels),
    ...lignesListe('Messages qui le toucheraient', p.messages_impactants),
    ...lignesListe('Objections à lever', p.objections_a_lever),
    ...ligne('Objection principale', p.objection_principale),
    ...ligne('Preuve attendue', p.preuve_attendue),
    ...ligne('Ce qui le ferait acheter', p.ce_qui_le_ferait_acheter || p.ce_qui_la_ferait_acheter),
    ...ligne('Ce qui le ferait fuir', p.ce_qui_le_ferait_fuir || p.ce_qui_la_ferait_fuir),
    ...ligne('Message à lui adresser', p.message_a_lui_dire),
  ].filter(Boolean).join('\n');
}

function syntheseEnTexte(data) {
  const brief = data.brief || {};
  const recos = data.recommandations || {};
  const emo = data.emotions || {};
  const ligne = (label, val) => (val ? [`${label} : ${itemText(val)}`] : []);
  return [
    'GABRIEL — SYNTHÈSE DU PSYCHOLOGUE',
    ...ligne('Qui', brief.qui || brief.synthese),
    ...ligne('Insight clé', brief.insight || brief.insight_cle),
    ...ligne('Action prioritaire', brief.action || brief.action_prioritaire),
    ...ligne('Vérité de l\'audience', recos.verite_de_l_audience),
    ...ligne('Message central', recos.message_central),
    ...ligne('Promesse authentique', recos.promesse_authentique),
    ...ligne('Émotion dominante', emo.dominante),
    ...ligne('Espoir déçu', emo.espoir_decu),
    ...ligne('Aspiration nourrie', emo.aspiration_nourrie),
    ...lignesListe('Actions prioritaires', recos.actions_prioritaires),
    ...lignesListe('Prochaines étapes', recos.prochaines_etapes),
  ].join('\n');
}

/* La fiche persona : portrait et identité à gauche, ce qu'il vit au
   centre, ce que l'analyse en déduit à droite. Dix-sept champs que le
   backend produisait et que l'écran n'avait jamais montrés. */
function PersonaCard({ persona: p, index }) {
  const nom = p.nom || `Persona ${index + 1}`;
  const signaux = (Array.isArray(p.signaux_mesures) ? p.signaux_mesures : []);
  const conf = typeof p.confiance === 'number' ? Math.round(p.confiance * 100) : null;
  const achat = p.ce_qui_le_ferait_acheter || p.ce_qui_la_ferait_acheter;
  const fuite = p.ce_qui_le_ferait_fuir || p.ce_qui_la_ferait_fuir;
  const meta = esc([p.age ? `${p.age} ans` : '', p.genre, p.metier].filter(Boolean).join(' · '));
  return <article className="gv2-psy-pc">
    <div className="gv2-psy-pc-left">
      <PersonaPortrait nom={nom} index={index} genre={p.genre}
                       emotion={p.emotion_dominante_mesuree} />
      <div className="gv2-psy-pc-name">{esc(nom)}</div>
      {meta && <div className="gv2-psy-pc-meta">{meta}</div>}
      {signaux.length > 0 && <div className="gv2-psy-pc-sigs">
        {signaux.map((sig, i) => <span key={i}>{esc(itemText(sig))}</span>)}
      </div>}
      {p.histoire_interieure && <blockquote className="gv2-psy-pc-quote">
        {formatInline(String(p.histoire_interieure))}
      </blockquote>}
    </div>

    <div className="gv2-psy-pc-center">
      {p.archetype_jungien && (
        <div className="gv2-psy-pc-arch">{esc(String(p.archetype_jungien))}</div>
      )}
      <div className="gv2-psy-pc-chips">
        {p.emotion_dominante_mesuree && <span className={`is-${ton(p.emotion_dominante_mesuree)}`}>{esc(p.emotion_dominante_mesuree)}</span>}
        {p.poids && <span>{esc(String(p.poids))}</span>}
      </div>
      {p.vision_monde && <p className="gv2-psy-pc-vision">{citation(p.vision_monde)}</p>}
      {p.etat_esprit && <Statement label="État d'esprit" text={p.etat_esprit} />}
      {p.situation_vie && <Statement label="Situation de vie" text={p.situation_vie} />}
      {p.langage_typique && <div className="gv2-psy-pc-lang">
        <div className="gv2-psy-pc-ttl">Ce qu'il écrirait en commentaire</div>
        <p>{citation(p.langage_typique)}</p>
      </div>}
      <div className="gv2-psy-pc-2col">
        <PersonaListe titre="Frustrations" items={p.frustrations} />
        <PersonaListe titre="Aspirations" items={p.aspirations} />
        <PersonaListe titre="Pain points" items={p.peurs} />
        <PersonaListe titre="Désirs cachés" items={p.desirs} />
        <PersonaListe titre="Déclencheurs émotionnels" items={p.declencheurs_emotionnels} />
        <PersonaListe titre="Habitudes digitales" items={p.habitudes_digitales} />
        <PersonaListe titre="Messages qui le toucheraient" items={p.messages_impactants} />
        <PersonaListe titre="Objections à lever" items={p.objections_a_lever} />
      </div>
      {p.rapport_autorite && <Statement label="Rapport à l'autorité" text={p.rapport_autorite} />}
      {p.message_a_lui_dire && <div className="gv2-psy-pc-msg">
        <div className="gv2-psy-pc-msg-lbl">Message à lui adresser</div>
        <p>{citation(p.message_a_lui_dire)}</p>
      </div>}
      <div className="gv2-psy-pc-actions">
        <CopyButton label="Copier la fiche" getText={() => personaEnTexte(p, nom)} />
      </div>
    </div>

    <div className="gv2-psy-pc-right">
      {conf !== null && <div className="gv2-psy-stat is-wide">
        <div className="gv2-psy-stat-lbl">Fiabilité du persona</div>
        <div className="gv2-psy-pc-conf">{conf}%</div>
        <div className="gv2-psy-conf-track"><div className="gv2-psy-conf-fill" style={{ width: `${conf}%` }} /></div>
      </div>}
      <Stat label="Cluster source" value={p.cluster_source} />
      <Stat label="Ancrage dans les données" value={p.cluster_grounding_reason} />
      <Stat label="Tension existentielle" value={p.tension_existentielle} />
      <Stat label="Quête · Frankl" value={p.quete_de_sens} />
      <Stat label="Biais · Kahneman" value={p.biais_cognitifs} />
      <Stat label="Ombre · Jung" value={p.ombre_jungienne} />
      <Stat label="Objection principale" value={p.objection_principale} />
      <Stat label="Preuve attendue" value={p.preuve_attendue} />
      <Stat label="Déclencheur d'achat" value={achat} />
      <Stat label="Mission cachée · Munroe" value={p.mission_cachee} />
      <Stat label="Potentiel bloqué · Munroe" value={p.potentiel_non_exprime} />
      <Stat label="Tribu aspirée" value={p.besoin_d_appartenance} />
      <Stat label="Désir de legacy" value={p.desir_de_legacy} />
      <Stat label="Rapport à l'argent" value={p.rapport_argent} />
      <Stat label="Repoussoir principal" value={fuite} />
    </div>
  </article>;
}

function AudienceGroup({ groupe }) {
  // Clés réelles de audience.compute_dashboard (mots_cles, exemples, taille,
  // stance_dominante, emotion_dominante) ; les anciennes restent lues en repli.
  const tokens = Array.isArray(groupe.mots_cles) ? groupe.mots_cles
    : Array.isArray(groupe.top_tokens) ? groupe.top_tokens : [];
  const samples = Array.isArray(groupe.exemples) ? groupe.exemples
    : Array.isArray(groupe.samples) ? groupe.samples : [];
  const taille = groupe.taille ?? groupe.size;
  const stance = groupe.stance_dominante || groupe.stance;
  const emotion = groupe.emotion_dominante || groupe.emotion;
  return <div className={`gv2-psy-group is-${ton(stance)}`}>
    <div className="gv2-psy-group-head">
      <span className="gv2-psy-group-pct">{groupe.pct != null ? `${groupe.pct}%` : ''}</span>
      <span className="gv2-psy-group-count">{taille != null ? `${taille} commentaires` : ''}</span>
      <div className="gv2-psy-group-tags">
        {groupe.likes_pct > 0 && <span>♥ {groupe.likes_pct}%</span>}
        {stance && <span className="is-stance">{libelle(stance)}</span>}
        {emotion && <span>{libelle(emotion)}</span>}
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
    <p className="gv2-psy-insight-conclusion">{formatInline(conclusion)}</p>
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
      <span>{formatInline(String(d.interpretation))}</span>
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
      <span className="gv2-psy-grid-key">Obs.</span><span>{formatInline(String(d.observation))}</span>
    </div>}
    {d.interpretation && <div className="gv2-psy-grid-row">
      <span className="gv2-psy-grid-key">Sens</span><span>{formatInline(String(d.interpretation))}</span>
    </div>}
    {d.implication && <div className="gv2-psy-grid-row">
      <span className="gv2-psy-grid-key">Action</span><span>{formatInline(String(d.implication))}</span>
    </div>}
  </div>;
}

/** Une phase de la trajectoire de transformation (état actuel / pont / désiré).
 *  Les champs sont des phrases, pas des faits courts : Statement (label au-dessus,
 *  texte en dessous) leur va mieux que la grille Obs./Sens/Action de GridEntry. */
function TransformationPhase({ title, fields, data }) {
  const d = data || {};
  if (!fields.some(([cle]) => d[cle])) return null;
  return <div className="gv2-psy-card gv2-psy-grid-entry">
    <div className="gv2-psy-grid-title">{title}</div>
    {fields.map(([cle, label]) => <Statement key={cle} label={label} text={d[cle]} />)}
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

/** État actuel → le pont → état désiré : ordre de lecture, pas ordre du JSON. */
const TRANSFORMATION_PHASES = [
  ['etat_actuel', 'État actuel', [
    ['situation', 'Situation'],
    ['frustration_principale', 'Frustration principale'],
    ['croyance_bloquante', 'Croyance bloquante'],
    ['identite_actuelle', 'Identité actuelle'],
    ['conscience_du_probleme', 'Conscience du problème'],
  ]],
  ['le_pont', 'Le pont', [
    ['ce_dont_ils_ont_besoin', 'Ce dont ils ont besoin'],
    ['obstacle_principal', 'Obstacle principal'],
    ['declencheur_de_transition', 'Déclencheur de transition'],
    ['message_de_passage', 'Message de passage'],
  ]],
  ['etat_desire', 'État désiré', [
    ['transformation_visee', 'Transformation visée'],
    ['identite_aspiree', 'Identité aspirée'],
    ['vie_revelee', 'Vie révélée'],
    ['indicateur_de_succes', "Indicateur de succès"],
  ]],
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

/** La couche la plus profonde de la lecture psychologique : sens et potentiel. */
const PSY_SENS = [
  ['potentiel_bloque', 'Potentiel bloqué'],
  ['signal_de_purpose', 'Signal de purpose'],
  ['quete_de_signifiance', 'Quête de signifiance'],
  ['besoin_d_appartenance', "Besoin d'appartenance"],
  ['desir_de_legacy', 'Désir de legacy'],
  ['besoin_de_transformation', 'Besoin de transformation'],
];

const PSY_RAPPORTS = [
  ['rapport_argent', "Rapport à l'argent"],
  ['rapport_succes', 'Rapport au succès'],
  ['rapport_autorite', "Rapport à l'autorité"],
  ['rapport_image', "Rapport à l'image"],
  ['rapport_travail', 'Rapport au travail'],
  ['rapport_famille', 'Rapport à la famille'],
  ['rapport_spiritualite', 'Rapport à la spiritualité'],
];

/** Livrables calculés sans LLM : la preuve chiffrée derrière la lecture. */
const PREUVES_STATISTIQUES = [
  ['repartition_camps', 'Répartition des camps'],
  ['positionnement_audience', "Positionnement de l'audience"],
  ['carte_emotionnelle', 'Carte émotionnelle'],
  ['clusters_comportementaux', 'Clusters comportementaux'],
  ['signaux_lexicaux_dominants', 'Signaux lexicaux dominants'],
  ['distribution_relevance', 'Pertinence des commentaires'],
];

function PsychoResult({ data, onReset, onGoToStratege, onGoToCreateur }) {
  const [tab, setTab] = useState('');

  const db = data.dashboard || {};
  const meta = data.meta || {};
  const brief = data.brief || {};
  const emo = data.emotions || {};
  const psy = data.psychologie || {};
  const asp = data.aspirations || {};
  const mkt = data.marketing || {};
  const interp = data.interpretation || {};
  const kpis = data.kpis || {};
  const livr = data.livrables_statistiques || {};
  const grille = data.grille_psychologique || {};
  const recos = data.recommandations || {};
  const demo = data.demographique || {};
  const cult = data.culturel || {};
  const ident = data.identitaire || {};
  const transfo = data.transformation || {};
  const caches = data.marches_caches || {};

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
  // Sans aucun like, des barres à 0 % ne disent rien : on ne garde que la densité.
  const likesResonance = Object.values(res).reduce((t, v) => t + ((v && v.likes) || 0), 0);
  const ard = db.argument_density || {};
  const mok = db.mockery_signals || {};
  const iry = db.irony_signals || {};
  // resume_tendances porte la tension et la tendance ; l'écran les cherchait
  // à la racine du dashboard, où elles n'existent pas.
  const rt = db.resume_tendances || {};
  const tension = rt.tension_principale || db.tension_principale;
  const tendance = rt.tendance_dominante || db.tendance_dominante;
  const signalDominant = rt.signal_dominant || db.signal_dominant;

  // Les commentaires les plus likés sont à la racine du résultat, pas dans le
  // dashboard : c'est pour ça que ce bloc n'apparaissait jamais.
  const topComments = Array.isArray(data.top_comments) ? data.top_comments
    : Array.isArray(db.top_comments) ? db.top_comments : [];

  // Les catégories vides (hors sujet, ironique à 0) n'apportent rien au lecteur.
  const pos = Object.fromEntries(Object.entries(db.positions || {})
    .filter(([, v]) => v && (v.count > 0 || v.pct > 0)));
  const emotions = Array.isArray(db.emotion_distribution)
    ? db.emotion_distribution
    : Object.entries(db.emotion_distribution || {}).map(([emotion, pct]) => ({ emotion, pourcentage: pct }));
  const sentimentDist = db.sentiment_distribution || {};
  const personas = Array.isArray(data.personas) ? data.personas : [];

  const qui = brief.qui || brief.synthese || '';
  const insight = brief.insight || brief.insight_cle || '';
  const action = brief.action || brief.action_prioritaire || '';

  const verbatims = (Array.isArray(emo.commentaires_revelateurs) ? emo.commentaires_revelateurs : []).filter(Boolean);
  const actionsPrio = (Array.isArray(recos.actions_prioritaires) ? recos.actions_prioritaires : []).filter(Boolean);
  const etapes = (Array.isArray(recos.prochaines_etapes) ? recos.prochaines_etapes : []).filter(Boolean);
  const livrablesPurs = PREUVES_STATISTIQUES.filter(([cle]) => (livr[cle] || {}).conclusion);

  const aPsychologie = Boolean(
    interp.psychologique || interp.socio_culturelle || Object.keys(psy).length ||
    Object.keys(asp).length || Object.keys(transfo).length || Object.keys(cult).length ||
    GRILLE.some(([cle]) => grille[cle]) || LIVRABLES.some(([cle]) => (livr[cle] || {}).conclusion));
  const aSynthese = Boolean(
    recos.verite_de_l_audience || recos.message_central || recos.promesse_authentique ||
    recos.insight_strategique_cle || recos.ce_qu_ils_ne_disent_pas_mais_veulent_entendre ||
    emo.dominante || emo.espoir_decu || emo.aspiration_nourrie ||
    actionsPrio.length || etapes.length);
  const aStrategie = Boolean(
    Object.keys(recos).length || Object.keys(mkt).length ||
    Object.keys(caches).length || Object.keys(ident).length);

  // Un onglet vide ne doit pas être proposé : mieux vaut quatre onglets pleins
  // que cinq dont un déçoit.
  const tabs = [
    ...(aSynthese ? [{ id: 'synthese', label: 'Synthèse' }] : []),
    { id: 'dashboard', label: 'Tableau de bord' },
    ...(aPsychologie ? [{ id: 'psychologie', label: 'Psychologie' }] : []),
    ...(aStrategie ? [{ id: 'strategie', label: 'Stratégie' }] : []),
    ...(personas.length ? [{ id: 'personas', label: `Personas (${personas.length})` }] : []),
  ];
  const actif = tabs.some(t => t.id === tab) ? tab : tabs[0].id;
  const rang = tabs.findIndex(t => t.id === actif);
  const suivant = tabs[rang + 1];

  function ouvrir(id) {
    setTab(id);
    // Changer d'onglet en bas de page doit ramener au début du nouvel onglet.
    try { document.querySelector('.gv2-psy-result-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (_) { /* jsdom */ }
  }

  const source = [
    data.source_label,
    meta.total_commentaires != null ? `${meta.total_commentaires} commentaires collectés` : '',
    meta.commentaires_analyses != null ? `${meta.commentaires_analyses} analysés` : '',
    fib.label_confiance ? `fiabilité : ${String(fib.label_confiance).toLowerCase()}` : '',
  ].filter(Boolean).join(' · ');

  const finOnglet = suivant
    ? <NextStep label={`Suite : ${suivant.label} →`} hint="Continuer la lecture" onClick={() => ouvrir(suivant.id)} />
    : <div className="gv2-psy-next is-final">
        <span className="gv2-psy-next-hint">Lecture terminée — passez à l'action.</span>
        <div className="gv2-psy-next-actions">
          {onGoToCreateur && <button type="button" className="gv2-psy-ghost-btn" onClick={() => onGoToCreateur(data)}>Passer au Créateur →</button>}
          {data.analysis_id && <button type="button" className="gv2-psy-primary-btn" onClick={() => onGoToStratege(data)}>Construire la stratégie →</button>}
        </div>
      </div>;

  return <section className="gv2-psy-result">
    <div className="gv2-psy-result-head">
      <div>
        <span className="gv2-psy-eyebrow">Le Psychologue</span>
        <h1>Résultats</h1>
        {source && <p className="gv2-psy-source">{esc(source)}</p>}
        {data.video_context && <p className="gv2-psy-source is-context">{esc(String(data.video_context))}</p>}
      </div>
      <div className="gv2-psy-result-actions">
        <button type="button" className="gv2-psy-ghost-btn" onClick={onReset}>← Nouvelle analyse</button>
        <CopyButton label="Copier la synthèse" getText={() => syntheseEnTexte(data)} />
        {data.analysis_id && <a className="gv2-psy-ghost-btn" href={`/export/pdf/${encodeURIComponent(data.analysis_id)}`}
                               download>Exporter en PDF</a>}
        {data.analysis_id && <button type="button" className="gv2-psy-primary-btn" onClick={() => onGoToStratege(data)}>Construire la stratégie →</button>}
      </div>
    </div>

    {qui && <div className="gv2-psy-hero">
      <div className="gv2-psy-hero-label">Ce que dit cette audience</div>
      <p className="gv2-psy-hero-text">{formatInline(qui)}</p>
      <div className="gv2-psy-hero-pills">
        {insight && <span><strong>Insight ·</strong> {formatInline(insight)}</span>}
        {action && <span><strong>Action ·</strong> {formatInline(action)}</span>}
      </div>
    </div>}

    {/* Les quatre chiffres clés restent visibles quel que soit l'onglet. */}
    <div className="gv2-psy-stats-grid">
      <StatChip value={meta.total_commentaires || 0} count={`${meta.commentaires_analyses || 0} qualifiés`} label="Collectés" />
      <StatChip value={`${(pos.favorable || {}).pct || 0}%`} count={`${(pos.favorable || {}).count || 0} cmnt`} label="Favorables" tone="pos" />
      <StatChip value={`${(pos.oppose || {}).pct || 0}%`} count={`${(pos.oppose || {}).count || 0} cmnt`} label="Opposés" tone="neg" />
      <StatChip value={`${(pos.neutre || {}).pct || 0}%`} count={`${(pos.neutre || {}).count || 0} cmnt`} label="Neutres" />
    </div>

    {tabs.length > 1 && <ResultTabs active={actif} onChange={ouvrir} tabs={tabs} />}

    {/* ── Synthèse : ce qu'un décideur doit retenir en deux minutes ─────── */}
    {actif === 'synthese' && <>
      {(recos.verite_de_l_audience || recos.message_central || recos.promesse_authentique || recos.insight_strategique_cle) && (
        <Section title="Ce qu'il faut retenir" hint="La lecture stratégique en quatre phrases.">
          <div className="gv2-psy-card gv2-psy-card--plain gv2-psy-keypoints">
            <Statement label="Vérité de l'audience" text={recos.verite_de_l_audience} />
            {recos.message_central && <div className="gv2-psy-reco-message">
              <div className="gv2-psy-statement-label">Message central</div>
              <blockquote>{formatInline(recos.message_central)}</blockquote>
            </div>}
            <Statement label="Promesse authentique" text={recos.promesse_authentique} />
            <Statement label="Insight stratégique" text={recos.insight_strategique_cle} />
          </div>
        </Section>
      )}

      {(emo.dominante || emo.intensite || emo.espoir_decu || emo.aspiration_nourrie || emo.besoins_sous_jacents) && (
        <Section title="Lecture émotionnelle" hint="Ce que l'audience ressent vraiment, derrière ce qu'elle écrit.">
          <div className="gv2-psy-card gv2-psy-card--plain">
            {emo.dominante && <div className="gv2-psy-emo-head">
              <span className={`gv2-psy-emo-dominante is-${ton(emo.dominante)}`}>{libelle(emo.dominante)}</span>
              {emo.intensite && <p>{formatInline(emo.intensite)}</p>}
            </div>}
            <div className="gv2-psy-reco-cols">
              <Statement label="Espoir déçu — derrière les critiques" text={emo.espoir_decu} />
              <Statement label="Aspiration nourrie — derrière l'enthousiasme" text={emo.aspiration_nourrie} />
            </div>
            <Statement label="Besoin sous-jacent" text={emo.besoins_sous_jacents} />
          </div>
        </Section>
      )}

      {actionsPrio.length > 0 && (
        <Section title="Actions prioritaires" hint="Dans l'ordre où les engager.">
          <ol className="gv2-psy-actions-list">
            {actionsPrio.map((a, i) => <li key={i}><span className="gv2-psy-actions-num">{i + 1}</span><p>{formatInline(itemText(a))}</p></li>)}
          </ol>
        </Section>
      )}

      {etapes.length > 0 && (
        <Section title="Feuille de route">
          <div className="gv2-psy-timeline">
            {etapes.map((etape, i) => {
              const texte = typeof etape === 'string' ? etape : [etape.horizon, etape.action].filter(Boolean).join(' : ');
              const [horizon, ...reste] = texte.split(' : ');
              return <div className="gv2-psy-timeline-step" key={i}>
                {reste.length > 0 ? <>
                  <span className="gv2-psy-timeline-when">{esc(horizon)}</span>
                  <p>{formatInline(reste.join(' : '))}</p>
                </> : <p>{formatInline(texte)}</p>}
              </div>;
            })}
          </div>
        </Section>
      )}

      {recos.ce_qu_ils_ne_disent_pas_mais_veulent_entendre && (
        <Section title="Ce qu'ils ne disent pas, mais veulent entendre">
          <blockquote className="gv2-psy-quote is-accent"><p>{formatInline(recos.ce_qu_ils_ne_disent_pas_mais_veulent_entendre)}</p></blockquote>
        </Section>
      )}

      {finOnglet}
    </>}

    {/* ── Tableau de bord : ce qui a été mesuré ───────────────────────────── */}
    {actif === 'dashboard' && <>
      {Object.keys(kpis).length > 0 && <Section title="Indicateurs"
               hint="Scores calculés sur les commentaires, sans IA. Ouvrez « Méthode de calcul » pour vérifier chaque chiffre.">
        <div className="gv2-psy-kpis">
          {Object.entries(kpis).map(([nom, valeur]) => <KpiCard key={nom} nom={nom} valeur={valeur} />)}
        </div>
      </Section>}

      {Object.keys(demo).length > 0 && (
        <Section title="Données démographiques" hint="Estimées à partir du vocabulaire, des références et du ton des commentaires.">
          <div className="gv2-psy-lex-cols">
            {demo.genre && (demo.genre.hommes != null || demo.genre.femmes != null) && (
              <div className="gv2-psy-card gv2-psy-card--plain">
                <div className="gv2-psy-trait-label">Genre estimé</div>
                <GenderSplitBar hommes={demo.genre.hommes} femmes={demo.genre.femmes} />
              </div>
            )}
            {Array.isArray(demo.tranches_age) && demo.tranches_age.length > 0 && (
              <div className="gv2-psy-card gv2-psy-card--plain">
                <div className="gv2-psy-trait-label">Âge estimé</div>
                {demo.tranches_age.map((t, i) => (
                  <Bar key={i} label={t.tranche} pct={Math.round(t.pourcentage || 0)} />
                ))}
              </div>
            )}
          </div>

          <div className="gv2-psy-trait-cols">
            <TraitGroup label="Métiers probables" items={demo.metiers_probables} />
            <TraitGroup label="Centres d'intérêt" items={demo.centres_interet} />
            <TraitGroup label="Comportements digitaux" items={demo.comportements_digitaux} />
            {demo.localisation && (
              <TraitGroup label="Pays" items={demo.localisation.pays} />
            )}
            {demo.localisation && (
              <TraitGroup label="Villes / régions" items={demo.localisation.villes_regions} />
            )}
          </div>

          <Statement label="Niveau social probable" text={demo.niveau_social_probable} />
          {demo.localisation && <Statement label="Note (inférence)" text={demo.localisation.note} />}
        </Section>
      )}

      {emotions.length > 0 && <Section title="Émotions détectées">
        <div className="gv2-psy-card gv2-psy-card--plain">
          <Donut slices={emotions.slice(0, 8).map(item => ({
            label: libelle(item.emotion), value: Math.round(item.pourcentage || item.pct || 0),
          }))} />
        </div>
        {(emo.signaux_authenticite || emo.signaux_artificialite) && <div className="gv2-psy-reco-cols gv2-psy-mt">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <Statement label="Signaux d'authenticité" text={emo.signaux_authenticite} />
          </div>
          <div className="gv2-psy-card gv2-psy-card--plain">
            <Statement label="Signaux d'artificialité" text={emo.signaux_artificialite} />
          </div>
        </div>}
        {verbatims.length > 0 && <div className="gv2-psy-mt">
          <div className="gv2-psy-trait-label">Commentaires révélateurs</div>
          <div className="gv2-psy-quotes">
            {verbatims.map((v, i) => <blockquote className="gv2-psy-quote" key={i}><p>{citation(itemText(v))}</p></blockquote>)}
          </div>
        </div>}
      </Section>}

      {(Object.keys(pos).length > 0 || Object.keys(sentimentDist).length > 0) && <Section title="Positions & sentiments">
        {Object.keys(pos).length > 0 && <div className="gv2-psy-card gv2-psy-card--plain">
          {Object.entries(pos).map(([key, value]) => <Bar key={key} label={libelle(key)} tone={ton(key)} pct={Math.round(value.pct || 0)} count={value.count} />)}
        </div>}
        <div className="gv2-psy-donuts-row">
          {Object.keys(sentimentDist).length > 0 && (
            <div className="gv2-psy-card gv2-psy-card--plain">
              <div className="gv2-psy-trait-label">Sentiments</div>
              <Donut slices={Object.entries(sentimentDist).map(([label, value]) => ({ label: libelle(label), value }))} />
            </div>
          )}
          {Object.keys(pos).length > 0 && (
            <div className="gv2-psy-card gv2-psy-card--plain">
              <div className="gv2-psy-trait-label">Positions</div>
              <Donut slices={Object.entries(pos).map(([label, v]) => ({ label: libelle(label), value: v && v.pct }))} />
            </div>
          )}
        </div>
      </Section>}

      {(tension || tendance || db.dominant_desire || signalDominant) && (
        <Section title="Lecture d'ensemble">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <Statement label="Tension principale" text={tension} />
            <Statement label="Tendance dominante" text={tendance && libelle(tendance)} />
            <Statement label="Désir dominant" text={db.dominant_desire} />
            <Statement label="Signal dominant" text={signalDominant && libelle(signalDominant)} />
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

      {topComments.length > 0 && (
        <Section title="Commentaires les plus amplifiés"
                 hint="Classés par nombre de likes — ce que l'audience a elle-même mis en avant.">
          <div className="gv2-psy-quotes">
            {topComments.slice(0, 10).map((c, i) => <blockquote className="gv2-psy-quote" key={i}>
              <p>{esc(typeof c === 'string' ? c : (c.text || ''))}</p>
              {c && (c.likes > 0 || (c.author && c.author !== 'inconnu')) && <cite>
                {c.likes > 0 ? `♥ ${c.likes}` : ''}{c.likes > 0 && c.author && c.author !== 'inconnu' ? ' · ' : ''}{c.author && c.author !== 'inconnu' ? esc(c.author) : ''}
              </cite>}
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
            <Metric label="Scepticisme" value={db.skepticism_score} hint="part de doute exprimé" />
            <Metric label="Opportunité" value={db.opportunity_score} hint="potentiel de conversion mesuré" />
          </div>
        </Section>
      )}

      {Object.keys(res).length > 0 && (
        <Section title={likesResonance > 0 ? 'Résonance par camp & densité argumentative' : 'Densité argumentative par camp'}
                 hint={likesResonance > 0 ? 'Qui fait réagir, et qui argumente.'
                   : "Ces commentaires n'ont pas de likes : seule la manière d'argumenter est mesurable."}>
          <div className="gv2-psy-card gv2-psy-card--plain">
            {Object.entries(res).map(([camp, v]) => likesResonance > 0 ? <div className="gv2-psy-resonance" key={camp}>
              <span className="gv2-psy-resonance-camp">{libelle(camp)}</span>
              <div className="gv2-psy-bar-track"><div className="gv2-psy-bar-fill" style={{ width: `${Math.min(100, v.pct || 0)}%` }} /></div>
              <span className="gv2-psy-resonance-pct">{v.pct}%</span>
              <span className="gv2-psy-resonance-likes">{v.likes} ♥</span>
              <span className="gv2-psy-resonance-words">
                {(ard[camp] || {}).avg_words != null ? `${ard[camp].avg_words} mots · ${ard[camp].label || ''}` : ''}
              </span>
            </div> : <div className="gv2-psy-resonance is-sans-likes" key={camp}>
              <span className="gv2-psy-resonance-camp">{libelle(camp)}</span>
              <span className="gv2-psy-resonance-words">
                {(ard[camp] || {}).avg_words != null ? `${ard[camp].avg_words} mots · ${ard[camp].label || ''}` : ''}
              </span>
            </div>)}
          </div>
        </Section>
      )}

      {(Array.isArray(lexique.top_mots) && lexique.top_mots.length > 0) && (
        <Section title="Mots et expressions fréquents">
          <div className="gv2-psy-lex-cols">
            <div className="gv2-psy-card gv2-psy-card--plain">
              <div className="gv2-psy-trait-label">Mots les plus significatifs</div>
              <div className="gv2-psy-tokens">
                {lexique.top_mots.slice(0, 14).map((m, i) => <span key={i}>{esc(motLexical(m))}</span>)}
              </div>
            </div>
            {Array.isArray(lexique.top_bigrams) && lexique.top_bigrams.length > 0 && (
              <div className="gv2-psy-card gv2-psy-card--plain">
                <div className="gv2-psy-trait-label">Expressions fréquentes</div>
                <div className="gv2-psy-tokens">
                  {lexique.top_bigrams.slice(0, 12).map((b, i) => {
                    const n = b && (b.count ?? b.freq);
                    return <span key={i}>{esc(motLexical(b))}{n > 1 ? ` · ${n}` : ''}</span>;
                  })}
                </div>
              </div>
            )}
          </div>
        </Section>
      )}

      {champs.length > 0 && (
        <Section title="Champs lexicaux détectés">
          <div className="gv2-psy-fields">
            {champs.map((champ, i) => {
              const mots = Array.isArray(champ.words) ? champ.words : Array.isArray(champ.tokens) ? champ.tokens : [];
              const exemple = champ.exemple || (Array.isArray(champ.examples) ? champ.examples[0] : '');
              return <div className="gv2-psy-card gv2-psy-field" key={i}>
                <strong>{esc(String(champ.field || champ.nom || ''))}</strong>
                <div className="gv2-psy-field-meta">
                  {champ.pct != null ? `${champ.pct}% des commentaires` : ''}
                  {champ.count != null ? ` · ${champ.count} occurrences` : ''}
                </div>
                {mots.length > 0 && <div className="gv2-psy-tokens">
                  {mots.slice(0, 5).map((t, j) => <span key={j}>{esc(String(t))}</span>)}
                </div>}
                {exemple && <p>{esc(String(exemple))}</p>}
              </div>;
            })}
          </div>
        </Section>
      )}

      {(Object.keys(mok).length > 0 || Object.keys(iry).length > 0) && (
        <Section title="Signaux de moquerie & ironie"
                 hint="Un enthousiasme ironique n'est pas de l'adhésion.">
          <div className="gv2-psy-metrics">
            <Metric label="Moquerie" value={`${mok.count || 0} (${mok.pct || 0}%)`} hint={mok.level} />
            <Metric label="Ironie" value={`${iry.count || 0} (${iry.pct || 0}%)`} hint={iry.level || (iry.count ? 'détectée' : 'absente')} />
          </div>
          {[...(mok.examples || []), ...(iry.examples || [])].filter(Boolean).length > 0 && <div className="gv2-psy-quotes gv2-psy-mt">
            {[...(mok.examples || []), ...(iry.examples || [])].filter(Boolean).slice(0, 6).map((ex, i) => <blockquote className="gv2-psy-quote" key={i}><p>{citation(itemText(ex))}</p></blockquote>)}
          </div>}
        </Section>
      )}

      {pol.phrase && (
        <Section title="Polarisation de l'audience">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <p className="gv2-psy-polar-phrase">{formatInline(String(pol.phrase))}</p>
            {pol.label && <div className="gv2-psy-metric-hint">{esc(String(pol.label))}{pol.score != null ? ` · score ${pol.score}` : ''}</div>}
          </div>
        </Section>
      )}

      {livrablesPurs.length > 0 && (
        <Section title="Preuves statistiques"
                 hint="Six lectures calculées sans IA, avec leur niveau de confiance.">
          {livrablesPurs.map(([cle, titre]) => <DataInsight key={cle} title={titre} data={livr[cle]} />)}
        </Section>
      )}

      {finOnglet}
    </>}

    {/* ── Psychologie : pourquoi ils agissent comme ils agissent ────────────── */}
    {actif === 'psychologie' && <>
      {LIVRABLES.some(([cle]) => (livr[cle] || {}).conclusion) && (
        <Section title="Insights fondés sur données"
                 hint="Chaque lecture s'appuie sur un chiffre mesuré, pas sur une impression.">
          {LIVRABLES.map(([cle, titre]) => <DataInsight key={cle} title={titre} data={livr[cle]} />)}
        </Section>
      )}

      <Interpretation title="Lecture psychologique" data={interp.psychologique} />
      <Interpretation title="Lecture socio-culturelle" data={interp.socio_culturelle} />

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
          <Statement label="Système de valeurs" text={psy.systeme_de_valeurs} />
          <Statement label="Maturité émotionnelle" text={psy.maturite_emotionnelle} />
        </div>
      </Section>}

      {PSY_SENS.some(([cle]) => psy[cle]) && (
        <Section title="Sens & potentiel"
                 hint="La couche la plus profonde : ce qui est retenu, ce qui cherche à émerger (Munroe, Frankl).">
          <div className="gv2-psy-grid">
            {PSY_SENS.map(([cle, label]) => psy[cle] ? <div className="gv2-psy-card gv2-psy-grid-entry" key={cle}>
              <div className="gv2-psy-grid-title">{label}</div>
              <p className="gv2-psy-sens-text">{formatInline(psy[cle])}</p>
            </div> : null)}
          </div>
        </Section>
      )}

      {PSY_RAPPORTS.some(([cle]) => psy[cle]) && (
        <Section title="Rapports au monde" hint="Comment cette audience se situe face à ce qui structure une décision.">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <div className="gv2-psy-reco-cols">
              {PSY_RAPPORTS.map(([cle, label]) => <Statement key={cle} label={label} text={psy[cle]} />)}
            </div>
          </div>
        </Section>
      )}

      {GRILLE.some(([cle]) => grille[cle]) && (
        <Section title="Grille psychologique"
                 hint="Dix angles, chacun de l'observation mesurée jusqu'à l'action qu'elle appelle.">
          <div className="gv2-psy-grid">
            {GRILLE.map(([cle, label]) => <GridEntry key={cle} label={label} data={grille[cle]} />)}
          </div>
        </Section>
      )}

      {Object.keys(transfo).length > 0 && (
        <Section title="Trajectoire de transformation"
                 hint="D'où part cette audience, ce qui doit se passer, où elle veut arriver.">
          <div className="gv2-psy-grid">
            {TRANSFORMATION_PHASES.map(([cle, titre, phaseChamps]) => (
              <TransformationPhase key={cle} title={titre} fields={phaseChamps} data={transfo[cle]} />
            ))}
          </div>
        </Section>
      )}

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

      {Object.keys(cult).length > 0 && (
        <Section title="Codes & dynamiques culturelles"
                 hint="Les visions du monde, croyances et tensions qui traversent cette audience.">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <div className="gv2-psy-reco-cols">
              <Statement label="Visions du monde" text={cult.visions_du_monde} />
              <Statement label="Tensions culturelles" text={cult.tensions_culturelles} />
              <Statement label="Récits émergents" text={cult.recits_emergents} />
              <Statement label="Dynamique communautaire" text={cult.dynamique_communautaire} />
            </div>
            <div className="gv2-psy-trait-cols">
              <TraitGroup label="Croyances dominantes" items={cult.croyances_dominantes} />
              <TraitGroup label="Références culturelles" items={cult.references_culturelles} />
              <TraitGroup label="Signaux faibles" items={cult.signaux_faibles} />
            </div>
          </div>
        </Section>
      )}

      {finOnglet}
    </>}

    {/* ── Stratégie : quoi faire de cette lecture ─────────────────────────── */}
    {actif === 'strategie' && <>
      {(recos.positionnement || recos.differenciation || recos.strategie_contenu) && (
        <Section title="Positionnement & différenciation">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <Statement label="Positionnement recommandé" text={recos.positionnement} />
            <Statement label="Différenciation" text={recos.differenciation} />
            <Statement label="Stratégie de contenu" text={recos.strategie_contenu} />
          </div>
        </Section>
      )}

      {((recos.angles_narratifs || []).length > 0 || (recos.risques_strategiques || []).length > 0) && (
        <Section title="Récits à porter & risques à éviter">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <div className="gv2-psy-trait-cols">
              <TraitGroup label="Angles narratifs" items={recos.angles_narratifs} tone="pos" />
              <TraitGroup label="Risques stratégiques" items={recos.risques_strategiques} tone="neg" />
            </div>
          </div>
        </Section>
      )}

      {Object.keys(mkt).length > 0 && <Section
        title="Signaux exploitables"
        hint="Ce que cette lecture ouvre comme prises concrètes.">
        <div className="gv2-psy-card gv2-psy-card--plain">
          <Statement label="Positionnement marketing" text={mkt.positionnement_recommande} />
          <div className="gv2-psy-trait-cols">
            <TraitGroup label="Objections visibles" items={mkt.objections_visibles} tone="neg" />
            <TraitGroup label="Objections invisibles" items={mkt.objections_invisibles} tone="neg" />
            <TraitGroup label="Déclencheurs émotionnels" items={mkt.declencheurs_emotionnels} tone="pos" />
            <TraitGroup label="Leviers de conversion" items={mkt.leviers_de_conversion} tone="pos" />
            <TraitGroup label="Opportunités d'offre" items={mkt.opportunites_offre} tone="pos" />
            <TraitGroup label="Opportunités de contenu" items={mkt.opportunites_contenu} tone="pos" />
            <TraitGroup label="Angles de contenu" items={mkt.angles_de_contenu} tone="pos" />
            <TraitGroup label="Sujets qui attirent" items={mkt.sujets_qui_attirent} />
            <TraitGroup label="Sujets qui divisent" items={mkt.sujets_qui_divisent} tone="neg" />
            <TraitGroup label="Risques de communication" items={mkt.risques_communication} tone="neg" />
          </div>
          <TraitGroup label="Accroches performantes" items={mkt.hooks_performants} tone="pos" />
          {(mkt.mots_cles || []).length > 0 && <div className="gv2-psy-statement">
            <div className="gv2-psy-statement-label">Mots-clés de l'audience</div>
            <div className="gv2-psy-tokens">
              {mkt.mots_cles.map((m, i) => <span key={i}>{esc(itemText(m))}</span>)}
            </div>
          </div>}
        </div>
      </Section>}

      {Object.keys(caches).length > 0 && (
        <Section title="Marchés cachés & opportunités"
                 hint="Des segments et opportunités que les données rendent visibles, pas encore exploités.">
          {Array.isArray(caches.segments_detectes) && caches.segments_detectes.length > 0 && (
            <div className="gv2-psy-fields">
              {caches.segments_detectes.map((seg, i) => <div className="gv2-psy-card gv2-psy-field" key={i}>
                <strong>{esc(String(seg.segment || ''))}</strong>
                {seg.taille_estimee && <div className="gv2-psy-field-meta">Taille estimée : {esc(seg.taille_estimee)}</div>}
                {seg.valeur_potentielle && <Statement label="Valeur potentielle" text={seg.valeur_potentielle} />}
                {seg.description && <p>{formatInline(String(seg.description))}</p>}
                {seg.signaux && <p>{formatInline(itemText(seg.signaux))}</p>}
              </div>)}
            </div>
          )}
          <div className="gv2-psy-trait-cols">
            <TraitGroup label="Besoins sous-exprimés" items={caches.besoins_sous_exprimes} />
            <TraitGroup label="Opportunités de niche" items={caches.opportunites_niche} tone="pos" />
            <TraitGroup label="Audiences adjacentes" items={caches.audiences_adjacentes} />
          </div>
          {caches.angle_differentiant && <div className="gv2-psy-reco-message">
            <div className="gv2-psy-statement-label">Angle différentiant</div>
            <blockquote>{formatInline(caches.angle_differentiant)}</blockquote>
          </div>}
        </Section>
      )}

      {Object.keys(ident).length > 0 && (
        <Section title="Cohérence & identité perçues"
                 hint="Ce que ce contenu projette, et ce qui pourrait fragiliser sa crédibilité.">
          <div className="gv2-psy-card gv2-psy-card--plain">
            <div className="gv2-psy-reco-cols">
              <Statement label="Cohérence perçue" text={ident.coherence_percue} />
              <Statement label="Authenticité perçue" text={ident.authenticite_percue} />
              <Statement label="Singularité" text={ident.singularite} />
              <Statement label="Crédibilité" text={ident.credibilite} />
              <Statement label="Confiance générée" text={ident.confiance_generee} />
              <Statement label="Incohérences détectées" text={ident.incaherences_detectees} />
            </div>
            <div className="gv2-psy-trait-cols">
              <TraitGroup label="Points de différenciation" items={ident.points_de_differenciation} tone="pos" />
              <TraitGroup label="Faiblesses narratives" items={ident.faiblesses_narratives} tone="neg" />
            </div>
            <Statement label="Récit dominant" text={ident.recit_dominant} />
          </div>
        </Section>
      )}

      {finOnglet}
    </>}

    {actif === 'personas' && <>
      <div className="gv2-psy-pc-grid">
        {personas.map((persona, index) => <PersonaCard persona={persona} index={index} key={index} />)}
      </div>
      {finOnglet}
    </>}
  </section>;
}

/* ── Résultat — Cross Analyse : la Salle Cross ─────────────────────────────
   Doctrine : on ne fusionne jamais les audiences. Chaque affirmation dit à qui
   elle s'applique (Commun, propre à une audience, opposé), avec l'intensité
   mesurée dans chacune. La conclusion vient d'abord ; chaque audience garde
   son analyse complète, consultable sans quitter la Salle. */

const CROSS_DIM_LABELS = {
  emotions: 'Émotions', fears: 'Peurs', aspirations: 'Aspirations', frustrations: 'Frustrations',
  beliefs: 'Croyances', motivations: 'Motivations', objections: 'Objections', themes: 'Centres d’intérêt',
  behavioral_signals: 'Comportements',
};
const CROSS_MAP_DIMS = ['emotions', 'aspirations', 'fears', 'frustrations', 'motivations', 'beliefs', 'objections', 'themes'];
const CROSS_CONF = { strong: 'solide', moderate: 'modérée', exploratory: 'exploratoire', insufficient: 'insuffisante', high: 'élevée', medium: 'moyenne', low: 'faible' };
const CROSS_KIND = { specifique: 'Propre à', oppose: 'Opposé', intensite: 'Intensité différente' };

// Mêmes mots vides que core/cross_synthesis.py : un « thème » comme merci ou
// vidéo ne dit rien d'une audience et n'est jamais présenté comme un signal.
const CROSS_NOISE = new Set(['merci', 'video', 'videos', 'super', 'bravo', 'top', 'cool', 'bien', 'tres', 'trop', 'chaine',
  'contenu', 'contenus', 'salut', 'bonjour', 'genial', 'excellent', 'moi', 'toi', 'comme', 'tout', 'fait', 'faire',
  'vraiment', 'encore', 'question', 'questions', 'possible', 'serait', 'peut', 'suis', 'tes', 'mes', 'ton', 'mon']);
const crossKey = label => String(label || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
const crossIsNoise = label => !crossKey(label).split(' ').some(word => word.length >= 3 && !CROSS_NOISE.has(word));

function crossAudiences(result) {
  const profiles = Array.isArray(result.source_profiles) ? result.source_profiles : [];
  const sources = Array.isArray(result.sources) ? result.sources : [];
  const base = profiles.length ? profiles : sources.map((source, index) => ({
    source_id: source.source_id, position: index, letter: String.fromCharCode(65 + index),
    title: (source.metadata || {}).title || `Audience ${index + 1}`, channel: (source.metadata || {}).channel || '',
    url: (source.metadata || {}).canonical_url || '', analysis_id: source.analysis_id || '',
    comments: (source.dataset || {}).comments_retained || 0, data_quality: (source.data_quality || {}).level || '', dimensions: {},
  }));
  return base.map((aud, index) => ({ ...aud, index, letter: aud.letter || String.fromCharCode(65 + index) }));
}

function AudienceBadge({ aud, suffix }) {
  if (!aud) return null;
  return <span className="gv2-cross-badge" style={{ '--aud': `var(--gv2-aud-${aud.index % 5})` }}>{aud.letter}{suffix ? ` · ${suffix}` : ''}</span>;
}

function CrossMeter({ audiences, values }) {
  const max = Math.max(1, ...Object.values(values).map(v => Number(v) || 0));
  return <div className="gv2-cross-meter">
    {audiences.map(aud => {
      const raw = values[aud.source_id];
      const present = raw !== undefined && raw !== null;
      return <div key={aud.source_id} style={{ '--aud': `var(--gv2-aud-${aud.index % 5})` }} className={present ? '' : 'is-absent'}>
        <span>{aud.letter}</span>
        <i><b style={{ width: present ? `${Math.max(4, Math.round((Number(raw) || 0) / max * 100))}%` : '0%' }} /></i>
        <em>{present ? (Number(raw) > 1.5 ? `${Math.round(Number(raw))} %` : 'présent') : '—'}</em>
      </div>;
    })}
  </div>;
}

function CrossRow({ dimension, label, badge, children, meter }) {
  return <div className="gv2-cross-row">
    <span className="gv2-cross-row-dim">{CROSS_DIM_LABELS[dimension] || dimension || ''}</span>
    <div className="gv2-cross-row-body"><p>{formatInline(label)}{badge}</p>{children}</div>
    {meter}
  </div>;
}

function CrossEmpty({ children }) {
  return <p className="gv2-cross-empty">{children}</p>;
}

function PlaceInComparison({ aud, synthesis, specific }) {
  const communs = (synthesis.rassemble || []).filter(item => item.per_source.some(p => p.source_id === aud.source_id));
  const propres = (synthesis.separe || []).filter(item => item.per_source.some(p => p.source_id === aud.source_id));
  const mesures = specific.filter(item => (item.sources || []).some(s => s.source_id === aud.source_id)).slice(0, 4);
  if (!communs.length && !propres.length && !mesures.length) return null;
  return <div className="gv2-cross-place">
    <span className="gv2-psy-mono-label">Place dans la comparaison</span>
    <ul>
      {communs.slice(0, 4).map((item, i) => <li key={`c${i}`}><span className="gv2-cross-tag is-common">Commun</span>{formatInline(item.label)}</li>)}
      {propres.slice(0, 4).map((item, i) => <li key={`p${i}`}><span className={`gv2-cross-tag ${item.kind === 'oppose' ? 'is-opposed' : 'is-own'}`}>{item.kind === 'oppose' ? 'Opposé' : 'Propre'}</span>{formatInline(item.label)}</li>)}
      {mesures.map((item, i) => <li key={`m${i}`}><span className="gv2-cross-tag is-own">Propre</span>{formatInline(item.label)}</li>)}
    </ul>
  </div>;
}

function CrossAudienceView({ aud, audiences, onSwitch, onBack, synthesis, specific, onNavigateAgent, onStratege, onCreateur }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  useEffect(() => {
    let live = true;
    setState({ loading: true, data: null, error: '' });
    if (!aud.analysis_id) { setState({ loading: false, data: null, error: 'Cette audience n’a pas d’analyse enregistrée.' }); return undefined; }
    fetchV2(`/history/${encodeURIComponent(aud.analysis_id)}/load`).then(async response => {
      const payload = JSON.parse(await response.text());
      if (!response.ok || !payload?.full_result) throw new Error(payload?.error || 'introuvable');
      if (live) setState({ loading: false, data: { ...payload.full_result, analysis_id: payload.full_result.analysis_id || aud.analysis_id }, error: '' });
    }).catch(() => { if (live) setState({ loading: false, data: null, error: 'L’analyse complète de cette audience n’a pas pu être chargée.' }); });
    return () => { live = false; };
  }, [aud.analysis_id]);

  return <div className="gv2-cross-audience" style={{ '--aud': `var(--gv2-aud-${aud.index % 5})` }}>
    <nav className="gv2-cross-crumb" aria-label="Fil d’Ariane">
      <button type="button" onClick={onBack}>← Synthèse croisée</button>
      <span aria-hidden="true">/</span>
      <span>Audience {aud.letter} · {aud.title}</span>
      <span className="gv2-cross-switch" role="group" aria-label="Changer d’audience">
        {audiences.map(other => <button key={other.source_id} type="button" aria-pressed={other.source_id === aud.source_id}
          style={{ '--aud': `var(--gv2-aud-${other.index % 5})` }} onClick={() => onSwitch(other.source_id)}
          aria-label={`Audience ${other.letter} · ${other.title}`}><i />{other.letter}</button>)}
      </span>
    </nav>
    <PlaceInComparison aud={aud} synthesis={synthesis} specific={specific} />
    {state.loading && <p className="gv2-cross-empty">Chargement de l’analyse complète…</p>}
    {state.error && <p className="gv2-cross-empty">{state.error}</p>}
    {/* Depuis le détail d'une audience, Ariane et le Créateur reçoivent l'analyse de CETTE audience. */}
    {state.data && <PsychoResult data={state.data} onReset={onBack}
      onGoToStratege={onStratege ? d => onStratege(d || state.data) : () => onNavigateAgent?.('stratege')}
      onGoToCreateur={onCreateur ? () => onCreateur({ id: aud.analysis_id, title: aud.title }) : (onNavigateAgent ? () => onNavigateAgent('createur') : undefined)} />}
  </div>;
}

function PsychoCrossResult({ data, onReset, onNavigateAgent, onStrategeCross, onStrategeAudience, onCreateurAudience }) {
  const result = data.result || {};
  const status = data.status || '';
  const audiences = crossAudiences(result);
  const byId = Object.fromEntries(audiences.map(aud => [aud.source_id, aud]));
  const synthesis = result.cross_synthesis && result.cross_synthesis.status === 'completed' ? result.cross_synthesis : { rassemble: [], separe: [] };
  const execSummary = result.executive_summary || {};
  const confidence = result.confidence || {};
  const core = result.common_psychological_core || {};
  const coreText = core.interpretation && typeof core.interpretation === 'object' ? core.interpretation.interpretation
    : (typeof core.interpretation === 'string' ? core.interpretation : '');
  const synthKeys = new Set([
    ...(synthesis.rassemble || []).flatMap(item => [item.label, ...item.per_source.map(p => p.signal)]),
    ...(synthesis.separe || []).flatMap(item => [item.label, ...item.per_source.map(p => p.signal)]),
  ].map(crossKey));
  // Signaux mesurés par libellé exact : on retire les mots vides et ce que la
  // synthèse montre déjà, pour ne jamais afficher deux fois la même chose.
  const convergences = (Array.isArray(result.convergences) ? result.convergences : [])
    .filter(item => !crossIsNoise(item.label) && !synthKeys.has(crossKey(item.label)));
  const divergences = (Array.isArray(result.divergences) ? result.divergences : [])
    .filter(item => !crossIsNoise(item.label) && !synthKeys.has(crossKey(item.label)));
  const oppositions = Array.isArray(result.oppositions) ? result.oppositions : [];
  const specific = (Array.isArray(result.source_specific_signals) ? result.source_specific_signals : [])
    .filter(item => !crossIsNoise(item.label));
  const failedSources = Array.isArray(result.failed_sources) ? result.failed_sources : [];
  const personas = Array.isArray(result.cross_personas) ? result.cross_personas : [];
  const interp = result.cross_interpretation || {};
  const review = interp.dialectic_review || {};
  const totalComments = confidence.total_comments || audiences.reduce((sum, aud) => sum + (Number(aud.comments) || 0), 0);
  const verdict = synthesis.verdict || {};
  const sujets = synthesis.sujets_qui_resolvent || [];
  const interets = synthesis.centres_interet || [];
  const aEviter = synthesis.a_eviter || [];
  const message = synthesis.message_commun || {};

  const [tab, setTab] = useState('synthese');
  const [openSource, setOpenSource] = useState('');

  const tabs = [
    { id: 'synthese', label: 'Synthèse croisée' },
    { id: 'rassemble', label: 'Ce qui les rassemble' },
    { id: 'separe', label: 'Ce qui les sépare' },
    { id: 'carte', label: 'Carte des audiences' },
    ...(personas.length ? [{ id: 'personas', label: 'Personas' }] : []),
    ...(sujets.length || interets.length || aEviter.length || message.message ? [{ id: 'sujets', label: 'Sujets & angles' }] : []),
    { id: 'audiences', label: 'Chaque audience' },
  ];
  const actif = tabs.some(t => t.id === tab) ? tab : 'synthese';
  const opened = openSource && byId[openSource];

  const header = <div className="gv2-cross-head">
    <div>
      <span className="gv2-psy-eyebrow">Le Psychologue · Cross Analyse</span>
      <h1>Salle Cross</h1>
      <div className="gv2-cross-auds">
        {audiences.map(aud => <button key={aud.source_id} type="button" className={`gv2-cross-aud${openSource === aud.source_id ? ' is-open' : ''}`}
          style={{ '--aud': `var(--gv2-aud-${aud.index % 5})` }} onClick={() => setOpenSource(aud.source_id)}
          aria-label={`Ouvrir l’audience ${aud.letter} · ${aud.title}`}>
          <i aria-hidden="true" /><strong>{aud.letter}</strong><span>{aud.title}</span>
          {aud.comments ? <small>{aud.comments} comm.</small> : null}<em aria-hidden="true">→</em>
        </button>)}
      </div>
    </div>
    <button type="button" className="gv2-psy-ghost-btn" onClick={onReset}>← Nouvelle analyse</button>
  </div>;

  if (opened) {
    return <section className="gv2-psy-result gv2-cross-room">
      {header}
      <CrossAudienceView aud={opened} audiences={audiences} onSwitch={setOpenSource} onBack={() => setOpenSource('')}
        synthesis={synthesis} specific={specific} onNavigateAgent={onNavigateAgent}
        onStratege={onStrategeAudience} onCreateur={onCreateurAudience} />
    </section>;
  }

  const sharedRows = synthesis.rassemble || [];
  const separeRows = synthesis.separe || [];
  const specificByAud = audiences.map(aud => ({ aud, items: specific.filter(item => (item.sources || []).some(s => s.source_id === aud.source_id)).slice(0, 6) }));

  return <section className="gv2-psy-result gv2-cross-room">
    {header}

    {(status === 'partial_success' || failedSources.length > 0) && <div className="gv2-psy-cross-warn">
      <strong>Analyse partielle.</strong> {failedSources.length} source{failedSources.length === 1 ? '' : 's'} n'{failedSources.length === 1 ? 'a' : 'ont'} pas pu être analysée{failedSources.length === 1 ? '' : 's'}. Les résultats portent sur {audiences.length} audience{audiences.length === 1 ? '' : 's'} exploitable{audiences.length === 1 ? '' : 's'}.
    </div>}

    <ResultTabs active={actif} onChange={setTab} tabs={tabs} />

    {actif === 'synthese' && <div className="gv2-cross-pane">
      <div className="gv2-cross-verdict">
        <div>
          <span className="gv2-psy-mono-label">Ce que ces audiences ont en commun</span>
          <p className="gv2-cross-verdict-text">{formatInline(verdict.rassemble || execSummary.text || coreText || 'Analyse terminée.')}</p>
          <div className="gv2-cross-conf">
            {confidence.score != null && <span>Confiance <strong>{Math.round(Number(confidence.score) || 0)}</strong>/100</span>}
            {(confidence.level || execSummary.confidence_level) && <span className="gv2-cross-pill">{CROSS_CONF[execSummary.confidence_level || confidence.level] || confidence.level}</span>}
            {totalComments ? <span>{totalComments} commentaires</span> : null}
            <span>{audiences.length} audiences</span>
          </div>
        </div>
        {audiences.length === 2 && <div className="gv2-cross-venn" role="img" aria-label={`Noyau commun entre ${audiences[0].title} et ${audiences[1].title}`}>
          <span className="is-a" style={{ '--aud': 'var(--gv2-aud-0)' }}>{audiences[0].letter}</span>
          <span className="is-b" style={{ '--aud': 'var(--gv2-aud-1)' }}>{audiences[1].letter}</span>
          <strong>{sharedRows[0] ? sharedRows[0].label : (convergences[0] ? convergences[0].label : 'Noyau commun')}</strong>
        </div>}
      </div>
      <div className="gv2-cross-trio">
        <div><span className="gv2-psy-mono-label">Les rassemble</span><p>{formatInline(verdict.rassemble || coreText || `${convergences.length} signal${convergences.length > 1 ? 'aux' : ''} partagé${convergences.length > 1 ? 's' : ''}.`)}</p></div>
        <div><span className="gv2-psy-mono-label">Les sépare</span><p>{formatInline(verdict.separe || `${divergences.length + oppositions.length} différence${divergences.length + oppositions.length > 1 ? 's' : ''} mesurée${divergences.length + oppositions.length > 1 ? 's' : ''}.`)}</p></div>
        <div><span className="gv2-psy-mono-label">À leur dire à toutes</span><p>{formatInline(verdict.a_leur_dire || message.message || 'Disponible après la synthèse croisée.')}</p></div>
      </div>
      {Array.isArray(execSummary.caveats) && execSummary.caveats.length > 0 && <div className="gv2-cross-caveats">
        <span className="gv2-psy-mono-label">Points de prudence</span>
        <ul>{execSummary.caveats.map((caveat, i) => <li key={i}>{formatInline(caveat)}</li>)}</ul>
      </div>}
      {review.status === 'completed' && ((review.challenges || []).length > 0 || (review.alternative_hypotheses || []).length > 0 || review.retained_conclusion) && <details className="gv2-cross-review">
        <summary>Ce qui pourrait contredire cette lecture</summary>
        {(review.challenges || []).length > 0 && <ul>{review.challenges.map((c, i) => <li key={i}><strong>{formatInline(c.claim)}</strong> — {formatInline(c.counter_evidence)}</li>)}</ul>}
        {(review.alternative_hypotheses || []).length > 0 && <><span className="gv2-psy-mono-label">Autres lectures possibles</span><ul>{review.alternative_hypotheses.map((h, i) => <li key={i}>{formatInline(h)}</li>)}</ul></>}
        {review.retained_conclusion && <p><strong>Conclusion retenue après critique :</strong> {formatInline(review.retained_conclusion)}</p>}
      </details>}
    </div>}

    {actif === 'rassemble' && <div className="gv2-cross-pane">
      {sharedRows.length === 0 && convergences.length === 0 && <CrossEmpty>Aucun point commun suffisamment étayé entre ces audiences.</CrossEmpty>}
      <div className="gv2-cross-rows">
        {sharedRows.map((item, i) => <CrossRow key={`s${i}`} dimension={item.dimension} label={item.label}
          badge={<span className="gv2-cross-tag is-common">Commun</span>}
          meter={<CrossMeter audiences={audiences} values={Object.fromEntries(item.per_source.map(p => [p.source_id, p.weight]))} />}>
          {item.interpretation && <p className="gv2-cross-interp">{formatInline(item.interpretation)}</p>}
          {item.per_source.map((p, j) => <blockquote key={j} style={{ '--aud': `var(--gv2-aud-${(byId[p.source_id] || {}).index % 5})` }}>
            <AudienceBadge aud={byId[p.source_id]} /> {formatInline(p.signal)}</blockquote>)}
        </CrossRow>)}
        {convergences.map((item, i) => {
          const lecture = (interp.convergence_interpretations || []).find(c => c.insight_id === item.insight_id);
          return <CrossRow key={`m${i}`} dimension={item.category} label={item.category === 'behavioral_signals' ? libelle(item.label) : item.label}
            badge={<span className="gv2-cross-tag is-common">Mesuré dans {item.sources_count} audiences</span>}
            meter={<CrossMeter audiences={audiences} values={Object.fromEntries((item.sources || []).map(s => [s.source_id, s.weight]))} />}>
            {lecture && <p className="gv2-cross-interp">{formatInline(lecture.interpretation)}</p>}
          </CrossRow>;
        })}
      </div>
    </div>}

    {actif === 'separe' && <div className="gv2-cross-pane">
      <div className="gv2-cross-rows">
        {separeRows.map((item, i) => {
          const aud = item.per_source.length === 1 ? byId[item.per_source[0].source_id] : null;
          return <CrossRow key={`s${i}`} dimension={item.dimension} label={item.label}
            badge={item.kind === 'oppose' ? <span className="gv2-cross-tag is-opposed">Opposé</span>
              : aud ? <AudienceBadge aud={aud} suffix={CROSS_KIND.specifique} /> : <span className="gv2-cross-tag is-own">{CROSS_KIND[item.kind]}</span>}
            meter={<CrossMeter audiences={audiences} values={Object.fromEntries(item.per_source.map(p => [p.source_id, p.weight]))} />}>
            {item.interpretation && <p className="gv2-cross-interp">{formatInline(item.interpretation)}</p>}
            {item.per_source.map((p, j) => <blockquote key={j} style={{ '--aud': `var(--gv2-aud-${(byId[p.source_id] || {}).index % 5})` }}>
              <AudienceBadge aud={byId[p.source_id]} /> {formatInline(p.note || p.signal)}</blockquote>)}
          </CrossRow>;
        })}
        {divergences.map((item, i) => {
          const lecture = (interp.divergence_interpretations || []).find(c => c.insight_id === item.insight_id);
          return <CrossRow key={`d${i}`} dimension={item.category} label={item.label}
            badge={<span className="gv2-cross-tag is-own">Intensité différente</span>}
            meter={<CrossMeter audiences={audiences} values={Object.fromEntries((item.sources || []).map(s => [s.source_id, s.weight]))} />}>
            {lecture && <p className="gv2-cross-interp">{formatInline(lecture.interpretation)}</p>}
          </CrossRow>;
        })}
        {oppositions.map((item, i) => <CrossRow key={`o${i}`} dimension="beliefs" label={item.observation || 'Positions opposées'}
          badge={<span className="gv2-cross-tag is-opposed">Opposé</span>}
          meter={<div className="gv2-cross-meter">{(item.source_positions || []).map((pos, j) => { const aud = byId[pos.source_id]; return aud ? <div key={j} style={{ '--aud': `var(--gv2-aud-${aud.index % 5})` }}><span>{aud.letter}</span><em>{libelle(pos.position)} {Math.round(pos.pct)} %</em></div> : null; })}</div>} />)}
      </div>
      {specificByAud.some(group => group.items.length) && <div className="gv2-cross-own">
        <span className="gv2-psy-mono-label">Signaux propres à une seule audience</span>
        <div className="gv2-cross-own-grid">
          {specificByAud.filter(group => group.items.length).map(group => <div key={group.aud.source_id} style={{ '--aud': `var(--gv2-aud-${group.aud.index % 5})` }}>
            <AudienceBadge aud={group.aud} /><strong className="gv2-cross-own-title">{group.aud.title}</strong>
            <ul>{group.items.map((item, j) => <li key={j}><em>{CROSS_DIM_LABELS[item.category] || item.category}</em>{formatInline(item.category === 'behavioral_signals' ? libelle(item.label) : item.label)}</li>)}</ul>
          </div>)}
        </div>
      </div>}
      {separeRows.length === 0 && divergences.length === 0 && oppositions.length === 0 && specific.length === 0 && <CrossEmpty>Aucune différence mesurée : ces audiences se ressemblent fortement.</CrossEmpty>}
    </div>}

    {actif === 'carte' && <div className="gv2-cross-pane">
      <p className="gv2-cross-lede">La vue de l’analyste : pour chaque dimension, ce que chaque audience exprime le plus.</p>
      <div className="gv2-cross-map-scroll">
        <table className="gv2-cross-map">
          <thead><tr><th scope="col">Dimension</th>{audiences.map(aud => <th scope="col" key={aud.source_id} style={{ '--aud': `var(--gv2-aud-${aud.index % 5})` }}><AudienceBadge aud={aud} /> {aud.title}</th>)}</tr></thead>
          <tbody>
            {CROSS_MAP_DIMS.filter(dim => audiences.some(aud => ((aud.dimensions || {})[dim] || []).length)).map(dim => <tr key={dim}>
              <th scope="row">{CROSS_DIM_LABELS[dim]}</th>
              {audiences.map(aud => <td key={aud.source_id}>
                {((aud.dimensions || {})[dim] || []).slice(0, 3).map((signal, i) => <div key={i} className="gv2-cross-map-cell">
                  <span>{formatInline(signal.label)}</span>{signal.weight > 1.5 && <small>{Math.round(signal.weight)} %</small>}
                </div>)}
                {!((aud.dimensions || {})[dim] || []).length && <span className="gv2-cross-map-none">—</span>}
              </td>)}
            </tr>)}
          </tbody>
        </table>
      </div>
    </div>}

    {actif === 'personas' && <div className="gv2-cross-pane">
      <div className="gv2-cross-personas">
        {personas.map((persona, index) => <article className="gv2-cross-persona" key={index}>
          <span className="gv2-psy-mono-label">{(persona.source_ids || []).length > 1 ? 'Persona croisé' : 'Persona propre'}</span>
          <h3>{persona.name || 'Persona'}</h3>
          <div className="gv2-cross-persona-auds">{(persona.source_ids || []).map(id => <AudienceBadge key={id} aud={byId[id]} />)}
            {persona.confidence_level && <span className="gv2-cross-pill">{CROSS_CONF[persona.confidence_level] || persona.confidence_level}</span>}</div>
          {persona.description && <p>{formatInline(persona.description)}</p>}
          {Array.isArray(persona.signals) && persona.signals.length > 0 && <div className="gv2-psy-tokens">{persona.signals.map((s, i) => <span key={i}>{typeof s === 'string' ? s : s.label || ''}</span>)}</div>}
        </article>)}
      </div>
      <p className="gv2-cross-lede">Les personas détaillés de chaque audience sont dans l’onglet « Chaque audience ».</p>
    </div>}

    {actif === 'sujets' && <div className="gv2-cross-pane">
      {message.message && <div className="gv2-cross-message">
        <span className="gv2-psy-mono-label">Un message pour toutes ces audiences</span>
        <p>{formatInline(message.message)}</p>
        {(message.nuances || []).length > 0 && <ul>{message.nuances.map((n, i) => <li key={i}><AudienceBadge aud={byId[n.source_id]} /> {formatInline(n.nuance)}</li>)}</ul>}
      </div>}
      <div className="gv2-cross-topics">
        {sujets.length > 0 && <div><span className="gv2-psy-mono-label">Sujets qui résolvent un problème commun</span><ol>
          {sujets.map((t, i) => <li key={i}><strong>{formatInline(t.title)}</strong><small>{formatInline(t.why)}</small><span>{t.source_ids.map(id => <AudienceBadge key={id} aud={byId[id]} />)}</span></li>)}
        </ol></div>}
        {interets.length > 0 && <div><span className="gv2-psy-mono-label">Centres d’intérêt</span><ul>
          {interets.map((t, i) => <li key={i}><strong>{formatInline(t.label)}</strong><small>{formatInline(t.why)}</small><span>{t.source_ids.map(id => <AudienceBadge key={id} aud={byId[id]} />)}</span></li>)}
        </ul></div>}
        {aEviter.length > 0 && <div><span className="gv2-psy-mono-label">À éviter</span><ul>
          {aEviter.map((t, i) => <li key={i}><strong>{formatInline(t.label)}</strong><small>{formatInline(t.why)}</small><span>{t.source_ids.map(id => <AudienceBadge key={id} aud={byId[id]} />)}</span></li>)}
        </ul></div>}
      </div>
      {onNavigateAgent && <div className="gv2-psy-next is-final">
        <span className="gv2-psy-next-hint">Transformer cette lecture croisée</span>
        <div className="gv2-psy-next-actions">
          <button type="button" className="gv2-psy-ghost-btn" onClick={() => onNavigateAgent('createur')}>Un message commun · Créateur →</button>
          <button type="button" className="gv2-psy-primary-btn" onClick={() => onStrategeCross ? onStrategeCross(data) : onNavigateAgent('stratege')}>Construire la stratégie · Ariane →</button>
        </div>
      </div>}
    </div>}

    {actif === 'audiences' && <div className="gv2-cross-pane">
      <p className="gv2-cross-lede">Chaque audience garde son analyse complète — synthèse, tableau de bord, psychologie, stratégie, personas — comme une analyse classique.</p>
      <div className="gv2-cross-solo">
        {audiences.map(aud => <button type="button" key={aud.source_id} style={{ '--aud': `var(--gv2-aud-${aud.index % 5})` }} onClick={() => setOpenSource(aud.source_id)}>
          <AudienceBadge aud={aud} suffix="Audience" />
          <strong>{aud.title}</strong>
          <span>{[aud.channel, aud.comments ? `${aud.comments} commentaires` : '', aud.data_quality ? `qualité ${qualityMeta(aud.data_quality).label.toLowerCase()}` : ''].filter(Boolean).join(' · ')}</span>
          <em>Ouvrir l’analyse complète →</em>
        </button>)}
      </div>
    </div>}
  </section>;
}

/* ── Racine ──────────────────────────────────────────────────────────── */

export function PsychologueView({ workspace, onWorkspaceChange, onNavigateAgent, openAnalysisRequest, onAnalysisReady }) {
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
    // Le backend écrit qui/insight/action ; synthese/insight_cle/action_prioritaire
    // sont les anciens noms, gardés pour les analyses sauvegardées avant.
    const qui = brief.qui || brief.synthese;
    const insight = brief.insight || brief.insight_cle;
    const action = brief.action || brief.action_prioritaire;
    const recos = data.recommandations || {};
    if (qui) lines.push('Audience : ' + qui);
    if (insight) lines.push('Insight clé : ' + insight);
    if (action) lines.push('Action : ' + action);
    if (recos.verite_de_l_audience) lines.push("Vérité de l'audience : " + recos.verite_de_l_audience);
    if (recos.message_central) lines.push('Message central : ' + recos.message_central);
    const motiv = (psycho.motivations_profondes || []).slice(0, 2).map(m => typeof m === 'string' ? m : JSON.stringify(m));
    if (motiv.length) lines.push('Motivations : ' + motiv.join(', '));
    const frustr = (psycho.frustrations || []).slice(0, 2).map(f => typeof f === 'string' ? f : JSON.stringify(f));
    if (frustr.length) lines.push('Frustrations : ' + frustr.join(', '));
    const hooks = (marketing.hooks_performants || []).slice(0, 2);
    if (hooks.length) lines.push('Hooks : ' + hooks.join(' | '));
    try {
      window.sessionStorage.setItem('gabriel_for_stratege', JSON.stringify({
        schema_version: 1,
        created_at: Date.now(),
        analysis_id: data.analysis_id,
        folder_id: workspace?.folder_id || '',
        psycho_brief: lines.join('\n'),
        psycho_data: {
          brief, psychologie: psycho, emotions: data.emotions || {}, marketing,
          kpis: data.kpis || {}, aspirations: data.aspirations || {},
          personas: data.personas || [], distribution: data.distribution || {},
          recommandations: recos, demographique: data.demographique || {},
        },
      }));
    } catch (_) { /* sessionStorage peut être indisponible (navigation privée) */ }
    onNavigateAgent?.('stratege');
  }

  // Cross Analyse → Ariane : le handoff porte l'identifiant de la Cross (le serveur la
  // résout en synthèse croisée vérifiée) et un résumé lisible pour l'écran d'Ariane.
  function goToStrategeFromCross(crossData) {
    const res = crossData?.result || {};
    const verdict = (res.cross_synthesis || {}).verdict || {};
    const message = ((res.cross_synthesis || {}).message_commun || {}).message;
    const audiences = crossAudiences(res);
    const clean = t => String(t || '').replace(/\*+/g, '').trim();
    const lines = [];
    if (audiences.length) lines.push('Audiences comparées : ' + audiences.map(a => `${a.letter} = ${a.title}`).join(' ; '));
    if (verdict.rassemble) lines.push('Ce qui les rassemble : ' + clean(verdict.rassemble));
    if (verdict.separe) lines.push('Ce qui les sépare : ' + clean(verdict.separe));
    if (verdict.a_leur_dire) lines.push('À leur dire : ' + clean(verdict.a_leur_dire));
    if (message) lines.push('Message commun : ' + clean(message));
    try {
      window.sessionStorage.setItem('gabriel_for_stratege', JSON.stringify({
        schema_version: 1,
        created_at: Date.now(),
        analysis_id: res.cross_analysis_id || crossData?.cross_analysis_id,
        folder_id: workspace?.folder_id || '',
        psycho_brief: lines.join('\n'),
      }));
    } catch (_) { /* sessionStorage peut être indisponible (navigation privée) */ }
    onNavigateAgent?.('stratege');
  }

  // Depuis le détail d'une audience de la Salle Cross, le Créateur écrit pour cette audience.
  function goToCreateurFor(analysis) {
    if (analysis?.id) onAnalysisReady?.(analysis);
    onNavigateAgent?.('createur');
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
      const startedAt = Date.now();
      let networkFailures = 0;
      while (Date.now() - startedAt < ANALYSIS_MAX_WAIT_MS) {
        await pause(POLL_MS);
        if (!aliveRef.current) return;
        let payload;
        try {
          const response = await fetchV2(`/status/${encodeURIComponent(jobId)}`);
          if (isLoginResponse(response)) { window.location.assign('/login'); return; }
          payload = await readApiPayload(response, 'Le suivi de l’analyse');
          networkFailures = 0;
        } catch (error) {
          // Serveur qui redémarre ou réseau qui saute : on réessaie avant d'abandonner.
          networkFailures += 1;
          if (networkFailures >= MAX_NETWORK_FAILURES) throw new Error('La connexion au serveur est perdue. Relancez l’analyse.');
          continue;
        }
        if (payload.status === 'done') {
          setResult(payload.data); setResultKind('single'); setStage('result');
          try { window.localStorage.removeItem(PENDING_JOB_KEY); } catch (_) {}
          await onWorkspaceChange?.();
          return;
        }
        if (['error', 'interrupted', 'not_found'].includes(payload.status)) {
          throw new Error(payload.error || 'L’analyse a été interrompue.');
        }
        setProgress(Math.min(95, Math.round(((Date.now() - startedAt) / ANALYSIS_EXPECTED_MS) * 100)));
        if (payload.step) setStep(payload.step);
      }
      throw new Error('L’analyse prend plus de temps que prévu et continue en arrière-plan. Retrouvez-la dans le menu Analyses dans quelques minutes.');
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
      const startedAt = Date.now();
      let networkFailures = 0;
      while (Date.now() - startedAt < CROSS_MAX_WAIT_MS) {
        await pause(POLL_MS);
        if (!aliveRef.current) return;
        let payload;
        try {
          const response = await fetchV2(`/api/v2/agents/psychologue/cross-analyses/${encodeURIComponent(crossId)}/status`);
          if (isLoginResponse(response)) { window.location.assign('/login'); return; }
          payload = await readApiPayload(response, 'Le suivi de la Cross Analyse');
          networkFailures = 0;
        } catch (error) {
          networkFailures += 1;
          if (networkFailures >= MAX_NETWORK_FAILURES) throw new Error('La connexion au serveur est perdue. Relancez la Cross Analyse.');
          continue;
        }
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
        setProgress(Math.min(95, Math.round(((Date.now() - startedAt) / CROSS_EXPECTED_MS) * 100)));
        if (payload.step) setStep(payload.step);
      }
      throw new Error('La Cross Analyse prend plus de temps que prévu et continue en arrière-plan. Retrouvez-la dans le menu Cross Analyses dans quelques minutes.');
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

  const [recentAnalyses, setRecentAnalyses] = useState([]);
  useEffect(() => {
    let live = true;
    const requete = fetchV2('/history');
    if (!requete || typeof requete.then !== 'function') return undefined;
    requete.then(async response => {
      if (!response || !response.ok) return;
      const payload = JSON.parse(await response.text());
      const liste = Array.isArray(payload) ? payload : Array.isArray(payload?.history) ? payload.history : [];
      if (live) setRecentAnalyses(liste.filter(item => item && item.analysis_id));
    }).catch(() => { /* l'accueil reste utilisable sans historique */ });
    return () => { live = false; };
  }, []);

  function openSavedAnalysis(analysisId) {
    fetchV2(`/history/${encodeURIComponent(analysisId)}/load`).then(async response => {
      const payload = JSON.parse(await response.text());
      if (!response.ok || !payload?.full_result) throw new Error(payload?.error || 'introuvable');
      setResult({ ...payload.full_result, analysis_id: payload.full_result.analysis_id || analysisId });
      setResultKind('single'); setStage('result');
    }).catch(() => {
      setStatusMsg('Cette analyse n’a pas pu être rouverte. Réessayez dans un instant.'); setStatusTone('error');
    });
  }

  // L'analyse affichée devient le contexte par défaut des autres agents (Créateur).
  useEffect(() => {
    if (result?.analysis_id && onAnalysisReady) {
      onAnalysisReady({ id: result.analysis_id, title: String(result.video_context || result.source_label || 'Dernière analyse').slice(0, 90) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.analysis_id]);

  // Une Cross Analyse ouverte devient aussi ce contexte : le Créateur écrit
  // alors depuis la synthèse croisée, audiences distinguées.
  useEffect(() => {
    const id = crossResult?.cross_analysis_id;
    if (!id || !onAnalysisReady || !['completed', 'partial_success'].includes(crossResult?.status)) return;
    const titres = crossAudiences(crossResult.result || {}).map(aud => aud.title).filter(Boolean);
    onAnalysisReady({ id, cross: true, title: `Cross Analyse · ${titres.join(' × ') || id}`.slice(0, 90) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossResult?.cross_analysis_id, crossResult?.status]);

  // Une analyse choisie dans le menu s'ouvre ici, même si l'écran était déjà affiché.
  useEffect(() => {
    if (openAnalysisRequest?.id) openSavedAnalysis(openAnalysisRequest.id);
    if (openAnalysisRequest?.crossId) openSavedCross(openAnalysisRequest.crossId);
    if (openAnalysisRequest?.startCross) { reset(); if (!crossMode) toggleCrossMode(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openAnalysisRequest?.at]);

  function openSavedCross(crossId) {
    fetchV2(`/api/v2/agents/psychologue/cross-analyses/${encodeURIComponent(crossId)}`).then(async response => {
      const payload = JSON.parse(await response.text());
      if (!response.ok || !payload?.success || !payload.result) throw new Error(payload?.error || 'introuvable');
      setCrossResult(payload); setResultKind('cross'); setStage('result');
    }).catch(() => {
      setStatusMsg('Cette Cross Analyse n’a pas pu être rouverte. Réessayez dans un instant.'); setStatusTone('error');
    });
  }

  function suggest(mode) {
    if (mode === 'cross') { if (!crossMode) toggleCrossMode(); changeTab('link'); }
    else {
      if (crossMode) toggleCrossMode();
      changeTab(mode);
    }
    // Le champ qui correspond à l'intention prend le focus : on peut coller tout de suite.
    window.setTimeout(() => {
      const champ = document.querySelector('.gv2-psy-composer-field');
      if (champ && typeof champ.focus === 'function') champ.focus();
      if (champ && typeof champ.scrollIntoView === 'function') champ.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 0);
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
      recentAnalyses={recentAnalyses} onOpenAnalysis={openSavedAnalysis}
      onSuggest={suggest} onNavigateAgent={onNavigateAgent}
    />;

  if (stage === 'loading') content = <PsychoLoading progress={progress} step={step} isCross={resultKind === 'cross'} crossSources={crossSources} />;
  if (stage === 'error') content = <PsychoError message={errorMsg} onRetry={reset} />;
  if (stage === 'result' && resultKind === 'cross' && crossResult) content = <PsychoCrossResult data={crossResult} onReset={reset} onNavigateAgent={onNavigateAgent}
    onStrategeCross={goToStrategeFromCross} onStrategeAudience={goToStratege} onCreateurAudience={goToCreateurFor} />;
  if (stage === 'result' && result) content = <PsychoResult data={result} onReset={reset} onGoToStratege={goToStratege}
                                   onGoToCreateur={onNavigateAgent ? () => onNavigateAgent('createur') : undefined} />;

  return <div className="gv2-psy-view">{content}</div>;
}
