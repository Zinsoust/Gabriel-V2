import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import Lenis from 'lenis';
import { gsap } from 'gsap';
import { Icon } from '../icons.jsx';
import { fetchV2, isLoginResponse, readApiPayload } from '../api-client.js';

// Les réponses de Gabriel conservent leur structure éditoriale (titres,
// emphases, listes et citations) sans jamais interpréter du HTML distant.
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

function numberedItems(value) {
  const items = [];
  const pattern = /(?:^|\s)(\d+)[.)]\s+([\s\S]*?)(?=(?:\s+\d+[.)]\s+)|$)/g;
  let match;
  while ((match = pattern.exec(String(value || '')))) items.push(match[2].trim());
  return items.length > 1 ? items : null;
}

function dashedItems(value) {
  const items = String(value || '').trim().replace(/^-\s+/, '').split(/\s+-\s+/).map(item => item.trim()).filter(Boolean);
  return items.length > 1 ? items : null;
}

function isSectionLabel(value) {
  const label = String(value || '').trim().toLowerCase();
  return label.length <= 100 && /^(?:ce que|votre situation|ma lecture|les constats|les éléments|ce qui|à éclaircir|pour avancer|prochaine étape|recommandation|en pratique|point d['’]attention|points? à|notre lecture)/.test(label);
}

function sectionKind(label) {
  const value = String(label || '').toLowerCase();
  if (/ne sais pas|éclaircir|question|manque|à préciser/.test(value)) return 'questions';
  if (/ce que je lis|ma lecture|analyse|ce qui/.test(value)) return 'insight';
  if (/situation|constat|élément|observ/.test(value)) return 'facts';
  return 'default';
}

function sectionKicker(kind) {
  return { facts: 'Les faits', insight: 'Lecture de Gabriel', questions: 'À éclaircir', default: 'Point de décision' }[kind] || 'Point de décision';
}

function renderAssistantParagraph(value, index, sectionNumber = 0) {
  const text = String(value || '').trim();
  const section = text.match(/^(.{3,100}?)\s*:\s+([\s\S]+)$/);
  if (section && isSectionLabel(section[1])) {
    const numbered = numberedItems(section[2]);
    const dashed = dashedItems(section[2]);
    const items = numbered || dashed;
    const kind = sectionKind(section[1]);
    return <section className={`gv2-message-section gv2-message-section--${kind}`} key={index}>
      <header className="gv2-message-section-header"><span className="gv2-message-section-index" aria-hidden="true">{String(sectionNumber).padStart(2, '0')}</span><div><small>{sectionKicker(kind)}</small><h3>{renderInline(section[1], `section-${index}`)}</h3></div></header>
      <div className="gv2-message-section-content">{items ? <ol className={`gv2-message-list${numbered ? ' gv2-message-list--ordered' : ''}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item, `section-${index}-${itemIndex}`)}</li>)}</ol> : <p>{renderInline(section[2], `section-copy-${index}`)}</p>}</div>
    </section>;
  }
  return <p className={index === 0 ? 'gv2-message-opening' : ''} key={index}>{renderInline(text, `paragraph-${index}`)}</p>;
}

function formatText(value, assistant = false) {
  const blocks = String(value || '').trim().split(/\n{2,}/).filter(Boolean);
  let assistantSectionNumber = 0;
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
    if (isBullets) return <ul className="gv2-message-list" key={index}>{lines.map((line, lineIndex) => <li key={lineIndex}>{renderInline(line.replace(/^(?:[-–•])\s+/, ''), `bullet-${index}-${lineIndex}`)}</li>)}</ul>;
    if (isOrdered) return <ol className="gv2-message-list gv2-message-list--ordered" key={index}>{lines.map((line, lineIndex) => <li key={lineIndex}>{renderInline(line.replace(/^\d+[.)]\s+/, ''), `ordered-${index}-${lineIndex}`)}</li>)}</ol>;
    const paragraph = lines.join(' ');
    const section = paragraph.match(/^(.{3,100}?)\s*:\s+([\s\S]+)$/);
    if (assistant && section && isSectionLabel(section[1])) assistantSectionNumber += 1;
    return assistant ? renderAssistantParagraph(paragraph, index, assistantSectionNumber) : <p key={index}>{renderInline(paragraph, `paragraph-${index}`)}</p>;
  });
}

function EventMessage({ mission, itemId }) {
  return <div className="gv2-event-card" data-gv2-message-id={itemId}>
    <div className="gv2-event-mark"><Icon name="sparkle" size={18} /></div>
    <div><span>Gabriel a défini la prochaine étape</span><strong>{mission.title}</strong>{mission.objective && <p>{mission.objective}</p>}</div>
  </div>;
}

function AssistantMessageActions({ content }) {
  const [copied, setCopied] = useState(false);

  async function copyResponse() {
    try {
      await navigator.clipboard.writeText(content);
    } catch (_) {
      const field = document.createElement('textarea');
      field.value = content;
      field.style.position = 'fixed';
      field.style.opacity = '0';
      document.body.append(field);
      field.select();
      document.execCommand('copy');
      field.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1300);
  }

  function downloadResponse() {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `reponse-gabriel-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return <div className="gv2-message-actions" aria-label="Actions de la réponse">
    <button type="button" onClick={copyResponse}><Icon name="copy" size={18} /><span>{copied ? 'Copié' : 'Copier'}</span></button>
    <button type="button" onClick={downloadResponse}><Icon name="download" size={18} /><span>Télécharger</span></button>
  </div>;
}

const landingPrompts = [
  { label: 'Analyser une audience', text: 'Je souhaite analyser mon audience afin de mieux comprendre ses attentes, ses motivations et ses freins.', icon: 'knowledge' },
  { label: 'Clarifier une offre', text: 'Aide-moi à clarifier mon offre, sa promesse et ce qui la différencie.', icon: 'sparkle' },
  { label: 'Préparer une stratégie', text: 'Je veux construire une stratégie claire à partir de mon contexte business.', icon: 'activity' },
  { label: 'Créer un contenu', text: 'Je veux préparer un contenu utile et aligné sur mon audience.', icon: 'briefcase' },
];

export function ConversationFeed({ items, firstName, isSubmitting, compact = false, landing = false }) {
  const bottomRef = useRef(null);
  const scrollRef = useRef(null);
  const lenisRef = useRef(null);
  const revealedItems = useRef(new Set());
  // L'accueil accompagne une page vide ; dès que l'utilisateur s'exprime,
  // le fil reprend naturellement toute sa hauteur.
  const hasStarted = items.some(item => item.role === 'user');

  useEffect(() => {
    const wrapper = scrollRef.current;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!wrapper || reducedMotion) return undefined;

    const lenis = new Lenis({
      wrapper,
      content: wrapper.firstElementChild,
      duration: 1.05,
      smoothWheel: true,
      syncTouch: false,
    });
    lenisRef.current = lenis;
    let frameId;
    const animate = time => {
      lenis.raf(time);
      frameId = window.requestAnimationFrame(animate);
    };
    frameId = window.requestAnimationFrame(animate);

    return () => {
      window.cancelAnimationFrame(frameId);
      lenis.destroy();
      lenisRef.current = null;
    };
  }, []);

  useEffect(() => {
    const target = bottomRef.current;
    if (!target) return;
    if (lenisRef.current) {
      lenisRef.current.scrollTo(target, { duration: isSubmitting ? .35 : .65 });
    } else {
      target.scrollIntoView({ block: 'end', behavior: 'smooth' });
    }
  }, [items, isSubmitting]);

  useLayoutEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !scrollRef.current) return undefined;
    const fresh = Array.from(scrollRef.current.querySelectorAll('[data-gv2-message-id]')).filter(node => {
      if (revealedItems.current.has(node.dataset.gv2MessageId)) return false;
      revealedItems.current.add(node.dataset.gv2MessageId);
      return true;
    });
    if (!fresh.length) return undefined;
    const animation = gsap.fromTo(fresh, { autoAlpha: 0, y: 10 }, {
      autoAlpha: 1,
      y: 0,
      duration: .38,
      ease: 'power2.out',
      stagger: .05,
      overwrite: 'auto',
    });
    return () => animation.kill();
  }, [items]);

  const showLanding = landing && !compact;

  return <div className={`gv2-conversation-scroll${compact ? ' is-compact' : ''}${showLanding ? ' is-landing' : ''}`} ref={scrollRef}>
    <div className={`gv2-conversation${compact ? ' is-compact' : ''}${hasStarted ? ' has-started' : ''}${showLanding ? ' is-landing' : ''}`}>
      {showLanding && <header className="gv2-conversation-landing">
        <h1>Que puis-je faire pour vous&nbsp;?</h1>
        <span>Décrivez votre besoin. Gabriel clarifie la demande et mobilise les bons experts au bon moment.</span>
      </header>}
      {!showLanding && !compact && !hasStarted && <header className="gv2-conversation-welcome">
        <h1>Bonjour {firstName},</h1>
        <p>Que souhaites-tu accomplir aujourd’hui&nbsp;?</p>
      </header>}
      {!showLanding && items.map(item => {
        if (item.role === 'event' && item.mission) return <EventMessage key={item.id} mission={item.mission} itemId={item.id} />;
        const editorial = item.role === 'assistant' && String(item.content || '').length > 460;
        return <article key={item.id} data-gv2-message-id={item.id} className={`gv2-message gv2-message--${item.role}${editorial ? ' is-editorial' : ''}`}>
          <div className="gv2-message-avatar">{item.role === 'assistant' ? 'G' : item.role === 'error' ? '!' : 'V'}</div>
          <div className="gv2-message-body"><div className="gv2-message-meta"><strong>{item.role === 'assistant' ? 'Gabriel' : item.role === 'error' ? 'Gabriel' : 'Vous'}</strong><time>{item.createdAt}</time></div>{formatText(item.content, item.role === 'assistant')}{item.role === 'assistant' && <AssistantMessageActions content={item.content} />}</div>
        </article>;
      })}
      {isSubmitting && <article className="gv2-message gv2-message--assistant gv2-message--typing"><div className="gv2-message-avatar">G</div><div className="gv2-typing"><span /><span /><span /></div></article>}
      <div ref={bottomRef} />
    </div>
  </div>;
}

export function Composer({ onSend, disabled, compact = false, landing = false }) {
  const [content, setContent] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [landingPromptsVisible, setLandingPromptsVisible] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceError, setVoiceError] = useState('');
  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);
  const speechRecognitionRef = useRef(null);
  const speechBaseRef = useRef('');
  const speechFinalRef = useRef('');
  const speechHeardRef = useRef(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioStreamRef = useRef(null);

  useEffect(() => {
    if (landing) setLandingPromptsVisible(true);
  }, [landing]);

  useEffect(() => () => {
    const recognition = speechRecognitionRef.current;
    if (recognition) {
      try { recognition.abort(); } catch (_) { /* reconnaissance déjà terminée */ }
    }
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    audioStreamRef.current?.getTracks().forEach(track => track.stop());
  }, []);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const maxHeight = compact ? 112 : landing ? 220 : 180;
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [compact, content, landing]);

  async function submit(event) {
    event.preventDefault();
    const text = content.trim() || (attachments.length ? `J’ai joint : ${attachments.map(file => file.name).join(', ')}` : '');
    if (!text || disabled) return;
    const sent = await onSend(text, attachments);
    if (sent) {
      setContent('');
      setAttachments([]);
    }
  }

  function captureFiles(event) {
    addFiles(event.target.files);
    event.target.value = '';
  }

  function addFiles(nextFiles) {
    const incoming = Array.from(nextFiles || []);
    if (!incoming.length) return;
    setAttachments(current => {
      const known = new Set(current.map(file => `${file.name}-${file.size}-${file.lastModified}`));
      return [...current, ...incoming.filter(file => {
        const key = `${file.name}-${file.size}-${file.lastModified}`;
        if (known.has(key)) return false;
        known.add(key);
        return true;
      })].slice(0, 1);
    });
  }

  function mergeDictation(base, transcript) {
    const spoken = String(transcript || '').trim();
    if (!spoken) return base;
    return `${base}${base && !/\s$/.test(base) ? ' ' : ''}${spoken}`;
  }

  function startBrowserDictation(SpeechRecognition) {
    const recognition = new SpeechRecognition();
    speechBaseRef.current = content;
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
      setContent(mergeDictation(speechBaseRef.current, spoken));
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
      window.requestAnimationFrame(() => textareaRef.current?.focus());
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
      recorder.ondataavailable = event => {
        if (event.data?.size) audioChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setIsRecording(false);
        setVoiceError('La dictée a été interrompue. Réessayez dans un instant.');
      };
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
          if (isLoginResponse(response)) {
            window.location.assign('/login');
            return;
          }
          const payload = await readApiPayload(response, 'Le service de dictée');
          if (!response.ok || !payload?.text) throw new Error(response.status === 503 ? 'La transcription serveur n’est pas disponible. Essayez depuis Chrome pour utiliser la dictée intégrée.' : (payload?.error || 'La transcription est indisponible.'));
          setContent(current => `${current}${current && !/\s$/.test(current) ? ' ' : ''}${String(payload.text).trim()}`);
          window.requestAnimationFrame(() => textareaRef.current?.focus());
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
    if (disabled) return;
    setVoiceError('');
    const activeRecognition = speechRecognitionRef.current;
    if (activeRecognition) {
      try { activeRecognition.stop(); } catch (_) { /* la reconnaissance est déjà arrêtée */ }
      return;
    }
    const activeRecorder = mediaRecorderRef.current;
    if (activeRecorder && activeRecorder.state !== 'inactive') {
      activeRecorder.stop();
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      startBrowserDictation(SpeechRecognition);
      return;
    }
    void startServerDictation();
  }

  function focusDraft(nextText) {
    setContent(current => current || nextText);
    setToolsOpen(false);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDraggingFiles(false);
    addFiles(event.dataTransfer?.files);
  }

  return <form className={`gv2-composer${compact ? ' is-compact' : ''}${landing ? ' is-landing' : ''}${toolsOpen ? ' is-tools-open' : ''}${isDraggingFiles ? ' is-dragging-files' : ''}${isRecording ? ' is-recording' : ''}`} onSubmit={submit} onDragOver={event => { event.preventDefault(); setIsDraggingFiles(true); }} onDragLeave={event => { if (event.currentTarget === event.target) setIsDraggingFiles(false); }} onDrop={handleDrop}>
    {attachments.length > 0 && <div className="gv2-attachment-row">{attachments.map(file => <span key={`${file.name}-${file.size}`}><Icon name="paperclip" size={13} />{file.name}<button type="button" onClick={() => setAttachments(current => current.filter(candidate => candidate !== file))}><Icon name="close" size={13} /></button></span>)}</div>}
    <textarea ref={textareaRef} value={content} rows="1" disabled={disabled} onChange={event => setContent(event.target.value)} onKeyDown={event => {
      if (event.key === 'Escape') setToolsOpen(false);
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(event); }
    }} placeholder={landing ? 'Décrivez ce que vous souhaitez accomplir…' : 'Écris ton message à Gabriel…'} aria-label="Message à Gabriel" />
    <div className="gv2-composer-actions">
      <div className="gv2-composer-toolbox">
        <button className="gv2-circle-button" type="button" onClick={() => setToolsOpen(current => !current)} title="Ajouter du contexte" aria-label="Ajouter du contexte" aria-expanded={toolsOpen} aria-haspopup="menu"><Icon name="plus" size={20} /></button>
        {toolsOpen && <div className="gv2-composer-tools" role="menu" aria-label="Ajouter au message">
          <button type="button" role="menuitem" onClick={() => { setToolsOpen(false); fileInputRef.current?.click(); }}><Icon name="paperclip" size={16} /><span><strong>Importer des commentaires</strong><small>CSV, Excel, JSON ou TXT</small></span></button>
          <button type="button" role="menuitem" onClick={() => focusDraft('Voici le lien à analyser : ')}><Icon name="link" size={16} /><span><strong>Coller un lien</strong><small>Page, vidéo ou ressource</small></span></button>
          <button type="button" role="menuitem" onClick={() => focusDraft('Note : ')}><Icon name="file" size={16} /><span><strong>Ajouter une note</strong><small>Conserver une idée dans le fil</small></span></button>
        </div>}
      </div>
      <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls,.json,.txt" hidden onChange={captureFiles} />
      <button className="gv2-action-chip gv2-file-chip" type="button" onClick={() => fileInputRef.current?.click()}><Icon name="paperclip" size={16} /><span>Importer des commentaires</span></button>
      <button className="gv2-action-chip" type="button" onClick={() => focusDraft('Voici le lien à analyser : ')}><Icon name="link" size={16} /><span>Coller un lien</span></button>
      <button className="gv2-action-chip gv2-note-chip" type="button" onClick={() => focusDraft('Note : ')}><Icon name="file" size={16} /><span>Enregistrer une note</span></button>
      <button className={`gv2-action-chip gv2-voice-chip${isRecording ? ' is-recording' : ''}`} type="button" onClick={toggleDictation} aria-pressed={isRecording} title={isRecording ? 'Terminer la dictée' : 'Dicter un message'}><Icon name="mic" size={16} /><span>{isRecording ? 'Terminer' : 'Dictée'}</span></button>
      <button className="gv2-send-button" type="submit" disabled={disabled || (!content.trim() && !attachments.length)} aria-label="Envoyer"><Icon name="send" size={20} /></button>
    </div>
    {isRecording && <div className="gv2-composer-voice-feedback" role="status"><p className="gv2-composer-voice-status"><i />Gabriel vous écoute : votre texte apparaît en direct.</p><div className="gv2-composer-voice-wave" aria-hidden="true">{Array.from({ length: 15 }, (_, index) => <span key={index} style={{ '--gv2-wave-delay': `${index * -0.085}s`, '--gv2-wave-height': `${34 + ((index * 29) % 57)}%` }} />)}</div></div>}
    {voiceError && <p className="gv2-composer-voice-error" role="status">{voiceError}</p>}
    {landing && landingPromptsVisible && <div className="gv2-landing-prompts" aria-label="Idées pour commencer">
      <div className="gv2-landing-prompts-head"><span>Quelques points de départ, si utile</span><button type="button" onClick={() => setLandingPromptsVisible(false)}>Masquer</button></div>
      <div>{landingPrompts.map(prompt => <button key={prompt.label} type="button" onClick={() => { setContent(prompt.text); window.requestAnimationFrame(() => textareaRef.current?.focus()); }}><Icon name={prompt.icon} size={15} /><span>{prompt.label}</span></button>)}</div>
    </div>}
  </form>;
}
