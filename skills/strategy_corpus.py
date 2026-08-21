"""Corpus stratégique — 39 méthodes business nommées.

Premier savoir-faire de Gabriel adossé à un corpus documentaire plutôt qu'à
un catalogue à clés : `agents/stratege/rag/**` contient 39 méthodes nommées
(formules de pricing avec paliers 7 €→10 000 €+, design d'offre, règles
audience→offre, schémas de marché gagnants et perdants, conversion, formats
sociaux, décision immédiate).

Ce que cette déclaration change. Le corpus existe et fonctionne déjà — il est
consulté par recherche sémantique dans `agents/stratege.py::_load_rag_rules`.
Mais il n'est **atteignable qu'en devinant les bons mots** : personne ne peut
demander « quelles méthodes de pricing Gabriel connaît-il ? ». Le déclarer
rend ces 39 méthodes énumérables, sans toucher à la récupération elle-même.
"""

import json
import pathlib

from skills.base import CorpusSkill, SkillSpec
from skills.registry import registry

_CORPUS_DIR = pathlib.Path(__file__).resolve().parent.parent / 'agents' / 'stratege' / 'rag'

# Les entrées ne portent pas toutes le même champ descriptif : les méthodes et
# principes ont `principle`, les schémas de marché ont `pattern`. On lit les
# deux plutôt que d'en imposer un — le corpus est la source de vérité, pas le
# lecteur.
_LABEL_FIELDS = ('principle', 'pattern')


def _load_corpus_entries() -> dict:
    """id → libellé lisible, pour les 39 méthodes du corpus stratégique.

    `router_rules.json` est exclu : c'est de la configuration de recherche,
    pas une méthode.
    """
    entries = {}
    if not _CORPUS_DIR.exists():
        return entries
    for path in sorted(_CORPUS_DIR.rglob('*.json')):
        if path.name == 'router_rules.json':
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception as error:   # noqa: BLE001 — un fichier illisible ne
            # doit pas empêcher de déclarer les autres méthodes.
            print(f"[SKILL] Corpus stratégique — {path.name} illisible : {error}")
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            entry_id = str(item.get('id') or '').strip()
            if not entry_id:
                continue
            label = next((str(item[f]) for f in _LABEL_FIELDS if item.get(f)), entry_id)
            entries[entry_id] = label
    return entries


# Les 8 fichiers du corpus, tels que `_RAG_CATEGORIES` les référence déjà.
_CORPUS_SOURCES = (
    'audience_to_offer_rules', 'immediate_decision_rules', 'social_format_rules',
    'pricing_logic', 'offer_design', 'conversion',
    'winning_patterns', 'failed_patterns',
)


def _retrieve(query: str) -> str:
    """Récupère les méthodes pertinentes via l'outil de recherche documentaire.

    Un Skill enseigne, il n'exécute pas : la récupération passe par
    `knowledge.search`, déjà déclaré — d'où `allowed_tools`.
    """
    from tools import registry as tool_registry
    try:
        result = tool_registry.get('knowledge.search').run(
            query=query, agent='stratege', sources=list(_CORPUS_SOURCES), top_k=4)
    except Exception as error:   # noqa: BLE001 — dégradation gracieuse déjà en
        # place partout ailleurs dans le pipeline stratégique.
        print(f"[SKILL] Corpus stratégique indisponible : {error}")
        return ''
    return result.get('context', '')


def _corpus_skill() -> CorpusSkill:
    entries = _load_corpus_entries()
    familles = ("pricing (paliers 7 €→10 000 €+), design d'offre, règles "
                "audience→offre, conversion, décision immédiate, formats "
                "sociaux, schémas de marché gagnants et perdants")
    return CorpusSkill(
        spec=SkillSpec(
            id='strategy.business_corpus',
            name='Corpus stratégique business',
            description=(
                f"{len(entries)} méthodes business nommées, récupérées par "
                "pertinence : " + familles + "."),
            domain='strategy',
            source='agents/stratege/rag/**',
            accepts_free_text=True,
            solves=(
                "Fournit au Stratège des méthodes business éprouvées et "
                "nommées — formules de prix, structures d'offre, schémas "
                "d'échec connus — plutôt qu'un raisonnement improvisé."),
            when_to_use=(
                "Quand une décision porte sur le prix, la structure d'une "
                "offre, un format de contenu ou un risque d'échec marché — "
                "c'est-à-dire à chaque décision stratégique réelle."),
            required_info=('situation ou question stratégique, en texte libre',),
            methodology_summary=(
                f"{len(entries)} méthodes nommées réparties en trois familles "
                "(méthode stratégique, principes business, schémas de marché), "
                "sélectionnées par similarité sémantique avec la situation "
                "décrite plutôt que choisies par leur nom."),
            allowed_tools=('knowledge.search',),
            limitations=(
                "Récupération par pertinence, pas par nom : citer un "
                "identifiant de méthode ne garantit pas de la recevoir. Le "
                "routage par catégorie utilisé en production "
                "(agents/stratege.py::_load_rag_rules — top_k par famille, "
                "déclencheurs de requête, cadres conceptuels) est plus riche "
                "que cette recherche unique et n'est pas rebranché ici : "
                "le déclarer ne doit pas dégrader ce qui fonctionne."),
            output_format=(
                "Extraits de méthodes formatés pour injection dans un prompt, "
                "chacun préfixé de sa source."),
        ),
        entries=entries,
        retrieve=_retrieve,
    )


def register_all() -> None:
    registry.register(_corpus_skill())
