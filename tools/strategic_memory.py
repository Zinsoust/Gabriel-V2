"""Outil de mémoire stratégique — cas passés par similarité.

`GabrielMemory.find_similar` lit les cas d'un utilisateur (ou de l'ensemble
des comptes, en repli) depuis Supabase, puis les note par similarité de
fingerprint audience — méthodologie chiffrée : émotion 20 / aspirations 25 /
frustrations 20 / motivations 15 / positionnement 10 / objectif 10.

Contrairement aux autres calculs déterministes déjà déclarés, cet outil
dépend d'une lecture réseau (Supabase) au moment de la construction de
``GabrielMemory`` — il n'est donc pas purement local, même si le score
lui-même est un calcul pur une fois les cas chargés.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _find_similar_cases(psycho_data, business_context=None, n=6, user_id=None):
    from core.memory import GabrielMemory
    memory = GabrielMemory(user_id)
    matches = memory.find_similar(psycho_data, business_context, n=n, user_id=user_id)
    return {'matches': matches, 'total_cases_considered': len(memory.cases)}


FIND_SIMILAR_STRATEGY_CASES = ToolSpec(
    id='strategic_memory.find_similar_cases',
    name='Cas stratégiques similaires',
    description=(
        "Retrouve les cas passés (stratégie + feedback) dont le profil "
        "d'audience ressemble à l'analyse en cours, pour éclairer une "
        "nouvelle décision par précédent."),
    category='strategic_memory',
    inputs=(
        ToolInput('psycho_data', "Rapport du Psychologue (dict complet)"),
        ToolInput('business_context', "Contexte business, affine le fingerprint",
                  required=False),
        ToolInput('n', "Nombre maximum de cas rendus (défaut 6)", required=False),
        ToolInput('user_id', "Priorise les cas de cet utilisateur si suffisants",
                  required=False),
    ),
    output="{matches: [{case, score}, ...], total_cases_considered: int}",
    deterministic=True,   # le score est pur ; seul le chargement des cas ne l'est pas
    parallel_safe=True,   # chaque appel charge sa propre instance, aucun état partagé
    cacheable=False,      # de nouveaux cas peuvent être ajoutés entre deux appels
    timeout_s=None,       # délégué à api/db.py (déjà doté de retry et timeout)
)


def register_all() -> None:
    registry.register(FunctionTool(FIND_SIMILAR_STRATEGY_CASES, _find_similar_cases))


register_all()
