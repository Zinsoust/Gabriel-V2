"""Rendu HTML des décisions du Design Agent — étape mécanique, jamais du
markup improvisé.

C'est la brique manquante de l'architecture prévue : le Design Agent
(`agents/design_agent.py`) ne fait QUE décider (quel composant, quel champ va
où) — il ne produit aucun HTML. Ce module traduit cette décision en page
réelle, mais toujours en composant depuis un gabarit fixe par recette validée
(`agents/design_recipes.py`) : jamais de structure inventée à la volée. Même
philosophie que les recettes elles-mêmes — ce qui doit être fiable ne dépend
jamais d'un LLM, ici ni au choix du format, ni à son rendu.

Tout ce qui apparaît dans la page vient soit du contenu réel reçu (jamais
inventé), soit de gabarits fixes ci-dessous — rien n'est ré-écrit à la main
après coup : `render_page()` est la sortie finale, pas un brouillon.

CSS et tokens recopiés de `static/css/gabriel.css` et `templates/stratege.html`
(composants déjà livrés en production) : ce module ne définit aucun style qui
n'existe pas déjà ailleurs dans Gabriel. La sortie ne contient ni <!DOCTYPE>
ni <html>/<head>/<body> : seulement <title>/<style>/contenu, pour pouvoir
s'insérer telle quelle dans n'importe quelle page hôte.
"""

from __future__ import annotations

import html as _html
import json as _json
from typing import Any


def _esc(value: Any) -> str:
    return _html.escape(str(value)) if value is not None else ""


def _prettify(key: str) -> str:
    return key.replace('_', ' ').capitalize()


# Tokens recopiés de static/css/gabriel.css (thèmes clair et sombre réels de
# Gabriel — même palette, même police). Composants recopiés de
# templates/stratege.html (.strat-card, .conf-gauge-*, .plan-phase-*).
_BASE_CSS = """
:root {
  --bg-main:#050403; --bg-card:#151514; --bg-card-2:#1B1A18;
  --champagne:#D8B982; --champagne-soft:#C7A66B;
  --text-primary:#F4F1EA; --text-secondary:#B8B1A6; --text-muted:#817A70;
  --risk:#DC6464;
  --border-soft:color-mix(in srgb, var(--text-primary) 5.5%, transparent);
  --border-med:color-mix(in srgb, var(--text-primary) 10%, transparent);
  --font-main:'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-serif:'Fraunces', Georgia, 'Times New Roman', serif;
  --radius-lg:6px;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg-main:#FCFBF9; --bg-card:#FFFFFF; --bg-card-2:#FAF9F7;
    --champagne:#B08B58; --champagne-soft:#876943;
    --text-primary:#111318; --text-secondary:#434951; --text-muted:#6D747D;
    --risk:#C0504D;
    --border-soft:rgba(17,19,24,0.08); --border-med:rgba(17,19,24,0.14);
  }
}
:root[data-theme="light"] {
  --bg-main:#FCFBF9; --bg-card:#FFFFFF; --bg-card-2:#FAF9F7;
  --champagne:#B08B58; --champagne-soft:#876943;
  --text-primary:#111318; --text-secondary:#434951; --text-muted:#6D747D;
  --risk:#C0504D;
  --border-soft:rgba(17,19,24,0.08); --border-med:rgba(17,19,24,0.14);
}
* { box-sizing:border-box; margin:0; padding:0; }
body {
  font-family:var(--font-main); background:var(--bg-main); color:var(--text-primary);
  font-size:14px; line-height:1.65; -webkit-font-smoothing:antialiased;
}
.da-page { max-width:760px; margin:0 auto; padding:64px 28px 88px; }
.da-eyebrow {
  display:flex; align-items:center; gap:8px; font-size:11px; font-weight:600;
  letter-spacing:0.09em; text-transform:uppercase; color:var(--champagne); margin-bottom:16px;
}
.da-eyebrow::before { content:''; width:6px; height:6px; border-radius:50%; background:var(--champagne); }
.da-title {
  font-family:var(--font-serif); font-weight:500; font-size:clamp(24px,3.6vw,32px);
  line-height:1.18; letter-spacing:-0.01em; text-wrap:balance; margin:0 0 14px;
}
.da-sub { font-size:13.5px; color:var(--text-secondary); max-width:62ch; line-height:1.7; margin:0; }
.da-stack { display:flex; flex-direction:column; gap:20px; margin-top:40px; }
.strat-card {
  position:relative; overflow:hidden; padding:24px 26px;
  background:linear-gradient(180deg, color-mix(in srgb, var(--text-primary) 2.8%, transparent), color-mix(in srgb, var(--text-primary) 1.2%, transparent)), var(--bg-card);
  border:1px solid var(--border-med); border-radius:10px;
  animation:da-rise .45s cubic-bezier(.22,1,.36,1) both;
}
@media (prefers-reduced-motion: reduce) { .strat-card { animation:none; } }
@keyframes da-rise { from{opacity:0; transform:translateY(8px);} to{opacity:1; transform:none;} }
.da-card-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:18px; flex-wrap:wrap; }
.da-pill {
  display:inline-flex; align-items:center; gap:6px; font-size:10.5px; font-weight:600;
  letter-spacing:0.03em; padding:5px 10px 5px 8px; border-radius:20px; font-family:var(--font-main);
}
.da-pill::before { content:''; width:5px; height:5px; border-radius:50%; }
.da-pill--match { background:color-mix(in srgb, var(--champagne) 14%, transparent); color:var(--champagne); }
.da-pill--match::before { background:var(--champagne); }
.da-pill--gap { background:color-mix(in srgb, var(--risk) 12%, transparent); color:var(--risk); }
.da-pill--gap::before { background:var(--risk); }
.da-timing { font-size:10.5px; color:var(--text-muted); font-variant-numeric:tabular-nums; }
.da-field { font-size:12px; color:var(--text-muted); margin-bottom:18px; margin-top:-6px; font-family:ui-monospace, Menlo, monospace; }
.conf-gauge-pair { display:grid; grid-template-columns:1fr 1fr; gap:1px; background:var(--border-soft); border:1px solid var(--border-soft); border-radius:8px; overflow:hidden; }
.conf-gauge-card { background:var(--bg-card); padding:22px 18px 20px; text-align:center; }
.conf-gauge-card-label { font-size:11px; color:var(--text-secondary); font-weight:600; margin-bottom:14px; }
.conf-gauge-wrap { position:relative; width:100%; max-width:170px; height:92px; margin:0 auto 4px; }
.conf-gauge-track { stroke:var(--border-med); }
.conf-gauge-fill { stroke-dasharray:226.2; transition:stroke-dashoffset 1.1s cubic-bezier(.2,.8,.2,1); }
.conf-gauge-fill--ok { stroke:var(--champagne); }
.conf-gauge-fill--risk { stroke:var(--risk); }
.conf-gauge-num { position:absolute; bottom:0; left:0; right:0; font-weight:700; font-size:25px; color:var(--text-primary); font-variant-numeric:tabular-nums; }
.conf-gauge-num small { font-size:11px; color:var(--text-muted); font-weight:600; }
.plan-phase-list { display:flex; flex-direction:column; }
.plan-phase { display:grid; grid-template-columns:30px minmax(0,1fr); gap:16px; padding:20px 0; border-top:1px solid var(--border-soft); }
.plan-phase:first-child { border-top:none; padding-top:2px; }
.plan-phase-num { font-family:var(--font-serif); font-weight:500; font-size:16px; color:var(--champagne-soft); font-variant-numeric:tabular-nums; opacity:.85; }
.plan-phase-title { font-size:14px; font-weight:600; color:var(--text-primary); margin-bottom:10px; line-height:1.45; }
.plan-section-title { font-size:9.5px; text-transform:uppercase; letter-spacing:0.09em; color:var(--text-muted); font-weight:700; margin:11px 0 4px; }
.plan-items { display:flex; flex-direction:column; gap:4px; }
.plan-item { font-size:12.5px; color:var(--text-secondary); line-height:1.65; }
.gap-raw { font-family:ui-monospace, Menlo, monospace; font-size:11.5px; color:var(--text-secondary); white-space:pre-wrap; line-height:1.75; background:var(--border-soft); border-radius:6px; padding:16px 18px; }
"""


def _render_confidence_gauge(decision: dict, content: dict) -> str:
    """Gabarit fixe de la recette `confidence_pair_v1`. N'invente jamais de
    champ : lit exactement les deux clés que la recette a mappées."""
    mapping = decision["field_mapping"]
    ok_key = next((k for k, v in mapping.items() if 'ok' in v), None)
    risk_key = next((k for k, v in mapping.items() if 'risk' in v), None)

    def gauge(key, tone):
        raw = content.get(key)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            return ""
        pct = round(raw * 100) if raw <= 1 else round(raw)
        pct = max(0, min(100, pct))
        offset = round(226.2 * (1 - pct / 100), 1)
        return f"""<div class="conf-gauge-card">
          <div class="conf-gauge-card-label">{_esc(_prettify(key))}</div>
          <div class="conf-gauge-wrap">
            <svg viewBox="0 0 190 112" width="100%" height="92">
              <path class="conf-gauge-track" d="M 10 102 A 85 85 0 0 1 180 102" fill="none" stroke-width="8" stroke-linecap="round"/>
              <path class="conf-gauge-fill conf-gauge-fill--{tone}" d="M 10 102 A 85 85 0 0 1 180 102" fill="none" stroke-width="8" stroke-linecap="round" stroke-dashoffset="{offset}"/>
            </svg>
            <div class="conf-gauge-num">{pct}<small>%</small></div>
          </div>
        </div>"""

    return f'<div class="conf-gauge-pair">{gauge(ok_key, "ok")}{gauge(risk_key, "risk")}</div>'


def _render_editorial_numbered_list(decision: dict, content: dict) -> str:
    """Gabarit fixe de la recette `editorial_list_v1`. Le premier champ mappé
    « titre » devient le titre de chaque ligne ; tous les autres deviennent
    des sous-sections, dans l'ordre reçu — jamais de champ ajouté qui
    n'existe pas dans le contenu."""
    list_key = next(iter(decision["field_mapping"]))
    field_map = decision["field_mapping"][list_key]
    title_key = next((k for k, v in field_map.items() if v == "titre"), next(iter(field_map)))
    detail_keys = [k for k in field_map if k != title_key]
    records = content.get(list_key) or []

    items = []
    for i, record in enumerate(records, start=1):
        title = _esc(record.get(title_key, ""))
        details = "".join(
            f'<div class="plan-section-title">{_esc(_prettify(dk))}</div>'
            f'<div class="plan-items"><div class="plan-item">{_esc(record[dk])}</div></div>'
            for dk in detail_keys if record.get(dk)
        )
        items.append(
            f'<div class="plan-phase"><div class="plan-phase-num">{i:02d}</div>'
            f'<div><div class="plan-phase-title">{title}</div>{details}</div></div>'
        )
    return f'<div class="plan-phase-list">{"".join(items)}</div>'


def _render_fallback(decision: dict, content: dict) -> str:
    """Aucune recette : montre le manque tel quel plutôt que d'improviser un
    affichage — le repli est aussi mécanique que le reste, jamais un
    freestyle du renderer pour compenser l'absence de recette."""
    return f'<div class="gap-raw">{_esc(_json.dumps(decision, ensure_ascii=False, indent=2))}</div>'


_RENDERERS = {
    "confidence_pair_v1": _render_confidence_gauge,
    "editorial_list_v1": _render_editorial_numbered_list,
}


def render_fragment(compose_result: dict, envelope: dict) -> str:
    """Rend le fragment HTML de la décision d'un seul `compose()` — le point
    d'entrée normal, un envelope à la fois."""
    decision = compose_result["decision"]
    content = envelope.get("content", {})
    renderer = _RENDERERS.get(decision.get("recipe_id"), _render_fallback)
    return renderer(decision, content)


def render_card(compose_result: dict, envelope: dict, elapsed_ms: float | None = None) -> str:
    """Une carte complète : pastille de statut + champ source + fragment.
    Tout est dérivé de la décision et de l'envelope reçus — aucun texte de
    légende écrit à la main pour un cas particulier."""
    decision = compose_result["decision"]
    recipe_id = decision.get("recipe_id")
    field_names = ", ".join(envelope.get("content", {}).keys())
    pill_cls = "da-pill--match" if recipe_id else "da-pill--gap"
    pill_label = _esc(recipe_id or "aucune recette")
    timing = f'{elapsed_ms:.2f} ms' if elapsed_ms is not None else ""
    fragment = render_fragment(compose_result, envelope)
    return (
        '<div class="strat-card">'
        f'<div class="da-card-head"><span class="da-pill {pill_cls}">{pill_label}</span>'
        f'<span class="da-timing">{timing}</span></div>'
        f'<div class="da-field">{_esc(field_names)}</div>'
        f'{fragment}</div>'
    )


def render_page(
    cards: list[str],
    title: str = "Design Agent",
    eyebrow: str = "Gabriel · Design Agent",
    subtitle: str = "",
) -> str:
    """Assemble la page finale à partir de cartes déjà rendues (`render_card`).
    Sortie sans <!DOCTYPE>/<html>/<head>/<body> : à insérer telle quelle dans
    une page hôte (ex. publication Artifact, ou un template Flask)."""
    body = "\n".join(cards)
    sub_html = f'<p class="da-sub">{_esc(subtitle)}</p>' if subtitle else ""
    return (
        f'<title>{_esc(title)}</title><style>{_BASE_CSS}</style>'
        f'<div class="da-page">'
        f'<div class="da-eyebrow">{_esc(eyebrow)}</div>'
        f'<h1 class="da-title">{_esc(title)}</h1>'
        f'{sub_html}'
        f'<div class="da-stack">{body}</div>'
        f'</div>'
    )
