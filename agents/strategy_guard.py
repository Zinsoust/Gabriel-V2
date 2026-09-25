# ═══════════════════════════════════════════════════════════════════════════
# GARDE-FOU DES CHIFFRES DU STRATÈGE — aucun prix ni pourcentage inventé
#
# Constaté le 24/09/2026 sur une vraie stratégie (Cross Analyse « IA locale ») :
# « atelier à 9 € », « upsell à 49 € », « si 80 % paient 5 €, le modèle à 49 € est
# irréaliste ». Deux causes : le prompt DEMANDAIT « une fourchette de prix » et
# « le budget estimé de la cible », et la relecture critique, censée challenger,
# inventait à son tour des montants et des statistiques.
#
# Règle (même promesse que le Créateur) : un montant en euros ou un pourcentage
# n'apparaît que s'il figure dans les données réelles — profil business de
# l'utilisateur, rapport du Psychologue, cas de sa propre mémoire. Sinon on garde
# la logique (« offre d'entrée bas de gamme », « prix de votre offre actuelle »)
# et on écrit [montant à définir].
#
# Volontairement limité aux MONTANTS et aux POURCENTAGES : les durées d'un plan
# (« jours 1-30 »), les cadences et les objectifs ne sont pas des faits avancés
# comme mesurés.
#
# Deux protections, comme pour le Créateur :
#   1. SOURCE_RULE — consigne commune au prompt et à la relecture critique ;
#   2. guard_strategy() — contrôle déterministe, puis réécriture ciblée
#      passage par passage (un modèle applique mal une consigne sur un long
#      JSON), puis remplacement par un emplacement explicite en dernier recours.
# ═══════════════════════════════════════════════════════════════════════════

import copy
import json
import re

AMOUNT_PLACEHOLDER = "[montant à définir]"
PERCENT_PLACEHOLDER = "[à mesurer]"

SOURCE_RULE = """RÈGLE DES CHIFFRES (non négociable) :
- Aucun montant en euros ou en dollars, aucun pourcentage qui ne figure pas dans le PROFIL BUSINESS ou dans le RAPPORT DU PSYCHOLOGUE ci-dessus. Cela vaut pour les prix, les budgets, les revenus attendus, les taux de conversion et toute « statistique » (« 80 % des gens paient… »).
- Pour le prix, raisonne par STRUCTURE et par ANCRAGE : positionnement (entrée / milieu / premium), rapport aux offres et aux prix déjà donnés dans le profil business, rôle de chaque palier (offre d'entrée, offre principale, extension). N'écris un montant que s'il est dans le profil business ; sinon écris [montant à définir] et dis COMMENT le fixer (tester auprès de quelques acheteurs potentiels, comparer à l'offre actuelle).
- Les hypothèses restent qualitatives. Un objectif chiffré n'est pas un fait : ne le présente jamais comme une donnée observée.
- Ne propose pas de rareté chiffrée inventée (« il reste 5 places ») ni de benchmark de marché inventé."""

_REWRITE_SYSTEM = """Tu corriges des extraits d'une stratégie marketing. On te donne des SOURCES (les seules données réelles : profil business, rapport du Psychologue) et des extraits numérotés. Pour CHAQUE extrait, retire ce qui n'est pas dans les sources, en gardant tout le reste mot pour mot (même langue, même ton, même mise en forme).

À retirer ou reformuler :
- Un montant en euros ou en dollars absent des sources : remplace-le par sa logique (« une offre d'entrée accessible », « un tarif au-dessus de votre offre actuelle ») ou par [montant à définir : à tester auprès de quelques acheteurs potentiels]. N'invente aucun autre montant.
- Un pourcentage ou une statistique absents des sources (« 80 % des participants… », « taux de conversion de 3 % ») : reformule qualitativement (« la majorité », « une part significative ») ou retire la phrase si elle n'apporte rien sans le chiffre.
- Une rareté ou un benchmark chiffré inventé (« il reste 5 places », « le marché paie en moyenne… ») : retire-le.
- Un montant ou un pourcentage présent dans les sources est CONSERVÉ tel quel. Les durées (jours, semaines, mois) sont conservées.

Réponds UNIQUEMENT avec un JSON qui reprend les mêmes numéros : {"0": "extrait corrigé", "1": "..."}. Un extrait sans problème est renvoyé à l'identique."""

_NUM = r"\d+(?:[\s  .]\d{3})*(?:[.,]\d+)?"
_RANGE = rf"{_NUM}(?:\s?(?:[-–]|à)\s?{_NUM})?"
_MONEY_UNIT = r"(?:k\s?€|m\s?€|€|euros?|dollars?|usd|eur|\$)"
_MONEY = re.compile(rf"(?<![\w\[.,]){_RANGE}\s?{_MONEY_UNIT}(?![\w])", re.IGNORECASE)
_MONEY_FIRST = re.compile(rf"(?<![\w\[])[$€£]\s?{_NUM}")
_PERCENT = re.compile(rf"(?<![\w\[.,]){_RANGE}\s?(?:%|pour\s?cent)", re.IGNORECASE)
_PCT_KEY = re.compile(r'"[A-Za-z_]*(?:pct|pourcentage|percent)[A-Za-z_]*"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
_NUM_ONLY = re.compile(_NUM)


def _norm(number: str) -> str:
    n = re.sub(r"[\s  ]", "", number).replace(",", ".")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", n):        # « 1.200 » = 1200
        n = n.replace(".", "")
    return n[:-2] if n.endswith(".0") else n


def _numbers(claim: str) -> list:
    return [_norm(m.group(0)) for m in _NUM_ONLY.finditer(claim)]


def allowed_numbers(sources: str) -> tuple:
    """(montants, pourcentages) réellement présents dans les données. Un montant se reconnaît
    à sa devise, un pourcentage à son « % » ou à un champ *_pct : « 80 Go » ne cautionne pas « 80 % »."""
    text = sources or ""
    amounts, percents = set(), set()
    for m in _MONEY.finditer(text):
        amounts.update(_numbers(m.group(0)))
    for m in _MONEY_FIRST.finditer(text):
        amounts.update(_numbers(m.group(0)))
    for m in _PERCENT.finditer(text):
        percents.update(_numbers(m.group(0)))
    for m in _PCT_KEY.finditer(text):
        percents.add(_norm(m.group(1)))
    return amounts, percents


def unsupported_claims(text: str, amounts: set, percents: set) -> list:
    """Montants et pourcentages du texte qu'aucune donnée réelle ne soutient."""
    found = []
    for pattern, allowed in ((_MONEY, amounts), (_MONEY_FIRST, amounts), (_PERCENT, percents)):
        for m in pattern.finditer(text or ""):
            if not all(n in allowed for n in _numbers(m.group(0))):
                found.append(m.group(0).strip())
    return found


def sources_for(brain_context="", psycho_json="", title="") -> str:
    """Ce que l'utilisateur et l'audience ont réellement fourni : l'unique base des chiffres autorisés.

    La mémoire de cas n'en fait PAS partie : ses prix et ses pourcentages sont ceux que Gabriel
    a lui-même produits lors de stratégies précédentes. Les autoriser ferait de chaque invention
    la caution de la suivante (constaté le 24/09/2026 : 49 €, 99 € et 100 € revenaient d'une
    génération à l'autre, jugés « sourcés » parce qu'ils figuraient dans la mémoire)."""
    return "\n".join(str(p or "") for p in (brain_context, psycho_json, title))


def scrub_numbers(text: str) -> str:
    """Retire tous les montants et pourcentages d'un texte qui n'est pas une donnée fournie
    (typiquement : la mémoire de cas injectée dans le prompt, pour qu'elle ne suggère pas de prix)."""
    return _replace_claims(text or "", set(), set(), [])


def _leaves(node, out):
    """Chaînes du document, sous forme (conteneur, clé) pour pouvoir les remplacer."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                out.append((node, k))
            else:
                _leaves(v, out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                out.append((node, i))
            else:
                _leaves(v, out)


def _replace_claims(text: str, amounts: set, percents: set, removed: list) -> str:
    def money(m):
        if all(n in amounts for n in _numbers(m.group(0))):
            return m.group(0)
        removed.append(m.group(0).strip())
        return AMOUNT_PLACEHOLDER

    def percent(m):
        if all(n in percents for n in _numbers(m.group(0))):
            return m.group(0)
        removed.append(m.group(0).strip())
        return PERCENT_PLACEHOLDER
    text = _MONEY_FIRST.sub(money, text)
    text = _MONEY.sub(money, text)
    return _PERCENT.sub(percent, text)


def _rewrite_batches(leaves, sources: str, call_llm, parse_json) -> int:
    modified = 0
    for start in range(0, len(leaves), 8):
        lot = leaves[start:start + 8]
        extracts = {str(n): container[key] for n, (container, key) in enumerate(lot)}
        prompt = (f"{_REWRITE_SYSTEM}\n\nSOURCES :\n{sources[:6000]}\n\n"
                  f"EXTRAITS :\n{json.dumps(extracts, ensure_ascii=False)}")
        try:
            fixed = parse_json(call_llm(prompt))
        except Exception as exc:
            print(f"[STRATÈGE/garde] lot de réécriture indisponible : {exc}")
            continue
        if not isinstance(fixed, dict):
            continue
        for n, (container, key) in enumerate(lot):
            new, old = fixed.get(str(n)), container[key]
            # Une réponse vide ou coupée ne remplace jamais le texte d'origine.
            if isinstance(new, str) and new.strip() and new != old and len(new) >= 0.3 * len(old):
                container[key] = new
                modified += 1
    return modified


def guard_strategy(strategy, sources: str, call_llm=None, parse_json=None):
    """Renvoie (stratégie corrigée, liste des chiffres retirés). Ne touche jamais à l'original.

    Si call_llm est fourni, les passages fautifs sont d'abord réécrits (deux tours au plus) ;
    ce qui reste est remplacé par un emplacement explicite : le résultat ne contient
    jamais un chiffre non sourcé, même si le modèle de réécriture est indisponible."""
    amounts, percents = allowed_numbers(sources)
    work = copy.deepcopy(strategy)
    leaves = []
    _leaves(work, leaves)
    removed = sorted({claim for c, k in leaves for claim in unsupported_claims(c[k], amounts, percents)})
    if removed and call_llm and parse_json:
        for _ in range(2):
            leaves = []
            _leaves(work, leaves)
            faulty = [(c, k) for c, k in leaves if unsupported_claims(c[k], amounts, percents)]
            if not faulty or not _rewrite_batches(faulty, sources, call_llm, parse_json):
                break
    leaves = []
    _leaves(work, leaves)
    for container, key in leaves:
        container[key] = _replace_claims(container[key], amounts, percents, [])
    return work, removed
