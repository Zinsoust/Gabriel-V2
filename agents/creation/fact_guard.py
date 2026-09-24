# ═══════════════════════════════════════════════════════════════════════════
# FACT GUARD — aucun chiffre ni fait inventé dans une création
#
# Promesse de Gabriel.ai : « aucun chiffre inventé ». Une consigne dans le
# prompt ne suffit pas : testé le 13/09/2026 sur une vraie génération, le
# modèle a posé des emplacements [chiffre réel] mais inventé quand même
# « 80 % », « 3h par semaine », un tableau avant/après et une citation
# attribuée à l'équipe de Stable Diffusion.
#
# Deux protections :
#   1. guard_numbers() — déterministe : tout chiffre accompagné d'une unité
#      (%, €, h, min, x, clients…) absent des SOURCES est remplacé par
#      « [chiffre à vérifier] ». Garanti, sans appel LLM, appliqué au
#      brouillon, à la version finale, au moteur historique et aux retouches.
#   2. run(ctx) — étape du pipeline : si le texte contient une étude, un
#      témoignage, une citation ou un nom propre suspect, une passe LLM
#      remplace ce qui n'est pas dans les sources par un emplacement explicite.
#
# SOURCES = ce que l'utilisateur et Gabriel savent réellement : la demande,
# l'analyse du Psychologue (dont les verbatims), le contexte business, la
# stratégie utilisée. Un chiffre qui y figure (« 80 Go » cité par l'audience)
# est conservé.
# ═══════════════════════════════════════════════════════════════════════════

import json
import re

PLACEHOLDER = "[chiffre à vérifier]"
HANDLE_PLACEHOLDER = "[pseudo réel à insérer]"

# Règle transmise à chaque étape qui écrit ou juge (plan, rédaction, critique,
# optimisation). Mesuré le 14/09/2026 : la critique réclamait « plus de
# preuves », l'optimisation les inventait (benchmarks, « mon Dell XPS 13 »,
# « @TechFail2023 sur Reddit ») et le texte final était truffé d'emplacements.
SOURCE_RULE = """RÈGLE DES SOURCES (non négociable) :
- N'écris que ce que les données fournies permettent d'affirmer : les mots, peurs et désirs réels de l'audience, l'offre et le contexte donnés.
- Aucun chiffre, prix, durée, benchmark, pourcentage ou nombre de personnes qui ne figure pas dans les données. Formule l'idée sans chiffre plutôt que de laisser un trou.
- Aucune expérience vécue attribuée au créateur (« mon PC », « mes erreurs », « mon repo », « j'ai testé ») sauf si elle figure dans les données : propose-la comme scène à tourner, pas comme un fait.
- Aucun témoignage, pseudo, nom de client, étude ou citation inventés.
- N'invente jamais l'offre. Gabriel est l'outil qui t'aide à écrire : il n'est ni le sujet ni le produit du contenu, ne le mentionne pas. Sans offre fournie, ne vends aucun produit ni fonctionnalité : l'appel à l'action reste générique (commenter, s'abonner, [offre à préciser]).
- La force du texte vient de la justesse psychologique et des mots de l'audience, pas de preuves fabriquées."""

# Champs de production : leurs durées (« 15s », « 0-3 ») sont des indications
# de tournage, pas des affirmations adressées au public.
_SKIP_KEYS = {
    "secondes", "temps", "duree", "duree_estimee", "longueur_estimee", "numero",
    "content_type", "note_realisateur", "notes_montage", "notes_orateur",
    "notes_production", "note_strategique", "success", "parse_error",
}

_UNITS = (
    r"%|pour\s?cent|€|euros?|\$|dollars?|k€|m€|"
    r"h\d{2}\b|h\b|heures?|min\b|minutes?|secondes?|sec\b|s\b|jours?|semaines?|mois|ans?\b|années?|"
    r"x\b|fois|"
    r"clients?|personnes?|élèves?|étudiants?|utilisateurs?|abonnés?|membres?|vues?|ventes?|leads?|"
    r"entreprises?|créateurs?|participants?|inscrits?|avis|projets?|places?|deadlines?|prospects?|"
    r"commandes?|contrats?|missions?|followers?|likes?|partages?|téléchargements?|"
    r"k\b|millions?|milliards?|milliers?"
)
# Un nombre (éventuellement décimal ou « 2-3 »), puis une unité : « 80 % »,
# « 3h », « 2x », « 1 200 clients ». Les années seules (« 2017 ») et les
# numéros de liste ne sont pas visés.
_CLAIM = re.compile(
    r"(?<![\w\[.,])(\+|-)?\d+(?:[\s  .]\d{3})*(?:[.,]\d+)?(?:\s?[-–à]\s?\d+(?:[.,]\d+)?)?"
    r"\s?(?:" + _UNITS + r")",
    re.IGNORECASE,
)
# Montant avec la devise devant : « $49,87 », « €12 ».
_CURRENCY_FIRST = re.compile(r"(?<![\w\[])[$€£]\s?\d+(?:[\s  .]\d{3})*(?:[.,]\d+)?")
# Pseudos de réseaux sociaux : « @TechFail2023 ».
_HANDLE = re.compile(r"(?<![\w.])@[A-Za-z0-9_]{3,30}\b")
_SPACES = re.compile(r"[\s  ]+")


def _normalise(claim: str) -> str:
    """« 80 % » et « 80% », « 3 heures » et « 3h » désignent la même affirmation."""
    # Le signe compte : « +15 % de tarifs » n'est pas « 15 % des commentaires ».
    c = _SPACES.sub("", claim.lower()).replace(",", ".").replace("pourcent", "%")
    m = re.match(r"^([$€£])(.+)$", c)
    if m:  # « $49,87 » et « 49,87$ » : même affirmation
        c = m.group(2) + m.group(1)
    c = re.sub(r"euros?$", "€", c)
    c = re.sub(r"(minutes?|min)$", "min", c)
    return re.sub(r"(heures?|h)$", "h", c)


def _claims_in(text: str) -> set:
    """Affirmations chiffrées (nombre + unité) présentes dans un texte. On compare
    des couples nombre-unité, jamais des nombres seuls : une analyse contient
    presque tous les petits nombres, ce qui laissait passer « 3h » inventé."""
    text = text or ""
    return ({_normalise(m.group(0)) for m in _CLAIM.finditer(text)}
            | {_normalise(m.group(0)) for m in _CURRENCY_FIRST.finditer(text)})


def _psycho_mesure(psycho_data) -> dict:
    """Seules les données MESURÉES de l'analyse font foi pour un chiffre :
    tableau de bord, indicateurs, preuves statistiques, verbatims. Le texte
    rédigé par un modèle (synthèses, recommandations) peut lui-même contenir
    un « 80 % » approximatif — il ne doit pas servir de caution."""
    p = psycho_data or {}
    livrables = p.get("livrables_statistiques") or {}
    return {
        "meta": p.get("meta"),
        "dashboard": p.get("dashboard"),
        "kpis": p.get("kpis"),
        "top_comments": p.get("top_comments"),
        "verbatims": (p.get("emotions") or {}).get("commentaires_revelateurs"),
        "indicateurs": [v.get("indicateur_statistique") for v in livrables.values() if isinstance(v, dict)],
    }


def sources_text(user_request="", psycho_data=None, business_context=None, strategy=None, persona=None) -> str:
    """Tout ce que Gabriel sait réellement, à plat, pour vérifier les chiffres."""
    parts = [str(user_request or "")]
    psycho_data = _psycho_mesure(psycho_data) if psycho_data else None
    for source in (psycho_data, business_context, strategy, persona):
        if source:
            try:
                parts.append(json.dumps(source, ensure_ascii=False))
            except (TypeError, ValueError):
                parts.append(str(source))
    return "\n".join(parts)


def _clean_string(text: str, allowed: set, removed: list, handles: set = frozenset()) -> str:
    def remplacer(match):
        claim = match.group(0)
        if _normalise(claim) in allowed:
            return claim
        removed.append(claim.strip())
        return PLACEHOLDER

    def pseudo(match):
        if match.group(0).lower() in handles:
            return match.group(0)
        removed.append(match.group(0))
        return HANDLE_PLACEHOLDER
    text = _CURRENCY_FIRST.sub(remplacer, text)
    text = _CLAIM.sub(remplacer, text)
    return _HANDLE.sub(pseudo, text)


def guard_numbers(content, sources: str):
    """Renvoie (contenu nettoyé, liste des affirmations chiffrées retirées).
    Parcourt les dict/listes en profondeur ; ne touche jamais aux clés."""
    allowed = _claims_in(sources)
    handles = {h.lower() for h in _HANDLE.findall(sources or "")}
    removed = []

    def walk(value, key=None):
        if key in _SKIP_KEYS:
            return value
        if isinstance(value, str):
            return _clean_string(value, allowed, removed, handles)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in value.items()}
        return value

    return walk(content), removed


# ── Passe LLM : faits qualitatifs inventés ─────────────────────────────────

_SUSPECT = re.compile(
    r"(?i)témoign|étude|sondage|selon |d['’]après|statistique|confirm|rapport de|"
    r"chercheurs?|universit|directeur|directrice|fondateur|fondatrice|\bchez [A-Z]|"
    r"méthode [A-Z]{2,}|\bcas client|@\w{3,}|j['’]ai (?:lancé|testé|installé|galéré|essayé)|"
    r"\b(?:mon|ma|mes) (?:repo|github|pc|ordinateur|macbook|dell|config|erreurs?|logs?|terminal|notebook|scripts?|dossier|benchmark)|"
    r"\bbenchmark|[«\"'*]\s*[A-ZÀ-Ý][^«»\"]{20,}[»\"'*]\s*[—–-]"
)

_SYSTEM = """Tu es le vérificateur de faits du Créateur de Gabriel.ai. On te donne des SOURCES (ce qui est réellement connu) et un CONTENU au format JSON.

Ta seule mission : repérer dans le CONTENU chaque affirmation factuelle qui n'est PAS dans les sources et la remplacer par un emplacement explicite entre crochets. Sont concernés : noms de personnes, d'entreprises, de clients ou de marques présentés comme références ; témoignages et citations attribuées ; études, rapports, sondages ; méthodes ou programmes présentés comme existants ; résultats obtenus par des tiers.

Exemples de remplacement : [témoignage client réel à insérer], [nom du client], [source à citer], [résultat réel à insérer], [démonstration réelle à filmer].

Cas des témoignages et citations : une phrase entre guillemets attribuée à quelqu'un (client, élève, expert, « Léa, graphiste ») est un témoignage. Remplace la citation ENTIÈRE ET son auteur par [témoignage client réel à insérer] — ne garde jamais le texte de la citation, même si l'auteur est déjà entre crochets.
Cas des expériences vécues : une anecdote à la première personne attribuée au créateur (« sur mon Dell XPS 13 », « mes erreurs CUDA », « mon repo GitHub », « j'ai lancé Llama sur… ») absente des sources devient [démonstration réelle à filmer : …] avec la description générique.
Cas des pseudos : un pseudo ou compte présenté comme réel (« @TechFail2023 sur Reddit ») devient [témoignage client réel à insérer].
Cas des démonstrations : un matériel, un modèle ou un résultat précis présenté comme observé (« sur ce MacBook Air 2015, on génère… ») devient [démonstration réelle à filmer : …] avec la description générique.

Cas des produits : si le contenu vend un produit, un outil ou des fonctionnalités (y compris « Gabriel », qui est l'outil d'écriture et jamais le produit) absents des sources, remplace le nom par [votre offre] et retire les fonctionnalités inventées.
Cas des CHIFFRES NON SOURCÉS (liste fournie) : réécris chaque phrase qui les contient pour dire la même idée SANS chiffre ni emplacement entre crochets (« en 3 clics » → « en quelques clics », « 90 % des débutants abandonnent » → « beaucoup de débutants abandonnent »).

Règles :
- Ne modifie RIEN d'autre : même structure JSON, mêmes clés, même texte partout ailleurs.
- Les mots et situations tirés des verbatims de l'audience sont autorisés.
- Les promesses générales sans chiffre ni source (« installer une IA sans compétence technique ») sont autorisées.

Réponds UNIQUEMENT avec le JSON corrigé."""


def _source_digest(ctx) -> str:
    digest = sources_text(ctx.user_request, None, ctx.business_context, ctx.strategy, ctx.persona)
    psycho = ctx.psycho_data or {}
    utile = {
        "brief": psycho.get("brief"),
        "verbatims": (psycho.get("emotions") or {}).get("commentaires_revelateurs"),
        "top_comments": [c.get("text") for c in (psycho.get("top_comments") or []) if isinstance(c, dict)][:10],
        "recommandations": psycho.get("recommandations"),
    }
    return (digest + "\n" + json.dumps(utile, ensure_ascii=False))[:6000]


def run(ctx) -> None:
    final = ctx.final or ctx.draft
    if not isinstance(final, dict) or final.get("parse_error"):
        return
    texte = json.dumps(final, ensure_ascii=False)
    # Les chiffres non sourcés sont reformulés ici plutôt que remplacés plus
    # tard par « [chiffre à vérifier] » : 14/09/2026, un script YouTube en
    # comptait une trentaine et devenait illisible.
    _, non_sources = guard_numbers(final, sources_text(ctx.user_request, ctx.psycho_data, ctx.business_context, ctx.strategy, ctx.persona))
    produit_suspect = re.search(r"\bGabriel\b", texte)
    if not (_SUSPECT.search(texte) or non_sources or produit_suspect):
        return
    try:
        from agents.createur import _call_llm, _parse_json, CREATION_MAX_TOKENS
        liste = ", ".join(sorted(set(non_sources))) or "aucun"
        prompt = (f"{_SYSTEM}\n\nSOURCES :\n{_source_digest(ctx)}\n\n"
                  f"CHIFFRES NON SOURCÉS À REFORMULER SANS CHIFFRE : {liste}\n\nCONTENU :\n{texte}")
        corrige = _parse_json(_call_llm(prompt, max_tokens=CREATION_MAX_TOKENS, temperature=0.1))
        if isinstance(corrige, dict) and not corrige.get("parse_error") and corrige:
            corrige.setdefault("content_type", ctx.content_type)
            corrige["success"] = True
            ctx.final = corrige
    except Exception as exc:  # la vérification numérique déterministe reste appliquée ensuite
        print(f"[CREATION/fact_guard] passe qualitative indisponible : {exc}")


def guard_result(result, sources: str):
    """Applique guard_numbers à une réponse du Créateur (content + full_text,
    variante incluse) et note ce qui a été retiré, pour la transparence."""
    if not isinstance(result, dict):
        return result
    removed = []
    for cle in ("content", "variant"):
        if result.get(cle):
            result[cle], retires = guard_numbers(result[cle], sources)
            removed += retires
    if isinstance(result.get("full_text"), str):
        result["full_text"], retires = guard_numbers(result["full_text"], sources)
        removed += retires
    if removed:
        result["unverified_figures"] = sorted(set(removed))
    return result
