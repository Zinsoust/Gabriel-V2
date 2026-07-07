/* ── Orchestrateur — widget flottant présent sur Psychologue / Stratège / Créateur ── */
let _orchHistory = [];
let _orchWaiting = false;
let _orchExpanded = false;

function _orchVar(name) {
  try { return eval('typeof ' + name + " !== 'undefined' ? " + name + ' : null'); }
  catch (e) { return null; }
}

function _orchGetContext() {
  const psycho = _orchVar('_lastAnalysisData') || _orchVar('_linkedPsychoData') || _orchVar('_psycho') || null;
  const strategie = _orchVar('_lastStratData') || _orchVar('_strategy') || null;
  const createur = _orchVar('_lastResult') || null;
  return {
    psycho_data:   (psycho && Object.keys(psycho).length) ? psycho : {},
    strategy_data: (strategie && Object.keys(strategie).length) ? strategie : {},
    createur_data: (createur && Object.keys(createur).length) ? createur : {},
  };
}

function orchOpen() {
  document.getElementById('orch-bubble')?.classList.add('hidden');
  document.getElementById('orch-panel')?.classList.remove('hidden');
  document.getElementById('orch-input')?.focus();
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

function _orchAddMsg(role, text) {
  const msgs = document.getElementById('orch-messages');
  if (!msgs) return;
  const el = document.createElement('div');
  el.className = `orch-msg ${role}`;
  el.innerHTML = `<div class="orch-bubble-text">${_orchEsc(text).replace(/\n/g, '<br>')}</div>`;
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
  _orchShowTyping();
  _orchHistory.push({ role: 'user', content: msg });

  try {
    const ctx = _orchGetContext();
    const r = await fetch('/orchestrator_chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: msg,
        history: _orchHistory.slice(-10),
        psycho_data: ctx.psycho_data,
        strategy_data: ctx.strategy_data,
        createur_data: ctx.createur_data,
      }),
    });
    const d = await r.json();
    _orchHideTyping();
    const reply = d.reply || d.error || 'Erreur de réponse.';
    _orchAddMsg('agent', reply);
    _orchHistory.push({ role: 'assistant', content: reply });
  } catch (e) {
    _orchHideTyping();
    _orchAddMsg('agent', 'Erreur de connexion — réessayez.');
  } finally {
    _orchWaiting = false;
    if (btn) btn.disabled = false;
  }
}
