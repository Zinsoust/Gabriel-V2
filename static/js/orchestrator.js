/* ── Orchestrateur — widget flottant présent sur Psychologue / Stratège / Créateur ── */
let _orchHistory  = [];
let _orchWaiting  = false;
let _orchExpanded = false;
let _orchFadeTimer = null;

/* ── Gestion opacité : actif (100%) au survol ou en conversation, sinon 75% après 8.2s ── */
function _orchSetActive(force) {
  const panel = document.getElementById('orch-panel');
  if (!panel) return;
  if (_orchFadeTimer) { clearTimeout(_orchFadeTimer); _orchFadeTimer = null; }
  panel.classList.add('orch-active');
  if (!force) {
    _orchFadeTimer = setTimeout(() => {
      // Ne réduit l'opacité que si le curseur n'est pas sur le panel
      // et qu'aucune conversation n'est en attente
      if (!_orchWaiting && !(document.getElementById('orch-input')?.value?.trim())) {
        panel.classList.remove('orch-active');
      }
    }, 8200);
  }
}

function _orchInitOpacity() {
  const panel = document.getElementById('orch-panel');
  if (!panel) return;
  panel.addEventListener('mouseenter', () => _orchSetActive(true));
  panel.addEventListener('mouseleave', () => _orchSetActive(false));
  document.getElementById('orch-input')?.addEventListener('input', () => _orchSetActive(true));
}

function _orchVar(name) {
  try { return eval('typeof ' + name + " !== 'undefined' ? " + name + ' : null'); }
  catch (e) { return null; }
}

function _orchGetContext() {
  const psycho    = _orchVar('_lastAnalysisData') || _orchVar('_linkedPsychoData') || _orchVar('_psycho') || null;
  const strategie = _orchVar('_lastStratData')    || _orchVar('_strategy') || null;
  const createur  = _orchVar('_lastResult')        || null;

  // Tente de récupérer le folder_id depuis l'URL ou un attribut data
  let folderId = null;
  const urlMatch = window.location.search.match(/[?&]folder_id=([^&]+)/);
  if (urlMatch) folderId = decodeURIComponent(urlMatch[1]);
  if (!folderId) {
    const el = document.querySelector('[data-folder-id]');
    if (el) folderId = el.dataset.folderId;
  }

  return {
    psycho_data:   (psycho    && Object.keys(psycho).length)    ? psycho    : {},
    strategy_data: (strategie && Object.keys(strategie).length) ? strategie : {},
    createur_data: (createur  && Object.keys(createur).length)  ? createur  : {},
    folder_id:     folderId || null,
  };
}

function orchOpen() {
  document.getElementById('orch-bubble')?.classList.add('hidden');
  const panel = document.getElementById('orch-panel');
  panel?.classList.remove('hidden');
  document.getElementById('orch-input')?.focus();
  _orchSetActive(true);   // ouverture = actif immédiatement
  _orchInitOpacity();     // attache les listeners une seule fois
}

function orchClose() {
  document.getElementById('orch-panel')?.classList.remove('expanded');
  document.getElementById('orch-panel')?.classList.add('hidden');
  document.getElementById('orch-bubble')?.classList.remove('hidden');
  _orchExpanded = false;
}

function orchToggleExpand() {
  _orchExpanded = !_orchExpanded;
  document.getElementById('orch-panel')?.classList.toggle('expanded', _orchExpanded);
}

function _orchEsc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function _orchInline(escapedText) {
  return escapedText
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>');
}

function _orchFormat(rawText) {
  const lines = String(rawText || '').split('\n');
  let html = '';
  let listBuf = [];
  let paraBuf = [];

  function flushList() {
    if (listBuf.length) {
      html += `<ul>${listBuf.map(l => `<li>${_orchInline(l)}</li>`).join('')}</ul>`;
      listBuf = [];
    }
  }
  function flushPara() {
    if (paraBuf.length) {
      html += `<p>${paraBuf.map(l => _orchInline(l)).join('<br>')}</p>`;
      paraBuf = [];
    }
  }

  lines.forEach(rawLine => {
    const line = _orchEsc(rawLine.trim());
    if (!line) { flushList(); flushPara(); return; }

    const headingMatch = line.match(/^#{1,6}\s+(.+)$/);
    if (headingMatch) {
      flushList(); flushPara();
      html += `<p><strong>${_orchInline(headingMatch[1])}</strong></p>`;
      return;
    }

    const bulletMatch = line.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      flushPara();
      listBuf.push(bulletMatch[1]);
      return;
    }

    const labelMatch = line.match(/^\*\*([^*]+)\*\*\s*:\s*(.+)$/);
    if (labelMatch) {
      flushList(); flushPara();
      html += `<div class="orch-label-block"><div class="orch-label">${labelMatch[1]}</div><div class="orch-label-value">${_orchInline(labelMatch[2])}</div></div>`;
      return;
    }

    flushList();
    paraBuf.push(line);
  });
  flushList();
  flushPara();
  return html || `<p>${_orchInline(_orchEsc(String(rawText || '')))}</p>`;
}

function _orchAddMsg(role, text) {
  const msgs = document.getElementById('orch-messages');
  if (!msgs) return;
  const el = document.createElement('div');
  el.className = `orch-msg ${role}`;
  const body = role === 'agent'
    ? _orchFormat(text)
    : `<p>${_orchInline(_orchEsc(text)).replace(/\n/g, '<br>')}</p>`;
  el.innerHTML = `<div class="orch-bubble-text">${body}</div>`;
  msgs.appendChild(el);
  requestAnimationFrame(() => { msgs.scrollTop = msgs.scrollHeight; });
}

function _orchShowTyping() {
  const msgs = document.getElementById('orch-messages');
  if (!msgs) return;
  const el = document.createElement('div');
  el.className = 'orch-msg agent';
  el.id = 'orch-typing';
  el.innerHTML = `<div class="orch-typing"><span></span><span></span><span></span></div>`;
  msgs.appendChild(el);
  requestAnimationFrame(() => { msgs.scrollTop = msgs.scrollHeight; });
}
function _orchHideTyping() { document.getElementById('orch-typing')?.remove(); }

async function orchSend() {
  if (_orchWaiting) return;
  const input = document.getElementById('orch-input');
  const msg = (input.value || '').trim();
  if (!msg) return;

  _orchAddMsg('user', msg);
  input.value = ''; input.style.height = 'auto';
  _orchWaiting = true;
  const btn = document.getElementById('orch-send');
  if (btn) btn.disabled = true;

  // Masque les actions rapides pendant l'échange
  const quickBar = document.getElementById('orch-quick-bar');
  if (quickBar) quickBar.classList.add('orch-quick-hidden');

  _orchSetActive(true);   // reste à 100% pendant l'attente
  _orchShowTyping();
  _orchHistory.push({ role: 'user', content: msg });

  try {
    const ctx = _orchGetContext();
    const r = await fetch('/orchestrator_chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message:       msg,
        history:       _orchHistory.slice(-12),
        psycho_data:   ctx.psycho_data,
        strategy_data: ctx.strategy_data,
        createur_data: ctx.createur_data,
        folder_id:     ctx.folder_id,
      }),
    });
    const d = await r.json();
    _orchHideTyping();
    const reply = d.reply || d.error || 'Erreur de réponse.';
    _orchAddMsg('agent', reply);
    _orchHistory.push({ role: 'assistant', content: reply });
  } catch (e) {
    _orchHideTyping();
    _orchAddMsg('agent', 'Une erreur de connexion est survenue. Veuillez réessayer.');
  } finally {
    _orchWaiting = false;
    if (btn) btn.disabled = false;
    // Réaffiche la barre d'actions rapides après chaque échange
    const qb = document.getElementById('orch-quick-bar');
    if (qb) qb.classList.remove('orch-quick-hidden');
    _orchSetActive(false);  // relance le timer de 8.2s après la réponse
  }
}

/* Envoie une action rapide comme si l'utilisateur l'avait tapée */
function orchQuick(text) {
  const input = document.getElementById('orch-input');
  if (!input) return;
  input.value = text;
  orchSend();
}
