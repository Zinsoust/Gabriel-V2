import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Icon } from '../icons.jsx';
import { agents } from '../agent-registry.js';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

const prompts = [
  { label: 'Post LinkedIn', text: 'Écris un post LinkedIn expert avec une conclusion actionnable autour de mon offre principale.' },
  { label: 'Vidéo courte', text: 'Écris un script vidéo court qui traite l’objection principale de mon audience.' },
  { label: 'Séquence email', text: 'Rédige une séquence email qui transforme l’intérêt en prise de rendez-vous.' },
];

const formatLabels = {
  script: 'Script', youtube: 'Script YouTube', tiktok: 'TikTok / Reels', linkedin: 'Post LinkedIn', post: 'Thread', email: 'Séquence email', sales_page: 'Page de vente',
};

const creatorFormatTabs = [
  { value: 'linkedin', label: 'Post' },
  { value: 'script', label: 'Script' },
  { value: 'post', label: 'Thread' },
];

function makeMessage(role, kind, payload = {}) {
  return { id: `${kind}-${Date.now()}-${Math.random().toString(16).slice(2)}`, role, kind, ...payload };
}

function textOf(result) {
  if (typeof result === 'string') return result.trim();
  const candidates = [
    result?.full_text,
    result?.text,
    result?.content?.full_text,
    result?.content?.text,
    result?.content,
  ];
  return candidates.find(value => typeof value === 'string' && value.trim())?.trim() || '';
}

function wordCount(value) {
  return String(value || '').trim().split(/\s+/).filter(Boolean).length;
}

// Les contenus du Créateur arrivent en texte Markdown léger. Le rendu reste
// volontairement local et sans HTML injecté : gras, italique et code gardent
// leur sens éditorial sans exposer la conversation à un rendu arbitraire.
// Emplacements posés par la garde anti-invention ou par le Créateur lui-même :
// ils doivent sauter aux yeux, pour être complétés avant publication.
const PLACEHOLDER_PATTERN = /^\[(?:[^\]\n]*(?:à vérifier|à insérer|à ajouter|à citer|à filmer|réel|réelle|nom du|nom de|lien|montant|pourcentage)[^\]\n]*)\]$/i;

function renderInline(value, keyPrefix) {
  const chunks = String(value || '').split(/(\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+?`|\*[^*\n]+?\*|_[^_\n]+?_|\[[^\]\n]{2,90}\])/g);
  return chunks.map((chunk, index) => {
    const key = `${keyPrefix}-${index}`;
    if (PLACEHOLDER_PATTERN.test(chunk)) return <mark key={key} className="gv2-cdoc-placeholder" title="À compléter avec une donnée réelle avant publication">{chunk.slice(1, -1)}</mark>;
    if (/^\*\*[^*]+\*\*$/.test(chunk) || /^__[^_]+__$/.test(chunk)) return <strong key={key}>{chunk.slice(2, -2)}</strong>;
    if (/^`[^`]+`$/.test(chunk)) return <code key={key}>{chunk.slice(1, -1)}</code>;
    if (/^\*[^*]+\*$/.test(chunk) || /^_[^_]+_$/.test(chunk)) return <em key={key}>{chunk.slice(1, -1)}</em>;
    return chunk;
  });
}

function renderCreation(value) {
  const blocks = String(value || '').trim().split(/\n{2,}/).filter(Boolean);
  return blocks.map((block, index) => {
    const lines = block.split('\n').map(line => line.trim()).filter(Boolean);
    const heading = lines.length === 1 && lines[0].match(/^(#{1,3})\s+(.+)/);
    const isBullets = lines.length > 1 && lines.every(line => /^(?:[-–•])\s+/.test(line));
    const isOrdered = lines.length > 1 && lines.every(line => /^\d+[.)]\s+/.test(line));
    const isQuote = lines.length > 0 && lines.every(line => /^>\s?/.test(line));
    const isRule = lines.length === 1 && /^(?:---+|\*\*\*+|___+)$/.test(lines[0]);
    if (isRule) return <hr key={index} />;
    if (heading) {
      const Heading = heading[1].length === 1 ? 'h2' : 'h3';
      return <Heading key={index}>{renderInline(heading[2], `heading-${index}`)}</Heading>;
    }
    if (isQuote) return <blockquote key={index}><p>{renderInline(lines.map(line => line.replace(/^>\s?/, '')).join(' '), `quote-${index}`)}</p></blockquote>;
    if (isBullets) return <ul key={index}>{lines.map((line, lineIndex) => <li key={lineIndex}>{renderInline(line.replace(/^(?:[-–•])\s+/, ''), `bullet-${index}-${lineIndex}`)}</li>)}</ul>;
    if (isOrdered) return <ol key={index}>{lines.map((line, lineIndex) => <li key={lineIndex}>{renderInline(line.replace(/^\d+[.)]\s+/, ''), `ordered-${index}-${lineIndex}`)}</li>)}</ol>;
    // Bloc mixte (une phrase puis des puces) : le modèle glisse souvent une
    // liste au milieu d'un paragraphe. On garde la liste au lieu de la coller.
    if (lines.some(line => /^(?:[-–•])\s+/.test(line))) {
      const groupes = [];
      lines.forEach(line => {
        const puce = /^(?:[-–•])\s+/.test(line);
        const dernier = groupes[groupes.length - 1];
        if (dernier && dernier.puce === puce) dernier.lignes.push(line);
        else groupes.push({ puce, lignes: [line] });
      });
      return <React.Fragment key={index}>{groupes.map((groupe, g) => groupe.puce
        ? <ul key={g}>{groupe.lignes.map((line, l) => <li key={l}>{renderInline(line.replace(/^(?:[-–•])\s+/, ''), `mixed-${index}-${g}-${l}`)}</li>)}</ul>
        : <p key={g}>{renderInline(groupe.lignes.join(' '), `mixed-${index}-${g}`)}</p>)}</React.Fragment>;
    }
    return <p key={index}>{renderInline(lines.join(' '), `paragraph-${index}`)}</p>;
  });
}

/* ── Rendu structuré d'une création ─────────────────────────────────────────
   Chaque format du Créateur renvoie un JSON riche (séquences minutées, notes
   de réalisation, accroche alternative, emails, FAQ…). L'afficher en un seul
   bloc de texte faisait perdre cette structure — et masquait les notes de
   réalisation. Ce rendu lit n'importe quel format à partir de clés connues ;
   tout ce qui n'est pas reconnu est affiché quand même, jamais jeté. */
const CDOC_LABELS = {
  angle_principal: 'Angle', angle_central: 'Angle', angle_fil_rouge: 'Fil rouge', angle_prioritaire: 'Angle prioritaire',
  fil_conducteur: 'Fil conducteur', emotion_cible: 'Émotion visée', emotion_fil: 'Émotion', emotion_activee: 'Émotion activée',
  emotion_visee: 'Émotion visée', hook_principal: 'Accroche', hook: 'Accroche', hook_ouverture: 'Accroche d’ouverture',
  accroche: 'Accroche', premiere_ligne: 'Première ligne', variante_hook: 'Accroche alternative',
  introduction: 'Introduction', insight_central: 'Idée centrale', conclusion: 'Conclusion', cta: 'Appel à l’action',
  cta_final: 'Appel à l’action', question_cta: 'Question finale', insight_chute: 'Chute', chute: 'Chute', corps: 'Corps',
  probleme: 'Problème', retournement: 'Retournement', direction: 'Direction', texte_a_lecran: 'Texte à l’écran',
  contexte: 'Contexte', climax: 'Climax', derniere_phrase: 'Dernière phrase', ouverture: 'Ouverture',
  sous_titre: 'Sous-titre', agitation: 'Agitation', solution: 'Solution', preuve: 'Preuve', offre_detail: 'Offre',
  garantie: 'Garantie', prix_et_cta: 'Prix et appel à l’action', objet: 'Objet', preview_text: 'Aperçu',
  objectif: 'Objectif', texte: 'Texte', contenu: 'Contenu', exemple: 'Exemple', transition: 'Transition',
  texte_principal: 'Texte principal', hook_visuel: 'Accroche visuelle', sous_titres: 'Sous-titres', reponse: 'Réponse',
  hook_exemple: 'Exemple d’accroche', tension_exploitee: 'Tension exploitée', pourquoi_ca_marche: 'Pourquoi ça marche',
  difficulte: 'Difficulté', canal: 'Canal', hashtags: 'Hashtags', persona_cible: 'Persona',
  clarte: 'Clarté', coherence_strategique: 'Cohérence stratégique', emotion: 'Émotion', note_globale: 'Note globale',
  originalite: 'Originalité', pertinence: 'Pertinence', persuasion: 'Persuasion', impact: 'Impact',
  note_realisateur: 'Réalisation', notes_montage: 'Montage', notes_orateur: 'Notes de l’orateur',
  notes_production: 'Production', note_strategique: 'Note stratégique', angle_utilise: 'Angle', angle: 'Angle',
};
const CDOC_LISTS = { sections: 'Séquences', parties: 'Parties', posts: 'Publications', sequence: 'Emails',
  publicites: 'Publicités', hooks: 'Accroches', angles: 'Angles', faq: 'Questions fréquentes', chapitres: 'Chapitres' };
const CDOC_TITLE = ['titre_video', 'headline', 'titre', 'titre_interne'];
const CDOC_META = ['duree_estimee', 'duree', 'longueur_estimee', 'format_recommande', 'format'];
const CDOC_CONTEXT = ['angle_principal', 'angle_central', 'angle_fil_rouge', 'angle_prioritaire', 'fil_conducteur', 'emotion_cible', 'emotion_fil', 'emotion_activee'];
const CDOC_HIGHLIGHT = ['hook_principal', 'hook_ouverture', 'hook', 'accroche', 'premiere_ligne'];
const CDOC_NOTES = ['note_realisateur', 'notes_montage', 'notes_orateur', 'notes_production', 'note_strategique', 'pourquoi_ca_marche'];
const CDOC_TIME = ['secondes', 'temps', 'duree'];
const CDOC_ITEM_LABEL = ['section', 'titre', 'titre_interne', 'objet', 'question', 'type', 'format'];
const CDOC_SKIP = new Set(['content_type', 'success', 'parse_error', 'refined', 'instruction', 'numero']);

const cdocLabel = key => CDOC_LABELS[key] || key.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
const cdocText = value => Array.isArray(value) ? value.map(v => (typeof v === 'object' ? JSON.stringify(v) : String(v))).join('\n') : String(value ?? '');

function isStructuredCreation(content) {
  return Boolean(content && typeof content === 'object' && !Array.isArray(content)
    && Object.keys(content).some(key => CDOC_LISTS[key] || CDOC_TITLE.includes(key) || CDOC_HIGHLIGHT.includes(key)));
}

function CdocField({ name, value, keyPrefix }) {
  if (value == null || value === '' || (Array.isArray(value) && !value.length)) return null;
  if (Array.isArray(value) && value.every(v => typeof v === 'string' && v.length < 40)) {
    return <div className="gv2-cdoc-field"><span className="gv2-cdoc-label">{cdocLabel(name)}</span>
      <div className="gv2-cdoc-tokens">{value.map((v, i) => <span key={i}>{v}</span>)}</div></div>;
  }
  const note = CDOC_NOTES.includes(name);
  return <div className={`gv2-cdoc-field${note ? ' is-note' : ''}`}>
    <span className="gv2-cdoc-label">{cdocLabel(name)}</span>
    <div className="gv2-cdoc-body">{renderCreation(cdocText(value)).map((node, i) => React.cloneElement(node, { key: `${keyPrefix}-${i}` }))}</div>
  </div>;
}

function CreationDocument({ content }) {
  const used = new Set(CDOC_SKIP);
  const take = keys => keys.find(key => content[key] && typeof content[key] === 'string' && !used.has(key) && used.add(key));
  const titleKey = take(CDOC_TITLE);
  const metaKeys = CDOC_META.filter(key => typeof content[key] === 'string' && content[key] && !used.has(key) && used.add(key));
  const contextKeys = CDOC_CONTEXT.filter(key => content[key] && !used.has(key) && used.add(key));
  const highlightKey = take(CDOC_HIGHLIGHT);
  const listKeys = Object.keys(CDOC_LISTS).filter(key => Array.isArray(content[key]) && content[key].length && used.add(key));
  const rest = Object.keys(content).filter(key => !used.has(key));
  const notesLast = [...rest.filter(k => !CDOC_NOTES.includes(k) && k !== 'variante_hook'), ...rest.filter(k => k === 'variante_hook'), ...rest.filter(k => CDOC_NOTES.includes(k))];

  return <div className="gv2-cdoc">
    {(titleKey || metaKeys.length > 0) && <header className="gv2-cdoc-head">
      {titleKey && <h2>{renderInline(content[titleKey], 'titre')}</h2>}
      {metaKeys.length > 0 && <div className="gv2-cdoc-meta">{metaKeys.map(key => <span key={key}>{content[key]}</span>)}</div>}
    </header>}
    {contextKeys.length > 0 && <dl className="gv2-cdoc-context">{contextKeys.map(key => <div key={key}>
      <dt>{cdocLabel(key)}</dt><dd>{renderInline(cdocText(content[key]), key)}</dd>
    </div>)}</dl>}
    {highlightKey && <div className="gv2-cdoc-highlight">
      <span className="gv2-cdoc-label">{cdocLabel(highlightKey)}</span>
      <p>{renderInline(content[highlightKey], 'accroche')}</p>
    </div>}
    {listKeys.map(listKey => <section className="gv2-cdoc-list" key={listKey}>
      <h3 className="gv2-cdoc-list-title">{CDOC_LISTS[listKey]}<span>{content[listKey].length}</span></h3>
      <ol>{content[listKey].map((item, index) => {
        if (typeof item !== 'object' || item === null) return <li key={index} className="gv2-cdoc-item"><span className="gv2-cdoc-time">{String(index + 1).padStart(2, '0')}</span><div>{renderCreation(String(item))}</div></li>;
        const timeKey = CDOC_TIME.find(key => item[key]);
        const labelKey = CDOC_ITEM_LABEL.find(key => typeof item[key] === 'string' && item[key]);
        const fields = Object.keys(item).filter(key => key !== timeKey && key !== labelKey && !CDOC_SKIP.has(key));
        const ordered = [...fields.filter(k => !CDOC_NOTES.includes(k)), ...fields.filter(k => CDOC_NOTES.includes(k))];
        return <li key={index} className="gv2-cdoc-item">
          <span className="gv2-cdoc-time">{timeKey ? String(item[timeKey]) : String(item.numero || index + 1).padStart(2, '0')}</span>
          <div>
            {labelKey && <strong className="gv2-cdoc-item-title">{renderInline(item[labelKey], `${listKey}-${index}`)}</strong>}
            {ordered.map(key => ['texte', 'corps', 'contenu', 'texte_principal', 'reponse'].includes(key) && typeof item[key] === 'string'
              ? <div key={key} className="gv2-cdoc-main">{renderCreation(item[key])}</div>
              : <CdocField key={key} name={key} value={item[key]} keyPrefix={`${listKey}-${index}-${key}`} />)}
          </div>
        </li>;
      })}</ol>
    </section>)}
    {notesLast.map(key => <CdocField key={key} name={key} value={content[key]} keyPrefix={key} />)}
  </div>;
}

function CreationSources({ sources, result }) {
  const eval_ = result?.auto_eval || {};
  const scores = Object.entries(eval_).filter(([, v]) => typeof v === 'number').slice(0, 5);
  const retires = Array.isArray(result?.unverified_figures) ? result.unverified_figures : [];
  if (!sources && !scores.length && !retires.length) return null;
  return <div className="gv2-cdoc-sources">
    {retires.length > 0 && <p className="gv2-cdoc-verification" role="note">
      <strong>{retires.length} chiffre{retires.length > 1 ? 's' : ''} non vérifiable{retires.length > 1 ? 's' : ''} retiré{retires.length > 1 ? 's' : ''}.</strong>
      {' '}Gabriel n’invente aucun chiffre : ajoutez vos vrais résultats (prix, délais, pourcentages) dans votre demande pour qu’ils soient utilisés.
    </p>}
    {sources && <div className="gv2-cdoc-source-list">
      <span className={sources.use_psycho ? 'is-on' : ''}>{sources.use_psycho ? 'Analyse du Psychologue utilisée' : 'Sans analyse du Psychologue'}</span>
      <span className={sources.use_strategy ? 'is-on' : ''}>{sources.use_strategy ? 'Stratégie d’Ariane utilisée' : 'Sans stratégie d’Ariane'}</span>
    </div>}
    {scores.length > 0 && <div className="gv2-cdoc-scores" aria-label="Relecture de Gabriel">
      {scores.map(([key, value]) => <span key={key}><em>{cdocLabel(key)}</em><strong>{Math.round(value)}</strong></span>)}
    </div>}
  </div>;
}

function CreationMessage({ messageId, result, sources, label = 'Création terminée', contentType, onCopy, onSave, onDownload, onPrepareRefinement, onRegenerate, saving, saved, copied }) {
  const content = textOf(result);
  const count = wordCount(content);
  return <article className="gv2-creator-message gv2-creator-message--result">
    <div className="gv2-creator-message-meta"><img src={agents.createur.portrait} alt="" /><strong>Le Créateur</strong><span>{label}</span></div>
    <div className="gv2-creator-result-card">
      <div className="gv2-creator-result-head"><div><span>{label}</span><strong>{formatLabels[contentType] || 'Contenu'}</strong></div></div>
      <div className="gv2-creator-result-meta"><span>{count ? `${count} mots` : 'Brouillon'}</span><span>Prêt à relire et affiner</span></div>
      {isStructuredCreation(result?.content)
        ? <CreationDocument content={result.content} />
        : <div className="gv2-creator-result-text">{content ? renderCreation(content) : <p>Le contenu généré est vide. Relancez une création.</p>}</div>}
      <CreationSources sources={sources} result={result} />
      <div className="gv2-creator-result-actions" role="toolbar" aria-label="Actions sur le contenu">
        <button type="button" onClick={() => onPrepareRefinement('Raccourcis le contenu sans perdre l’idée principale ni le ton.') }><Icon name="scissors" size={15} />Raccourcir</button>
        <button type="button" onClick={() => onPrepareRefinement('Propose une variante A/B avec un angle nettement différent, tout en gardant le même objectif.') }><Icon name="split" size={15} />Variante A/B</button>
        <button type="button" onClick={onRegenerate}><Icon name="refresh" size={15} />Régénérer</button>
        <button type="button" onClick={() => onCopy(content, messageId)}><Icon name={copied ? 'check' : 'copy'} size={15} />{copied ? 'Copié' : 'Copier'}</button>
        <button type="button" onClick={() => onDownload(content)}><Icon name="download" size={15} />Télécharger</button>
        <button type="button" onClick={onSave} disabled={saving || saved}><Icon name={saved ? 'check' : 'file'} size={15} />{saving ? 'Sauvegarde…' : saved ? 'Sauvegardé' : 'Sauvegarder'}</button>
      </div>
      <div className="gv2-creator-result-note"><Icon name="sparkle" size={14} /><span>{result?.writing_brief ? 'Le format, la tonalité et le contexte relié ont été pris en compte.' : 'Affinez cette version avec une instruction courte dans le champ ci-dessous.'}</span></div>
    </div>
  </article>;
}

function Message({ message, contentType, onCopy, onSave, onDownload, onPrepareRefinement, onRegenerate, onRetry, saving, saved, copied }) {
  if (message.kind === 'intro') return <article className="gv2-creator-message gv2-creator-message--intro"><div className="gv2-creator-message-meta"><img src={agents.createur.portrait} alt="" /><strong>Le Créateur</strong></div><p>{message.content}</p></article>;
  if (message.kind === 'status') return <article className="gv2-creator-message gv2-creator-message--status"><span className="gv2-creator-pulse" /><p>{message.content}</p></article>;
  if (message.kind === 'result') return <CreationMessage messageId={message.id} result={message.result} sources={message.sources} label={message.label} contentType={contentType} onCopy={onCopy} onSave={onSave} onDownload={onDownload} onPrepareRefinement={onPrepareRefinement} onRegenerate={onRegenerate} saving={saving} saved={saved} copied={copied} />;
  if (message.kind === 'error') return <article className="gv2-creator-message gv2-creator-message--error"><span>!</span><div><p>{message.content}</p>{message.retryRequest && onRetry && <button type="button" className="gv2-creator-retry" onClick={() => onRetry(message.retryRequest, message.id)}><Icon name="refresh" size={14} />Relancer la création</button>}</div></article>;
  return <article className="gv2-creator-message gv2-creator-message--user"><div className="gv2-creator-message-meta"><span className="gv2-creator-user-mark">Vous</span></div><p>{message.content}</p></article>;
}

function pause(duration) {
  return new Promise(resolve => window.setTimeout(resolve, duration));
}

// Une génération complète dure 4 à 6 minutes (mesuré le 24/09/2026) : on attend
// jusqu'à 15 minutes, et la création en cours survit à un rechargement de page.
const PENDING_CREATION_KEY = 'gabriel_pending_creation';
const CREATION_MAX_WAIT_MS = 15 * 60 * 1000;
const CREATION_POLL_MS = 2000;
const MAX_NETWORK_FAILURES = 8;

function readPendingCreation() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(PENDING_CREATION_KEY) || 'null');
    if (stored?.id && Date.now() - Number(stored.t0 || 0) < CREATION_MAX_WAIT_MS) return stored;
  } catch (_) { /* stockage indisponible : on repart d'un écran vide */ }
  return null;
}
function savePendingCreation(value) {
  try { window.localStorage.setItem(PENDING_CREATION_KEY, JSON.stringify(value)); } catch (_) { /* facultatif */ }
}
function clearPendingCreation() {
  try { window.localStorage.removeItem(PENDING_CREATION_KEY); } catch (_) { /* facultatif */ }
}

export function CreatorConversation({ workspace, lastAnalysis, creatorHandoff, settings, refinementRequest, onHasOutputChange, onWorkspaceChange, onSettingsChange, contextCollapsed, onShowContext }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [result, setResult] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [suggestionsVisible, setSuggestionsVisible] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copiedResultId, setCopiedResultId] = useState('');
  const [isListening, setIsListening] = useState(false);
  const inputRef = useRef(null);
  const scrollRef = useRef(null);
  // Sources de contexte : le Créateur marche seul, avec l'analyse du
  // Psychologue (par défaut dès qu'elle existe), et/ou avec la stratégie
  // d'Ariane (seulement si l'utilisateur l'active).
  const [latestAnalysis, setLatestAnalysis] = useState(null);
  const sourcesRef = useRef(null);
  const [usePsycho, setUsePsycho] = useState(true);
  const [useStrategy, setUseStrategy] = useState(false);
  const analysis = workspace?.analysis_id
    ? { id: workspace.analysis_id, title: 'Analyse de cet espace' }
    : lastAnalysis?.id ? lastAnalysis : latestAnalysis;
  const strategyAvailable = Boolean(workspace?.strategy_id);
  const strategyActivatedByAriane = Boolean(
    creatorHandoff?.source === 'stratege'
    && creatorHandoff.folder_id === workspace?.folder_id
    && creatorHandoff.strategy_id === workspace?.strategy_id,
  );

  useEffect(() => {
    // Seul le bouton explicite du rapport d'Ariane active automatiquement sa
    // stratégie. Une ouverture directe de Thomas conserve le mode autonome.
    setUseStrategy(strategyActivatedByAriane);
  }, [strategyActivatedByAriane, workspace?.folder_id, workspace?.strategy_id]);

  useEffect(() => {
    if (workspace?.analysis_id || lastAnalysis?.id) return undefined;
    let live = true;
    const requete = fetchV2('/history');
    if (!requete || typeof requete.then !== 'function') return undefined;
    requete.then(async response => {
      if (!response || !response.ok || isLoginResponse(response)) return;
      const payload = JSON.parse(await response.text());
      const liste = Array.isArray(payload) ? payload : Array.isArray(payload?.history) ? payload.history : [];
      const derniere = liste.find(item => item && item.analysis_id);
      if (live && derniere) setLatestAnalysis({ id: derniere.analysis_id, title: derniere.title || derniere.source || 'Dernière analyse' });
    }).catch(() => { /* sans historique, le Créateur fonctionne seul */ });
    return () => { live = false; };
  }, [workspace?.analysis_id, lastAnalysis?.id]);

  function contextSources() {
    const withPsycho = usePsycho && Boolean(analysis?.id);
    const withStrategy = useStrategy && strategyAvailable;
    return {
      use_psycho: withPsycho,
      use_strategy: withStrategy,
      analysis_id: withPsycho && !analysis.cross ? analysis.id : undefined,
      cross_analysis_id: withPsycho && analysis.cross ? analysis.id : undefined,
      strategy_id: withStrategy ? workspace.strategy_id : undefined,
    };
  }

  useEffect(() => {
    const viewport = scrollRef.current;
    if (viewport) viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' });
  }, [messages, isGenerating]);

  useEffect(() => {
    onHasOutputChange(Boolean(result));
  }, [result, onHasOutputChange]);

  useEffect(() => {
    let live = true;
    setMessages([]);
    setResult(null);
    setInput('');
    setSuggestionsVisible(true);
    setSaved(false);
    if (!workspace?.creator_output_id) return () => { live = false; };
    fetchV2(`/api/v2/jobs/${encodeURIComponent(workspace.creator_output_id)}`).then(async response => {
      if (isLoginResponse(response)) { window.location.assign('/login'); return null; }
      const payload = await readApiPayload(response, 'La création enregistrée');
      return response.ok ? payload : null;
    }).then(payload => {
      if (!live || payload?.status !== 'done' || !payload.data || !textOf(payload.data)) return;
      setResult(payload.data);
      setSuggestionsVisible(false);
      setMessages([makeMessage('assistant', 'result', { result: payload.data, label: 'Création enregistrée' })]);
    }).catch(() => {});
    return () => { live = false; };
  }, [workspace?.folder_id, workspace?.creator_output_id]);

  useEffect(() => {
    if (!refinementRequest?.id || !refinementRequest.text || !result) return;
    setInput(refinementRequest.text);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [refinementRequest, result]);

  useLayoutEffect(() => {
    const textarea = inputRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 210)}px`;
    textarea.style.overflowY = textarea.scrollHeight > 210 ? 'auto' : 'hidden';
  }, [input]);

  function replaceMessage(id, next) {
    setMessages(current => current.map(message => message.id === id ? next : message));
  }

  // Une création lancée avant un rechargement de page reprend là où elle en était.
  const resumedRef = useRef(false);
  useEffect(() => {
    if (resumedRef.current) return;
    const pending = readPendingCreation();
    if (!pending) return;
    resumedRef.current = true;
    const status = makeMessage('assistant', 'status', { content: 'Le Créateur retrouve votre création en cours…' });
    setMessages(current => [...current, makeMessage('user', 'request', { content: pending.request }), status]);
    setIsGenerating(true);
    sourcesRef.current = pending.sources || sourcesRef.current;
    pollGeneration(pending.id, status.id, pending.request, pending.t0)
      .catch(error => appendError(error.message || 'Une erreur est survenue. Réessayez dans un instant.', pending.request))
      .finally(() => setIsGenerating(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function appendError(content, retryRequest) {
    // Le message d'attente n'a plus lieu d'être : l'erreur prend sa place.
    setMessages(current => [...current.filter(message => message.kind !== 'status'), makeMessage('assistant', 'error', { content, retryRequest })]);
  }

  async function pollGeneration(jobId, statusMessageId, originalRequest, startedAt = Date.now()) {
    let networkFailures = 0;
    while (Date.now() - startedAt < CREATION_MAX_WAIT_MS) {
      await pause(CREATION_POLL_MS);
      let response;
      let payload;
      try {
        response = await fetchV2(`/api/v2/jobs/${encodeURIComponent(jobId)}`);
        if (isLoginResponse(response)) { window.location.assign('/login'); return; }
        payload = await readApiPayload(response, 'Le suivi de la création');
        networkFailures = 0;
      } catch (error) {
        // Serveur qui redémarre, réseau qui saute : on réessaie avant d'abandonner.
        networkFailures += 1;
        if (networkFailures >= MAX_NETWORK_FAILURES) { clearPendingCreation(); throw new Error('La connexion au serveur est perdue. Relancez la création.'); }
        continue;
      }
      if (!response.ok || !payload) { clearPendingCreation(); throw new Error(payload?.error || 'Le suivi de la création est indisponible.'); }
      if (payload.status === 'done') {
        clearPendingCreation();
        const nextResult = payload.data || {};
        if (!textOf(nextResult)) throw new Error('La création ne contient aucun texte exploitable.');
        setResult(nextResult);
        setSaved(false);
        setSuggestionsVisible(false);
        replaceMessage(statusMessageId, makeMessage('assistant', 'result', { result: nextResult, label: 'Création terminée', request: originalRequest, sources: sourcesRef.current }));
        await onWorkspaceChange?.();
        return;
      }
      if (['error', 'interrupted', 'not_found'].includes(payload.status)) {
        clearPendingCreation();
        throw new Error(payload.error || 'La création a été interrompue.');
      }
      replaceMessage(statusMessageId, { id: statusMessageId, role: 'assistant', kind: 'status', content: payload.step || 'Le Créateur prépare votre contenu…' });
    }
    // Le travail continue côté serveur : on garde de quoi le retrouver au prochain affichage.
    throw new Error('La création prend plus de temps que prévu et continue en arrière-plan. Rouvrez le Créateur dans quelques minutes pour la retrouver.');
  }

  async function create(request) {
    const status = makeMessage('assistant', 'status', { content: 'Le Créateur relie votre demande au contexte du workspace…' });
    setMessages(current => [...current, status]);
    const payload = {
      content_type: settings.contentType,
      channel: settings.channel,
      tone: settings.tone,
      emotion: settings.emotion,
      creativity: settings.creativity,
      objective: settings.objective,
      generate_variant: settings.generateVariant,
      user_request: request,
      folder_id: workspace?.folder_id || undefined,
      ...contextSources(),
    };
    sourcesRef.current = { use_psycho: payload.use_psycho, use_strategy: payload.use_strategy };
    const response = await fetchV2('/api/v2/agents/createur/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (isLoginResponse(response)) { window.location.assign('/login'); return; }
    const data = await readApiPayload(response, 'Le Créateur');
    if (!response.ok || data?.error) throw new Error(data?.error || 'La création n’a pas pu démarrer.');
    if (data.job_id) {
      const startedAt = Date.now();
      savePendingCreation({ id: data.job_id, request, t0: startedAt, sources: sourcesRef.current });
      await pollGeneration(data.job_id, status.id, request, startedAt);
    }
    else {
      const nextResult = data.data || data;
      if (!textOf(nextResult)) throw new Error('La création ne contient aucun texte exploitable.');
      setResult(nextResult);
      setSuggestionsVisible(false);
      replaceMessage(status.id, makeMessage('assistant', 'result', { result: nextResult, label: 'Création terminée', request, sources: sourcesRef.current }));
      await onWorkspaceChange?.();
    }
  }

  async function refine(request) {
    const status = makeMessage('assistant', 'status', { content: 'Le Créateur applique votre modification sans repartir de zéro…' });
    setMessages(current => [...current, status]);
    const response = await fetchV2('/api/v2/agents/createur/refine', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      original_content: result?.content || result || {}, instruction: request, content_type: settings.contentType, tone: settings.tone,
      folder_id: workspace?.folder_id || undefined,
      ...contextSources(),
    }) });
    if (isLoginResponse(response)) { window.location.assign('/login'); return; }
    const data = await readApiPayload(response, 'La modification du contenu');
    if (!response.ok || data?.error) throw new Error(data?.error || 'La modification a échoué.');
    const nextResult = data.data || data;
    if (!textOf(nextResult)) throw new Error('La modification ne contient aucun texte exploitable.');
    // Le prochain raffinement doit repartir de cette version, et non du
    // premier brouillon. Le texte lisible reste exposé au niveau racine.
    const mergedResult = { ...(result || {}), ...nextResult, content: nextResult };
    setResult(mergedResult);
    setSaved(false);
    replaceMessage(status.id, makeMessage('assistant', 'result', { result: mergedResult, label: 'Modification appliquée', sources: sourcesRef.current }));
  }

  async function submit() {
    const request = input.trim();
    if (!request || isGenerating) return;
    setMessages(current => [...current, makeMessage('user', 'request', { content: request })]);
    setInput('');
    setIsGenerating(true);
    try {
      if (result) await refine(request); else await create(request);
    } catch (error) {
      appendError(error.message || 'Une erreur est survenue. Réessayez dans un instant.', result ? undefined : request);
    } finally {
      setIsGenerating(false);
    }
  }

  // Relance la même demande après une interruption, sans la retaper.
  async function retryCreation(request, errorMessageId) {
    if (!request || isGenerating) return;
    setMessages(current => current.filter(message => message.id !== errorMessageId));
    setIsGenerating(true);
    try {
      await create(request);
    } catch (error) {
      appendError(error.message || 'Une erreur est survenue. Réessayez dans un instant.', request);
    } finally {
      setIsGenerating(false);
    }
  }

  async function copy(content, messageId) {
    if (!content) return;
    try {
      await navigator.clipboard?.writeText(content);
      setCopiedResultId(messageId);
      window.setTimeout(() => setCopiedResultId(current => current === messageId ? '' : current), 1800);
    } catch (_) { /* La copie peut être bloquée par le navigateur. */ }
  }

  function download(content) {
    if (!content) return;
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `gabriel-${settings.contentType || 'creation'}.txt`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
  }

  function prepareRefinement(instruction) {
    setInput(instruction);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }

  function startDictation() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || isListening || isGenerating) {
      inputRef.current?.focus();
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'fr-FR';
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognition.onresult = event => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim();
      if (transcript) setInput(current => `${current}${current ? ' ' : ''}${transcript}`.slice(0, 5000));
    };
    recognition.start();
  }

  async function save() {
    if (!result || saving) return;
    setSaving(true);
    try {
      const response = await fetchV2('/api/v2/agents/createur/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        content_type: settings.contentType, content: result?.content || result, full_text: textOf(result), analysis_id: workspace?.analysis_id || '', tone: settings.tone, channel: settings.channel,
      }) });
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const payload = await readApiPayload(response, 'La sauvegarde');
      if (!response.ok || !payload?.success) throw new Error(payload?.error || 'La sauvegarde a échoué.');
      setSaved(true);
    } catch (error) {
      appendError(error.message || 'La sauvegarde a échoué.');
    } finally {
      setSaving(false);
    }
  }

  function startFresh() {
    setResult(null);
    setSaved(false);
    setSuggestionsVisible(true);
    setInput('');
    setMessages(current => [...current, makeMessage('assistant', 'intro', { content: 'Très bien. Décrivez la nouvelle création que vous souhaitez préparer.' })]);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }

  return <section className={`gv2-creator-conversation${result ? ' has-result' : ''}`} aria-label="Conversation avec le Créateur">
    <header className="gv2-creator-header"><img src={agents.createur.portrait} alt="" /><div><h1>Le Créateur</h1><p>Rédaction et formats de conversion</p></div><div className="gv2-creator-header-actions"><button type="button" className={!contextCollapsed ? 'is-active' : ''} onClick={onShowContext}><Icon name="settings" size={14} />Atelier</button>{result && <button type="button" onClick={startFresh}><Icon name="plus" size={14} />Nouvelle création</button>}</div></header>
    <div className="gv2-creator-stream" ref={scrollRef}>
      <div className="gv2-creator-thread">
        {messages.map(message => <Message key={message.id} message={message} contentType={settings.contentType} onCopy={copy} onSave={save} onDownload={download} onPrepareRefinement={prepareRefinement} onRetry={retryCreation} onRegenerate={() => prepareRefinement('Génère une nouvelle version avec un angle différent, en conservant l’objectif initial.')} saving={saving} saved={saved} copied={copiedResultId === message.id} />)}
        {!result && suggestionsVisible && <section className="gv2-creator-suggestions"><div><span>Points de départ</span><button type="button" onClick={() => setSuggestionsVisible(false)}>Masquer</button></div><p>Choisissez un format ou décrivez directement le résultat attendu.</p><div className="gv2-creator-suggestion-list">{prompts.map(prompt => <button key={prompt.label} type="button" onClick={() => { setInput(prompt.text); inputRef.current?.focus(); }}><strong>{prompt.label}</strong><Icon name="chevronRight" size={15} /></button>)}</div></section>}
      </div>
    </div>
    <footer className="gv2-creator-composer-dock">
      <div className="gv2-creator-composer-toolbar">
        <div className="gv2-creator-format-tabs" role="tablist" aria-label="Format de création">
          {creatorFormatTabs.map(format => <button key={format.value} type="button" role="tab" aria-selected={settings.contentType === format.value} className={settings.contentType === format.value ? 'is-active' : ''} onClick={() => onSettingsChange?.({ contentType: format.value })}>{format.label}</button>)}
        </div>
        <div className="gv2-creator-toolbar-actions">{result && <button type="button" className="gv2-creator-new-trigger" onClick={startFresh}><Icon name="plus" size={15} />Nouvelle création</button>}<button type="button" className="gv2-creator-atelier-trigger" onClick={onShowContext}><Icon name="settings" size={16} />Atelier</button></div>
      </div>
      <div className="gv2-creator-sources" role="group" aria-label="Contexte utilisé par le Créateur">
        <button type="button" className={`gv2-creator-source${usePsycho && analysis ? ' is-on' : ''}`} aria-pressed={Boolean(usePsycho && analysis)}
          disabled={!analysis} onClick={() => setUsePsycho(value => !value)}
          title={analysis ? `Analyse utilisée : ${analysis.title}` : 'Aucune analyse du Psychologue pour le moment'}>
          <img src={agents.psychologue.portrait} alt="" />
          <span><strong>Analyse du Psychologue</strong><small>{analysis ? analysis.title : 'Aucune analyse disponible'}</small></span>
          <i aria-hidden="true" />
        </button>
        <button type="button" className={`gv2-creator-source${useStrategy && strategyAvailable ? ' is-on' : ''}`} aria-pressed={Boolean(useStrategy && strategyAvailable)}
          disabled={!strategyAvailable} onClick={() => setUseStrategy(value => !value)}
          title={strategyAvailable ? 'Appuyer la création sur la stratégie d’Ariane' : 'Aucune stratégie d’Ariane dans cet espace'}>
          <img src={agents.stratege.portrait} alt="" />
          <span><strong>Stratégie d’Ariane</strong><small>{strategyAvailable ? (useStrategy ? (strategyActivatedByAriane ? 'Activée depuis Ariane' : 'Utilisée') : 'Optionnelle') : 'Aucune stratégie'}</small></span>
          <i aria-hidden="true" />
        </button>
      </div>
      <form className={`gv2-creator-composer${result ? ' is-refining' : ''}`} onSubmit={event => { event.preventDefault(); submit(); }}>
        <label className="gv2-visually-hidden" htmlFor="gv2-creator-request">{result ? 'Affiner cette version' : 'Nouvelle création'}</label>
        <textarea id="gv2-creator-request" ref={inputRef} value={input} rows="2" maxLength="5000" disabled={isGenerating} onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); } }} placeholder={result ? 'Décrivez la modification à appliquer…' : 'Décrivez le contenu que vous souhaitez créer…'} aria-label={result ? 'Demande de modification' : 'Demande de création'} />
        <div className="gv2-creator-composer-actions">
          <div><button type="button" className="gv2-creator-composer-icon" onClick={onShowContext} aria-label="Ajouter du contexte" title="Ajouter du contexte"><Icon name="plus" size={20} /></button><button type="button" className="gv2-creator-model-trigger" onClick={onShowContext}>Créateur 1.0<Icon name="chevronDown" size={14} /></button><span>{input.length} / 5000</span></div>
          <div><button type="button" className={`gv2-creator-composer-icon${isListening ? ' is-listening' : ''}`} onClick={startDictation} aria-label="Dicter la demande" title="Dicter la demande"><Icon name="mic" size={19} /></button><button type="submit" className="gv2-creator-submit" disabled={isGenerating || !input.trim()} aria-label={isGenerating ? 'Création en cours' : result ? 'Appliquer la modification' : 'Créer le contenu'}>{isGenerating ? <span className="gv2-creator-submit-spinner" /> : <Icon name="send" size={21} />}</button></div>
        </div>
      </form>
    </footer>
  </section>;
}
