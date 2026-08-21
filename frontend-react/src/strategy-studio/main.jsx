import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { gsap } from 'gsap';
import Lenis from 'lenis';
import './studio.css';

const GROUPS = [
  { label: 'Conversation', items: [
    ['st-msgsize', 'Texte des messages', 10, 20, .5],
    ['st-inputsize', 'Texte de saisie', 10, 19, .5],
    ['st-messagegap', 'Rythme des messages', 10, 52, 1],
    ['st-chatwidth', 'Largeur de lecture', 560, 1100, 10],
  ]},
  { label: 'Box chat · position et taille', items: [
    ['st-inputwidth', 'Largeur de la box', 280, 1400, 10],
    ['st-inputheight', 'Hauteur de la box', 54, 160, 2],
    ['st-inputbottom', 'Distance depuis le bas', 0, 240, 2],
    ['st-inputoffsetx', 'Décalage horizontal', -500, 500, 5],
    ['st-inputradius', 'Arrondi de la box', 0, 999, 5],
  ]},
  { label: 'Box chat · composition', items: [
    ['st-inputpaddingx', 'Marge intérieure horizontale', 0, 80, 1],
    ['st-inputpaddingy', 'Marge intérieure verticale', 0, 40, 1],
    ['st-inputgap', 'Espacement des éléments', 0, 40, 1],
    ['st-inputborder', 'Épaisseur de bordure', 0, 20, .5],
    ['st-inputshadow', "Intensité de l’ombre", 0, 120, 2],
    ['st-iconbtnsize', 'Zone des icônes', 12, 80, 1],
    ['st-iconsize', 'Taille des icônes', 8, 48, 1],
    ['st-inputbgopacity', 'Opacité du fond', 0, 100, 1, '%'],
    ['st-inputborderopacity', 'Opacité de la bordure', 0, 100, 1, '%'],
  ]},
  { label: 'Progression', items: [
    ['st-ctxtitle', "Titre d’entretien", 8, 24, .5],
    ['st-ctxfield', 'Libellés des dimensions', 6, 16, .5],
    ['st-sidewidth', 'Largeur du panneau', 180, 420, 5],
    ['st-panelradius', 'Arrondi du panneau', 0, 32, 1],
  ]},
  { label: 'Résultat stratégique', items: [
    ['st-decision', 'Décision principale', 10, 36, .5],
    ['st-decisionlabel', 'Libellé décision', 7, 18, .5],
    ['st-secttl', 'Titres de section', 8, 24, .5],
    ['st-genbtn', 'Bouton de génération', 8, 20, .5],
    ['st-ctabtn', "Boutons d’action", 8, 18, .5],
    ['st-cardradius', 'Arrondi des cartes', 0, 32, 1],
  ]},
];

const COLORS = [
  ['ux-champagne', 'Accent champagne'],
  ['ux-textprimary', 'Texte principal'],
  ['ux-bgmain', 'Fond principal'],
  ['st-inputbg', 'Fond de la box chat'],
  ['st-inputbordercolor', 'Bordure de la box chat'],
  ['st-inputtextcolor', 'Texte de la box chat'],
  ['st-inputiconcolor', 'Icônes de la box chat'],
];

function Studio() {
  const [settings, setSettings] = useState({});
  const [defaults, setDefaults] = useState({});
  const [history, setHistory] = useState([]);
  const [version, setVersion] = useState(0);
  const [status, setStatus] = useState('Chargement…');
  const [viewport, setViewport] = useState('desktop');
  const [dirty, setDirty] = useState(false);
  const panelRef = useRef(null);
  const contentRef = useRef(null);
  const iframeRef = useRef(null);
  const readyRef = useRef(false);

  useEffect(() => {
    fetch('/api/studio/stratege/settings').then(r => r.json()).then(data => {
      if (!data.success) throw new Error(data.error || 'Chargement impossible');
      setDefaults(data.defaults); setSettings(data.draft);
      setHistory(data.history || []); setVersion(data.version || 0);
      setStatus(`Version publiée ${data.version || 0}`); readyRef.current = true;
    }).catch(error => setStatus(error.message));
  }, []);

  useEffect(() => {
    if (!panelRef.current || !contentRef.current) return;
    const lenis = new Lenis({ wrapper: panelRef.current, content: contentRef.current, smoothWheel: true });
    let frame;
    const raf = time => { lenis.raf(time); frame = requestAnimationFrame(raf); };
    frame = requestAnimationFrame(raf);
    gsap.fromTo('.studio-group', { opacity: 0, y: 14 }, {
      opacity: 1, y: 0, duration: .55, stagger: .06, ease: 'power3.out',
    });
    return () => { cancelAnimationFrame(frame); lenis.destroy(); };
  }, [defaults]);

  useEffect(() => {
    if (!readyRef.current || !Object.keys(settings).length) return;
    iframeRef.current?.contentWindow?.postMessage({
      type: 'gabriel-strategy-ux', settings,
    }, window.location.origin);
    const timer = setTimeout(async () => {
      setStatus('Sauvegarde du brouillon…');
      const response = await fetch('/api/studio/stratege/settings', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({settings}),
      });
      setStatus(response.ok ? 'Brouillon sauvegardé' : 'Échec de sauvegarde');
    }, 600);
    return () => clearTimeout(timer);
  }, [settings]);

  useEffect(() => {
    const receivePreviewChange = event => {
      if (event.origin !== window.location.origin || event.data?.type !== 'gabriel-strategy-ux-drag') return;
      setSettings(current => ({...current, ...event.data.settings}));
      setDirty(true);
    };
    window.addEventListener('message', receivePreviewChange);
    return () => window.removeEventListener('message', receivePreviewChange);
  }, []);

  const frameWidth = useMemo(() => ({desktop:'100%', tablet:'900px', mobile:'390px'})[viewport], [viewport]);
  const update = (key, value) => { setSettings(s => ({...s, [key]: value})); setDirty(true); };

  async function publish() {
    if (!window.confirm('Publier ces réglages sur la page Stratège pour tous les utilisateurs ?')) return;
    setStatus('Publication…');
    const response = await fetch('/api/studio/stratege/publish', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({settings}),
    });
    const data = await response.json();
    if (!response.ok) { setStatus(data.error || 'Publication impossible'); return; }
    setVersion(data.version); setDirty(false); setStatus(`Version ${data.version} publiée`);
    gsap.fromTo('.publish-button', {scale:.96}, {scale:1, duration:.45, ease:'back.out(2)'});
  }

  function restore(entry) {
    if (!entry?.settings) return;
    setSettings(entry.settings); setDirty(true); setStatus(`Version ${entry.version} restaurée en brouillon`);
  }

  async function copySettings() {
    await navigator.clipboard.writeText(JSON.stringify(settings, null, 2));
    setStatus('Réglages copiés');
  }

  return <main className="strategy-studio-shell">
    <header className="studio-topbar">
      <div><span className="studio-eyebrow">GABRIEL · OUTIL INTERNE</span><h1>Studio UX du Stratège</h1></div>
      <div className="studio-status"><span className={dirty ? 'dirty' : ''}/>{status}</div>
      <a href="/stratege" className="studio-exit">Retour au Stratège</a>
    </header>

    <section className="studio-workspace">
      <aside className="studio-controls" ref={panelRef} data-lenis-prevent>
        <div className="studio-controls-content" ref={contentRef}>
          <p className="studio-intro">Ajustez la véritable interface en direct. Le brouillon est sauvegardé automatiquement ; seule l’action Publier modifie l’expérience des utilisateurs.</p>
          {GROUPS.map(group => <section className="studio-group" key={group.label}>
            <h2>{group.label}</h2>
            {group.items.map(([key,label,min,max,step,unit='px']) => <label className="studio-control" key={key}>
              <span><b>{label}</b><output>{settings[key] ?? '—'}{unit}</output></span>
              <input type="range" min={min} max={max} step={step} value={settings[key] ?? min}
                onChange={event => update(key, Number(event.target.value))}/>
            </label>)}
          </section>)}
          <section className="studio-group"><h2>Couleurs</h2>
            {COLORS.map(([key,label]) => <label className="studio-color" key={key}>
              <span>{label}</span><input type="color" value={settings[key] || '#000000'} onChange={event => update(key,event.target.value)}/>
            </label>)}
          </section>
          <section className="studio-group"><h2>Historique</h2>
            {!history.length && <p className="studio-empty">Aucune version antérieure.</p>}
            {history.slice().reverse().map(entry => <button className="history-item" key={entry.version} onClick={() => restore(entry)}>
              <span>Version {entry.version}</span><small>Restaurer en brouillon</small>
            </button>)}
          </section>
        </div>
      </aside>

      <section className="studio-preview">
        <div className="preview-toolbar">
          <div className="viewport-switcher">{['desktop','tablet','mobile'].map(mode =>
            <button key={mode} className={viewport===mode?'active':''} onClick={() => setViewport(mode)}>{mode}</button>
          )}</div>
          <span>Version publiée {version}</span>
        </div>
        <div className="preview-stage">
          <iframe ref={iframeRef} title="Aperçu réel du Stratège" src="/studio/stratege/preview"
            style={{width:frameWidth}} onLoad={() => iframeRef.current?.contentWindow?.postMessage({type:'gabriel-strategy-ux',settings},window.location.origin)}/>
        </div>
      </section>
    </section>

    <footer className="studio-actions">
      <button onClick={() => {setSettings(defaults);setDirty(true);}}>Réinitialiser le brouillon</button>
      <button onClick={copySettings}>Copier les réglages</button>
      <button className="publish-button" onClick={publish}>Publier sur le Stratège</button>
    </footer>
  </main>;
}

createRoot(document.getElementById('strategy-studio-root')).render(<Studio/>);
