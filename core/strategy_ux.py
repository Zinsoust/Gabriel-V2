"""Contrat sûr des réglages UX publiables pour la page Stratège."""

import re


STRATEGY_UX_FIELDS = {
    'st-ctxtitle': (13, 8, 24, 'px'),
    'st-ctxfield': (8.5, 6, 16, 'px'),
    'st-msgsize': (13.5, 10, 20, 'px'),
    'st-inputsize': (13, 10, 19, 'px'),
    'st-decision': (18, 10, 36, 'px'),
    'st-decisionlabel': (10, 7, 18, 'px'),
    'st-secttl': (13, 8, 24, 'px'),
    'st-genbtn': (13, 8, 20, 'px'),
    'st-ctabtn': (11, 8, 18, 'px'),
    'st-chatwidth': (780, 560, 1100, 'px'),
    'st-sidewidth': (215, 180, 420, 'px'),
    'st-inputheight': (74, 54, 160, 'px'),
    'st-inputwidth': (780, 280, 1400, 'px'),
    'st-inputbottom': (26, 0, 240, 'px'),
    'st-inputoffsetx': (0, -500, 500, 'px'),
    'st-inputradius': (999, 0, 999, 'px'),
    'st-inputpaddingx': (16, 0, 80, 'px'),
    'st-inputpaddingy': (6, 0, 40, 'px'),
    'st-inputgap': (4, 0, 40, 'px'),
    'st-inputborder': (1, 0, 20, 'px'),
    'st-inputshadow': (28, 0, 120, 'px'),
    'st-iconbtnsize': (28, 12, 80, 'px'),
    'st-iconsize': (14, 8, 48, 'px'),
    'st-inputbgopacity': (100, 0, 100, '%'),
    'st-inputborderopacity': (100, 0, 100, '%'),
    'st-messagegap': (26, 10, 52, 'px'),
    'st-cardradius': (16, 0, 32, 'px'),
    'st-panelradius': (14, 0, 32, 'px'),
}

STRATEGY_UX_COLORS = {
    'ux-champagne': '#d8b982',
    'ux-textprimary': '#f4f1ea',
    'ux-bgmain': '#080806',
    'st-inputbg': '#111110',
    'st-inputbordercolor': '#2b2a27',
    'st-inputtextcolor': '#f4f1ea',
    'st-inputiconcolor': '#d8b982',
}

DEFAULT_STRATEGY_UX = {
    **{key: spec[0] for key, spec in STRATEGY_UX_FIELDS.items()},
    **STRATEGY_UX_COLORS,
}

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def sanitize_strategy_ux(settings):
    """Ignore toute clé inconnue et borne chaque valeur autorisée."""
    source = settings if isinstance(settings, dict) else {}
    clean = dict(DEFAULT_STRATEGY_UX)
    for key, (default, minimum, maximum, _unit) in STRATEGY_UX_FIELDS.items():
        value = source.get(key, default)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = default
        clean[key] = max(minimum, min(maximum, value))
    for key, default in STRATEGY_UX_COLORS.items():
        value = source.get(key, default)
        clean[key] = value.lower() if isinstance(value, str) and _HEX.match(value) else default
    return clean


def strategy_ux_css(settings):
    """Produit uniquement des déclarations de variables CSS pré-autorisées."""
    clean = sanitize_strategy_ux(settings)
    declarations = []
    for key, (_default, _minimum, _maximum, unit) in STRATEGY_UX_FIELDS.items():
        declarations.append(f'--ux-{key}:{clean[key]:g}{unit}')
    declarations.extend([
        f'--champagne:{clean["ux-champagne"]}',
        f'--text-primary:{clean["ux-textprimary"]}',
        f'--bg-main:{clean["ux-bgmain"]}',
    ])
    declarations.extend(
        f'--ux-{key}:{clean[key]}' for key in STRATEGY_UX_COLORS
        if not key.startswith('ux-')
    )
    return ';'.join(declarations)
