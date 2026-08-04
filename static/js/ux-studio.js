/* ═══════════════════════════════════════════════════════════════════════════
   UX STUDIO — panneau de réglage live réutilisable.
   Usage :
     UxStudio.mount({
       pageKey: 'psychologue',
       groups: [
         { label: 'Typographie', items: [
           { key: 'psy-title', label: 'Titre de page', def: 26, min: 14, max: 44, step: 0.5 },
         ]},
         { label: 'Couleurs', colors: [ { key: 'champagne', label: 'Accent', def: '#d8b982', cssVar: '--champagne' } ] },
       ],
     });
   Chaque item écrit --ux-<key> sur :root (ou un cssVar explicite). La page
   référence var(--ux-<key>, défaut) sur les éléments à rendre ajustables.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function flatItems(groups) {
    var out = [];
    groups.forEach(function (g) {
      (g.items || []).forEach(function (it) { out.push(it); });
      (g.colors || []).forEach(function (c) { out.push(c); });
    });
    return out;
  }

  function UxStudio() {}

  UxStudio.mount = function (config) {
    var pageKey = config.pageKey || 'page';
    var groups = config.groups || [];
    var STORE = 'gabriel_uxstudio_' + pageKey;
    var items = flatItems(groups);
    var defaults = {};
    items.forEach(function (it) { defaults[it.key] = it.def; });

    var state = load();

    function load() {
      try {
        var saved = JSON.parse(localStorage.getItem(STORE) || '{}');
        var merged = {};
        Object.keys(defaults).forEach(function (k) {
          merged[k] = (saved[k] !== undefined) ? saved[k] : defaults[k];
        });
        return merged;
      } catch (e) { return Object.assign({}, defaults); }
    }

    function cssVarFor(it) { return it.cssVar || ('--ux-' + it.key); }
    function unitFor(it) { return (it.unit !== undefined) ? it.unit : (typeof it.def === 'number' ? 'px' : ''); }

    function apply() {
      var root = document.documentElement.style;
      items.forEach(function (it) {
        root.setProperty(cssVarFor(it), state[it.key] + unitFor(it));
      });
      try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) {}
    }

    function exportText() {
      var lines = ['=== Réglages ' + pageKey + ' (Gabriel) ==='];
      groups.forEach(function (g) {
        lines.push('— ' + g.label + ' —');
        (g.items || []).forEach(function (it) {
          lines.push(it.label + ' : ' + state[it.key] + unitFor(it));
        });
        (g.colors || []).forEach(function (c) {
          lines.push(c.label + ' : ' + state[c.key]);
        });
      });
      lines.push('');
      lines.push('JSON : ' + JSON.stringify(state));
      return lines.join('\n');
    }

    function copy() {
      var text = exportText();
      var done = function () { toast('Réglages copiés — collez-les dans le chat.'); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text); done(); });
      } else { fallbackCopy(text); done(); }
    }
    function fallbackCopy(text) {
      var ta = el('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (e) {} document.body.removeChild(ta);
    }

    var toastTimer = null;
    function toast(msg) {
      var t = document.getElementById('uxs-toast');
      if (!t) { t = el('div', 'uxs-toast'); t.id = 'uxs-toast'; document.body.appendChild(t); }
      t.textContent = msg; t.style.display = 'block';
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { t.style.display = 'none'; }, 2600);
    }

    // ── Construction du panneau ──────────────────────────────────────────────
    var fab = el('button', 'uxs-fab');
    fab.type = 'button';
    fab.setAttribute('aria-label', 'Studio de réglage');
    fab.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';

    var panel = el('aside', 'uxs');
    panel.setAttribute('data-lenis-prevent', '');

    var head = el('div', 'uxs-head', '<span class="uxs-title">Studio de réglage</span>');
    var xBtn = el('button', 'uxs-x');
    xBtn.type = 'button';
    xBtn.setAttribute('aria-label', 'Fermer');
    xBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    head.appendChild(xBtn);

    var body = el('div', 'uxs-body');
    body.appendChild(el('p', 'uxs-note', 'Ajustez la page en direct. Tout est sauvegardé dans votre navigateur. Quand c’est bon, « Copier mes réglages » et collez-les dans le chat.'));

    groups.forEach(function (g) {
      var grp = el('div', 'uxs-group');
      grp.appendChild(el('div', 'uxs-group-label', g.label));
      (g.items || []).forEach(function (it) {
        var row = el('div', 'uxs-row');
        var top = el('div', 'uxs-row-top');
        top.appendChild(el('span', 'uxs-row-label', it.label));
        var valEl = el('span', 'uxs-row-val', state[it.key] + unitFor(it));
        top.appendChild(valEl);
        row.appendChild(top);
        var input = el('input', 'uxs-slider');
        input.type = 'range';
        input.min = it.min; input.max = it.max; input.step = it.step || 1;
        input.value = state[it.key];
        input.addEventListener('input', function () {
          state[it.key] = parseFloat(this.value);
          valEl.textContent = state[it.key] + unitFor(it);
          apply();
        });
        row.appendChild(input);
        grp.appendChild(row);
      });
      (g.colors || []).forEach(function (c) {
        var row = el('div', 'uxs-color-row');
        row.appendChild(el('span', 'uxs-row-label', c.label));
        var input = el('input');
        input.type = 'color';
        input.value = state[c.key];
        input.addEventListener('input', function () {
          state[c.key] = this.value; apply();
        });
        row.appendChild(input);
        grp.appendChild(row);
      });
      body.appendChild(grp);
    });

    var foot = el('div', 'uxs-foot');
    var actions = el('div', 'uxs-actions');
    var copyBtn = el('button', 'uxs-btn primary', 'Copier mes réglages');
    copyBtn.type = 'button';
    copyBtn.addEventListener('click', copy);
    var resetBtn = el('button', 'uxs-btn', 'Réinitialiser');
    resetBtn.type = 'button';
    resetBtn.addEventListener('click', function () {
      state = Object.assign({}, defaults);
      apply();
      // Resynchronise les curseurs affichés
      var rows = panel.querySelectorAll('.uxs-row');
      var idx = 0;
      groups.forEach(function (g) {
        (g.items || []).forEach(function (it) {
          var row = rows[idx++];
          if (!row) return;
          row.querySelector('input').value = state[it.key];
          row.querySelector('.uxs-row-val').textContent = state[it.key] + unitFor(it);
        });
      });
      panel.querySelectorAll('.uxs-color-row input').forEach(function (inp, i) {
        var cols = []; groups.forEach(function (g) { (g.colors || []).forEach(function (c) { cols.push(c); }); });
        if (cols[i]) inp.value = state[cols[i].key];
      });
      toast('Réglages réinitialisés.');
    });
    actions.appendChild(copyBtn);
    actions.appendChild(resetBtn);
    foot.appendChild(actions);

    panel.appendChild(head);
    panel.appendChild(body);
    panel.appendChild(foot);

    fab.addEventListener('click', function () { panel.classList.toggle('open'); });
    xBtn.addEventListener('click', function () { panel.classList.remove('open'); });

    document.body.appendChild(fab);
    document.body.appendChild(panel);

    apply();
  };

  window.UxStudio = UxStudio;
})();
