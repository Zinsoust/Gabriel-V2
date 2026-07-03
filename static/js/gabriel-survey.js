/**
 * gabriel-survey.js — Composant d'enquête non intrusif
 * Aidez-nous à améliorer Gabriel.
 *
 * Règles d'affichage :
 *  - Min 10 min entre deux enquêtes
 *  - Max 3 enquêtes par session
 *  - "Ne plus demander aujourd'hui" : bloque jusqu'à minuit
 *  - Ne pas redemander pour le même target_id si déjà répondu
 */

(function () {
  'use strict';

  // ── Clés localStorage ─────────────────────────────────────────────────────
  const LS = {
    lastShown:    'gabriel_survey_lastShownAt',
    sessionCount: 'gabriel_survey_sessionCount',
    dismissDay:   'gabriel_survey_dismissDay',
    answered:     'gabriel_survey_answered',   // JSON array de target_id répondus
  };

  const MIN_INTERVAL_MS  = 10 * 60 * 1000;  // 10 minutes
  const MAX_PER_SESSION  = 3;

  // ── Garde-fous d'affichage ────────────────────────────────────────────────
  function _canShow(targetId) {
    const now      = Date.now();
    const today    = new Date().toDateString();

    // "Ne plus demander aujourd'hui"
    const dismissDay = localStorage.getItem(LS.dismissDay);
    if (dismissDay === today) return false;

    // Intervalle minimum
    const lastShown = parseInt(localStorage.getItem(LS.lastShown) || '0', 10);
    if (now - lastShown < MIN_INTERVAL_MS) return false;

    // Max par session (sessionStorage)
    const sessionCount = parseInt(sessionStorage.getItem(LS.sessionCount) || '0', 10);
    if (sessionCount >= MAX_PER_SESSION) return false;

    // Déjà répondu pour ce target_id
    if (targetId) {
      try {
        const answered = JSON.parse(localStorage.getItem(LS.answered) || '[]');
        if (answered.includes(targetId)) return false;
      } catch (_) {}
    }

    return true;
  }

  function _markShown() {
    localStorage.setItem(LS.lastShown, String(Date.now()));
    const count = parseInt(sessionStorage.getItem(LS.sessionCount) || '0', 10);
    sessionStorage.setItem(LS.sessionCount, String(count + 1));
  }

  function _markAnswered(targetId) {
    if (!targetId) return;
    try {
      const answered = JSON.parse(localStorage.getItem(LS.answered) || '[]');
      if (!answered.includes(targetId)) {
        answered.push(targetId);
        localStorage.setItem(LS.answered, JSON.stringify(answered.slice(-50)));
      }
    } catch (_) {}
  }

  function _dismissToday() {
    localStorage.setItem(LS.dismissDay, new Date().toDateString());
  }

  // ── API calls ─────────────────────────────────────────────────────────────
  async function _recordEvent(eventType, targetType, targetId) {
    try {
      const r = await fetch('/feedback/survey-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_type: eventType, target_type: targetType, target_id: targetId }),
      });
      const d = await r.json();
      return d.event_id || null;
    } catch (_) { return null; }
  }

  async function _sendResponse(eventId, payload) {
    try {
      await fetch('/feedback/survey-response', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ survey_event_id: eventId, ...payload }),
      });
    } catch (_) {}
  }

  async function _dismiss(eventId, status) {
    try {
      await fetch('/feedback/dismiss', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: eventId, status }),
      });
    } catch (_) {}
  }

  // ── Rendu du composant ────────────────────────────────────────────────────
  function _render(opts, eventId) {
    const {
      question   = 'Ce résultat vous paraît-il utile ?',
      agent      = '',
      targetType = '',
      targetId   = '',
    } = opts;

    // Supprimer un éventuel composant précédent
    document.getElementById('gabriel-survey-widget')?.remove();

    const widget = document.createElement('div');
    widget.id = 'gabriel-survey-widget';
    widget.setAttribute('role', 'dialog');
    widget.setAttribute('aria-label', 'Enquête Gabriel');
    widget.innerHTML = `
      <div class="gsw-inner">
        <div class="gsw-header">
          <span class="gsw-label">Aidez-nous à améliorer Gabriel</span>
          <button class="gsw-close" aria-label="Fermer" data-action="later">✕</button>
        </div>
        <p class="gsw-question">${_esc(question)}</p>
        <div class="gsw-quick-btns">
          <button class="gsw-quick" data-val="oui">Oui</button>
          <button class="gsw-quick" data-val="partiellement">Partiellement</button>
          <button class="gsw-quick" data-val="non">Non</button>
        </div>
        <div class="gsw-detail hidden">
          <div class="gsw-scores">
            ${_scoreRow('relevance_score',     'Pertinence')}
            ${_scoreRow('clarity_score',       'Clarté')}
            ${_scoreRow('usefulness_score',    'Utilité')}
            ${_scoreRow('actionability_score', 'Actionnable')}
          </div>
          <textarea class="gsw-textarea" placeholder="Qu'est-ce qui pourrait être amélioré ? (optionnel)" maxlength="2000" rows="2"></textarea>
          <div class="gsw-actions">
            <button class="gsw-submit">Envoyer →</button>
          </div>
        </div>
        <div class="gsw-done hidden">
          <span class="gsw-done-msg">Merci — votre retour nous aide à améliorer Gabriel.</span>
        </div>
        <div class="gsw-footer">
          <button class="gsw-later" data-action="later">Plus tard</button>
          <button class="gsw-nodayone" data-action="nodayone">Ne plus demander aujourd'hui</button>
        </div>
      </div>`;

    document.body.appendChild(widget);

    // Animate in
    requestAnimationFrame(() => { requestAnimationFrame(() => { widget.classList.add('gsw-visible'); }); });

    let _quickChoice = null;

    // Quick answer buttons
    widget.querySelectorAll('.gsw-quick').forEach(btn => {
      btn.addEventListener('click', () => {
        _quickChoice = btn.dataset.val;
        widget.querySelectorAll('.gsw-quick').forEach(b => b.classList.remove('gsw-selected'));
        btn.classList.add('gsw-selected');
        widget.querySelector('.gsw-detail').classList.remove('hidden');
        widget.querySelector('.gsw-footer').classList.add('hidden');
      });
    });

    // Score buttons (1-5)
    widget.querySelectorAll('.gsw-score-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const group = btn.closest('.gsw-score-row');
        group.querySelectorAll('.gsw-score-btn').forEach(b => b.classList.remove('gsw-sel'));
        btn.classList.add('gsw-sel');
      });
    });

    // Submit
    widget.querySelector('.gsw-submit').addEventListener('click', async () => {
      const scores = {};
      widget.querySelectorAll('.gsw-score-row').forEach(row => {
        const sel = row.querySelector('.gsw-sel');
        if (sel) scores[row.dataset.key] = parseInt(sel.dataset.score, 10);
      });
      const freeFb = (widget.querySelector('.gsw-textarea')?.value || '').trim().slice(0, 2000);

      widget.querySelector('.gsw-submit').disabled = true;
      await _sendResponse(eventId, {
        agent, target_type: targetType, target_id: targetId,
        quick_answer: _quickChoice,
        ...scores,
        free_feedback: freeFb,
      });
      _markAnswered(targetId);
      widget.querySelector('.gsw-detail').classList.add('hidden');
      widget.querySelector('.gsw-done').classList.remove('hidden');
      setTimeout(() => _closeWidget(widget), 2800);
    });

    // Dismiss / later / nodayone
    widget.querySelectorAll('[data-action]').forEach(el => {
      el.addEventListener('click', async () => {
        const action = el.dataset.action;
        if (action === 'nodayone') { _dismissToday(); await _dismiss(eventId, 'dismissed'); }
        else                        { await _dismiss(eventId, 'later'); }
        _closeWidget(widget);
      });
    });
  }

  function _scoreRow(key, label) {
    const btns = [1, 2, 3, 4, 5].map(n =>
      `<button class="gsw-score-btn" data-score="${n}" aria-label="${n}/5">${n}</button>`
    ).join('');
    return `<div class="gsw-score-row" data-key="${key}">
      <span class="gsw-score-label">${label}</span>
      <div class="gsw-score-btns">${btns}</div>
    </div>`;
  }

  function _closeWidget(widget) {
    widget.classList.remove('gsw-visible');
    setTimeout(() => widget.remove(), 300);
  }

  function _esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── CSS injecté ───────────────────────────────────────────────────────────
  function _injectStyles() {
    if (document.getElementById('gabriel-survey-styles')) return;
    const style = document.createElement('style');
    style.id = 'gabriel-survey-styles';
    style.textContent = `
#gabriel-survey-widget {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9000;
  width: 320px;
  opacity: 0;
  transform: translateY(12px);
  transition: opacity 0.28s ease, transform 0.28s cubic-bezier(0.22,1,0.36,1);
  pointer-events: none;
}
#gabriel-survey-widget.gsw-visible {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}
.gsw-inner {
  background: #141418;
  border: 1px solid rgba(216,185,130,0.22);
  border-radius: 14px;
  padding: 18px 20px 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.03);
  position: relative;
}
.gsw-inner::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  border-radius: 14px 14px 0 0;
  background: linear-gradient(90deg, rgba(216,185,130,0.6), rgba(216,185,130,0.08));
}
.gsw-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.gsw-label {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: rgba(216,185,130,0.6);
  font-weight: 600;
}
.gsw-close {
  background: none;
  border: none;
  color: rgba(255,255,255,0.3);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
  line-height: 1;
  transition: color 0.15s;
}
.gsw-close:hover { color: rgba(255,255,255,0.6); }
.gsw-question {
  font-size: 13px;
  color: rgba(255,255,255,0.88);
  line-height: 1.6;
  margin: 0 0 14px;
}
.gsw-quick-btns {
  display: flex;
  gap: 7px;
  margin-bottom: 12px;
}
.gsw-quick {
  flex: 1;
  padding: 7px 6px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: rgba(255,255,255,0.55);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.gsw-quick:hover {
  border-color: rgba(216,185,130,0.3);
  color: rgba(216,185,130,0.8);
}
.gsw-quick.gsw-selected {
  background: rgba(216,185,130,0.1);
  border-color: rgba(216,185,130,0.4);
  color: #D8B982;
}
.gsw-detail { margin-top: 8px; }
.gsw-detail.hidden { display: none; }
.gsw-scores { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.gsw-score-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.gsw-score-label {
  font-size: 10px;
  color: rgba(255,255,255,0.45);
  width: 80px;
  flex-shrink: 0;
}
.gsw-score-btns { display: flex; gap: 4px; }
.gsw-score-btn {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.4);
  font-size: 10px;
  cursor: pointer;
  transition: all 0.12s;
  font-family: inherit;
}
.gsw-score-btn:hover {
  border-color: rgba(216,185,130,0.25);
  color: rgba(216,185,130,0.7);
}
.gsw-score-btn.gsw-sel {
  background: rgba(216,185,130,0.12);
  border-color: rgba(216,185,130,0.4);
  color: #D8B982;
}
.gsw-textarea {
  width: 100%;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  color: rgba(255,255,255,0.75);
  font-size: 11px;
  font-family: inherit;
  padding: 8px 10px;
  resize: none;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.15s;
  margin-bottom: 10px;
}
.gsw-textarea:focus { border-color: rgba(216,185,130,0.25); }
.gsw-actions { display: flex; justify-content: flex-end; }
.gsw-submit {
  padding: 7px 16px;
  border-radius: 20px;
  border: 1px solid rgba(216,185,130,0.3);
  background: rgba(216,185,130,0.08);
  color: #D8B982;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.gsw-submit:hover { background: rgba(216,185,130,0.15); }
.gsw-submit:disabled { opacity: 0.45; cursor: not-allowed; }
.gsw-done.hidden { display: none; }
.gsw-done-msg {
  display: block;
  font-size: 12px;
  color: rgba(120,200,140,0.8);
  text-align: center;
  padding: 6px 0 4px;
}
.gsw-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(255,255,255,0.05);
}
.gsw-footer.hidden { display: none; }
.gsw-later, .gsw-nodayone {
  background: none;
  border: none;
  font-size: 10px;
  color: rgba(255,255,255,0.3);
  cursor: pointer;
  padding: 2px 0;
  transition: color 0.15s;
  font-family: inherit;
}
.gsw-later:hover, .gsw-nodayone:hover { color: rgba(255,255,255,0.55); }
`;
    document.head.appendChild(style);
  }

  // ── API publique ──────────────────────────────────────────────────────────

  /**
   * Déclenche une enquête si les conditions sont remplies.
   *
   * @param {object} opts
   *   opts.eventType   'after_analysis' | 'after_strategy' | 'after_creation' | 'after_chat'
   *   opts.targetType  'analysis' | 'strategy' | 'content' | 'chat'
   *   opts.targetId    identifiant unique du résultat (analysis_id, strategy_id…)
   *   opts.agent       'psychologue' | 'stratege' | 'createur'
   *   opts.question    Texte de la question principale
   *   opts.delay       Délai avant affichage en ms (défaut: 2500)
   */
  window.GabrielSurvey = {
    trigger: function (opts) {
      opts = opts || {};
      const targetId = opts.targetId || '';
      const delay    = typeof opts.delay === 'number' ? opts.delay : 2500;

      if (!_canShow(targetId)) return;

      _injectStyles();
      _markShown();

      setTimeout(async () => {
        const eventId = await _recordEvent(
          opts.eventType  || 'after_analysis',
          opts.targetType || '',
          targetId
        );
        _render(opts, eventId);
      }, delay);
    },

    /** Réinitialise les compteurs de session (utile pour les tests). */
    _reset: function () {
      sessionStorage.removeItem(LS.sessionCount);
      localStorage.removeItem(LS.lastShown);
      localStorage.removeItem(LS.dismissDay);
    },
  };

})();
