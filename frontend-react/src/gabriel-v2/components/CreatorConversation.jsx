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
  script: 'Script', youtube: 'Script YouTube', tiktok: 'TikTok / Reels', linkedin: 'Post LinkedIn', email: 'Séquence email', sales_page: 'Page de vente',
};

function makeMessage(role, kind, payload = {}) {
  return { id: `${kind}-${Date.now()}-${Math.random().toString(16).slice(2)}`, role, kind, ...payload };
}

function introMessage() {
  return makeMessage('assistant', 'intro', {
    content: 'Décrivez le contenu que vous voulez créer. Je m’appuierai sur votre audience, votre stratégie et les paramètres visibles à droite.',
  });
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
function renderInline(value, keyPrefix) {
  const chunks = String(value || '').split(/(\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+?`|\*[^*\n]+?\*|_[^_\n]+?_)/g);
  return chunks.map((chunk, index) => {
    const key = `${keyPrefix}-${index}`;
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
    return <p key={index}>{renderInline(lines.join(' '), `paragraph-${index}`)}</p>;
  });
}

function CreationMessage({ messageId, result, label = 'Création terminée', contentType, onCopy, onSave, onRegenerate, saving, saved, copied }) {
  const content = textOf(result);
  const count = wordCount(content);
  return <article className="gv2-creator-message gv2-creator-message--result">
    <div className="gv2-creator-message-meta"><img src={agents.createur.portrait} alt="" /><strong>Le Créateur</strong><span>{label}</span></div>
    <div className="gv2-creator-result-card">
      <div className="gv2-creator-result-head"><div><span>Livrable proposé</span><strong>{formatLabels[contentType] || 'Contenu'}</strong></div><div className="gv2-creator-result-actions"><button type="button" onClick={() => onCopy(content, messageId)}><Icon name={copied ? 'check' : 'copy'} size={15} />{copied ? 'Copié' : 'Copier'}</button><button type="button" onClick={onRegenerate}><Icon name="refresh" size={15} />Reprendre</button><button type="button" onClick={onSave} disabled={saving || saved}><Icon name={saved ? 'check' : 'file'} size={15} />{saving ? 'Sauvegarde…' : saved ? 'Sauvegardé' : 'Sauvegarder'}</button></div></div>
      <div className="gv2-creator-result-meta"><span>{count ? `${count} mots` : 'Brouillon'}</span><span>Prêt à relire et affiner</span></div>
      <div className="gv2-creator-result-text">{content ? renderCreation(content) : <p>Le contenu généré est vide. Relancez une création.</p>}</div>
      <div className="gv2-creator-result-note"><Icon name="sparkle" size={14} /><span>{result?.writing_brief ? 'Le format, la tonalité et le contexte relié ont été pris en compte.' : 'Affinez cette version avec une instruction courte dans le champ ci-dessous.'}</span></div>
    </div>
  </article>;
}

function Message({ message, contentType, onCopy, onSave, onRegenerate, saving, saved, copied }) {
  if (message.kind === 'intro') return <article className="gv2-creator-message gv2-creator-message--intro"><div className="gv2-creator-message-meta"><img src={agents.createur.portrait} alt="" /><strong>Le Créateur</strong></div><p>{message.content}</p></article>;
  if (message.kind === 'status') return <article className="gv2-creator-message gv2-creator-message--status"><span className="gv2-creator-pulse" /><p>{message.content}</p></article>;
  if (message.kind === 'result') return <CreationMessage messageId={message.id} result={message.result} label={message.label} contentType={contentType} onCopy={onCopy} onSave={onSave} onRegenerate={onRegenerate} saving={saving} saved={saved} copied={copied} />;
  if (message.kind === 'error') return <article className="gv2-creator-message gv2-creator-message--error"><span>!</span><p>{message.content}</p></article>;
  return <article className="gv2-creator-message gv2-creator-message--user"><div className="gv2-creator-message-meta"><span className="gv2-creator-user-mark">Vous</span></div><p>{message.content}</p></article>;
}

function pause(duration) {
  return new Promise(resolve => window.setTimeout(resolve, duration));
}

export function CreatorConversation({ workspace, settings, refinementRequest, onHasOutputChange, onWorkspaceChange, contextCollapsed, onShowContext }) {
  const [messages, setMessages] = useState(() => [introMessage()]);
  const [input, setInput] = useState('');
  const [result, setResult] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [suggestionsVisible, setSuggestionsVisible] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [copiedResultId, setCopiedResultId] = useState('');
  const inputRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    const viewport = scrollRef.current;
    if (viewport) viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' });
  }, [messages, isGenerating]);

  useEffect(() => {
    onHasOutputChange(Boolean(result));
  }, [result, onHasOutputChange]);

  useEffect(() => {
    let live = true;
    setMessages([introMessage()]);
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
      setMessages([introMessage(), makeMessage('assistant', 'result', { result: payload.data, label: 'Création enregistrée' })]);
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

  function appendError(content) {
    setMessages(current => [...current, makeMessage('assistant', 'error', { content })]);
  }

  async function pollGeneration(jobId, statusMessageId, originalRequest) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await pause(2000);
      const response = await fetchV2(`/api/v2/jobs/${encodeURIComponent(jobId)}`);
      if (isLoginResponse(response)) { window.location.assign('/login'); return; }
      const payload = await readApiPayload(response, 'Le suivi de la création');
      if (!response.ok || !payload) throw new Error(payload?.error || 'Le suivi de la création est indisponible.');
      if (payload.status === 'done') {
        const nextResult = payload.data || {};
        if (!textOf(nextResult)) throw new Error('La création ne contient aucun texte exploitable.');
        setResult(nextResult);
        setSaved(false);
        setSuggestionsVisible(false);
        replaceMessage(statusMessageId, makeMessage('assistant', 'result', { result: nextResult, label: 'Création terminée', request: originalRequest }));
        await onWorkspaceChange?.();
        return;
      }
      if (['error', 'interrupted', 'not_found'].includes(payload.status)) throw new Error(payload.error || 'La création a été interrompue.');
      replaceMessage(statusMessageId, { id: statusMessageId, role: 'assistant', kind: 'status', content: payload.step || 'Le Créateur prépare votre contenu…' });
    }
    throw new Error('Le temps de création est dépassé. Réessayez dans un instant.');
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
      analysis_id: workspace?.analysis_id || undefined,
      strategy_id: workspace?.strategy_id || undefined,
    };
    const response = await fetchV2('/api/v2/agents/createur/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (isLoginResponse(response)) { window.location.assign('/login'); return; }
    const data = await readApiPayload(response, 'Le Créateur');
    if (!response.ok || data?.error) throw new Error(data?.error || 'La création n’a pas pu démarrer.');
    if (data.job_id) await pollGeneration(data.job_id, status.id, request);
    else {
      const nextResult = data.data || data;
      if (!textOf(nextResult)) throw new Error('La création ne contient aucun texte exploitable.');
      setResult(nextResult);
      setSuggestionsVisible(false);
      replaceMessage(status.id, makeMessage('assistant', 'result', { result: nextResult, label: 'Création terminée', request }));
      await onWorkspaceChange?.();
    }
  }

  async function refine(request) {
    const status = makeMessage('assistant', 'status', { content: 'Le Créateur applique votre modification sans repartir de zéro…' });
    setMessages(current => [...current, status]);
    const response = await fetchV2('/api/v2/agents/createur/refine', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      original_content: result?.content || result || {}, instruction: request, content_type: settings.contentType, tone: settings.tone,
      analysis_id: workspace?.analysis_id || undefined,
      strategy_id: workspace?.strategy_id || undefined,
      folder_id: workspace?.folder_id || undefined,
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
    replaceMessage(status.id, makeMessage('assistant', 'result', { result: mergedResult, label: 'Modification appliquée' }));
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
      appendError(error.message || 'Une erreur est survenue. Réessayez dans un instant.');
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

  return <section className="gv2-creator-conversation" aria-label="Conversation avec le Créateur">
    <header className="gv2-creator-header"><img src={agents.createur.portrait} alt="" /><div><h1>Le Créateur</h1><p>Rédaction et formats de conversion</p></div><div className="gv2-creator-header-actions">{contextCollapsed && <button type="button" onClick={onShowContext}><Icon name="settings" size={14} />Paramètres</button>}{result && <button type="button" onClick={startFresh}><Icon name="plus" size={14} />Nouvelle création</button>}</div></header>
    <div className="gv2-creator-stream" ref={scrollRef}>
      <div className="gv2-creator-thread">
        {messages.map(message => <Message key={message.id} message={message} contentType={settings.contentType} onCopy={copy} onSave={save} onRegenerate={() => { setResult(null); setSaved(false); setInput(message.request || 'Je souhaite une nouvelle version avec un angle différent.'); window.requestAnimationFrame(() => inputRef.current?.focus()); }} saving={saving} saved={saved} copied={copiedResultId === message.id} />)}
        {!result && suggestionsVisible && <section className="gv2-creator-suggestions"><div><span>Points de départ</span><button type="button" onClick={() => setSuggestionsVisible(false)}>Masquer</button></div><p>Choisissez un format ou décrivez directement le résultat attendu.</p><div className="gv2-creator-suggestion-list">{prompts.map(prompt => <button key={prompt.label} type="button" onClick={() => { setInput(prompt.text); inputRef.current?.focus(); }}><strong>{prompt.label}</strong><Icon name="chevronRight" size={15} /></button>)}</div></section>}
        {result && !suggestionsVisible && <button type="button" className="gv2-creator-show-suggestions" onClick={() => setSuggestionsVisible(true)}>Afficher des idées de création</button>}
      </div>
    </div>
    <form className={`gv2-creator-composer${result ? ' is-refining' : ''}`} onSubmit={event => { event.preventDefault(); submit(); }}>
      <div className="gv2-creator-composer-label"><strong>{result ? 'Affiner cette version' : 'Nouvelle création'}</strong><span>{result ? 'Décrivez précisément ce que vous voulez modifier.' : 'Les paramètres de création restent accessibles dans la colonne de droite.'}</span></div>
      <textarea ref={inputRef} value={input} rows="1" maxLength="2000" disabled={isGenerating} onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); } }} placeholder={result ? 'Ex. Raccourcis le hook et rends la conclusion plus directe…' : 'Décrivez le contenu que vous souhaitez créer…'} aria-label={result ? 'Demande de modification' : 'Demande de création'} />
      <div className="gv2-creator-composer-actions"><span>{input.length} / 2000</span><button type="submit" disabled={isGenerating || !input.trim()}>{isGenerating ? 'En cours…' : result ? 'Appliquer' : 'Créer'}<Icon name="send" size={17} /></button></div>
    </form>
  </section>;
}
