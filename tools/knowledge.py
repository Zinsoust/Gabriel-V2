"""Outil de recherche documentaire — le corpus RAG de Gabriel.

`core/rag.py` sépare recherche (`search`/`search_filtered`) et mise en forme
(`format_context`) en deux appels, mais aucun consommateur réel ne les
utilise séparément : les trois sites d'appel (`core/analyzer.py`,
`agents/stratege.py`) enchaînent systématiquement les deux. L'outil déclare
donc la chaîne réelle, comme `files.parse_comments` l'a déjà fait pour
l'import de fichiers — pas seulement la recherche brute.

`sources` devient un paramètre optionnel plutôt que deux fonctions
séparées : filtré si fourni, global sinon. C'est la fusion que l'audit des
capacités avait identifiée.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _search_knowledge(query, agent, top_k=4, sources=None, max_chars=1800):
    from core import rag

    if sources:
        results = rag.search_filtered(query, agent, sources, top_k=top_k)
    else:
        results = rag.search(query, agent, top_k=top_k)
    return {"results": results, "context": rag.format_context(results, max_chars=max_chars)}


SEARCH_KNOWLEDGE = ToolSpec(
    id='knowledge.search',
    name='Recherche documentaire (RAG)',
    description=(
        "Cherche dans le corpus de connaissance d'un agent (psychologie, "
        "stratégie, copywriting…) et rend le contexte déjà formaté pour "
        "injection dans un prompt."),
    category='knowledge',
    inputs=(
        ToolInput('query', "Texte de la requête"),
        ToolInput('agent', "Corpus à interroger : psychologue, stratege, "
                           "createur, psychologue_psycho ou psychologue_socio"),
        ToolInput('top_k', "Nombre de résultats (défaut 4)", required=False),
        ToolInput('sources', "Noms de fichiers sans extension pour restreindre "
                             "la recherche (défaut : corpus entier)",
                  required=False),
        ToolInput('max_chars', "Longueur maximale du contexte formaté (défaut 1800)",
                  required=False),
    ),
    output="{results: [{text, source, score}, ...], context: str}",
    # Déterministe *pour un index stable* : même requête, même index → même
    # résultat (similarité cosinus). L'index ne change qu'à la reconstruction
    # du corpus (admin), pas à l'usage courant.
    deterministic=True,
    # Le premier appel sur un corpus non chargé peut déclencher deux
    # constructions redondantes en cas d'accès concurrent (pas de verrou dans
    # `_load_or_build`) — idempotent, jamais incorrect, seulement du travail
    # dupliqué au démarrage. Sans conséquence une fois l'index en cache.
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,   # local ; le premier chargement du modèle sémantique
                      # peut prendre plusieurs secondes, les suivants sont immédiats
)




def _retrieve_concept_cards(rag_name, dashboard_signals=None, max_cards=4,
                            max_chars=2000):
    from core import rag

    cards = rag.load_concept_cards(rag_name)
    selected = rag.filter_concept_cards_by_triggers(
        cards, dashboard_signals or [], max_cards=max_cards)
    return {
        'cards': selected,
        'context': rag.format_concept_cards_context(selected, max_chars=max_chars),
        'available': len(cards),
    }


RETRIEVE_CONCEPT_CARDS = ToolSpec(
    id='knowledge.concept_cards',
    name='Cartes de concept',
    description=(
        "Sélectionne les cartes de concept d'un corpus spécialisé selon les "
        "signaux réellement mesurés dans l'analyse, et rend le contexte "
        "formaté pour injection dans un prompt."),
    category='knowledge',
    inputs=(
        ToolInput('rag_name', "Corpus de cartes : 'psychologie' ou 'socioculturel'"),
        ToolInput('dashboard_signals',
                  "Signaux mesurés (émotion dominante, thèmes, postures) qui "
                  "guident la sélection ; sans eux, les premières cartes sont "
                  "rendues telles quelles", required=False),
        ToolInput('max_cards', "Nombre maximum de cartes retenues (défaut 4)",
                  required=False),
        ToolInput('max_chars', "Longueur maximale du contexte formaté (défaut 2000)",
                  required=False),
    ),
    output="{cards: [...], context: str, available: int}",
    # Sélection par correspondance de mots-clés, pas par modèle : mêmes cartes
    # et mêmes signaux donnent toujours le même choix.
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,   # lecture de fichiers locaux
)


def register_all() -> None:
    registry.register(FunctionTool(SEARCH_KNOWLEDGE, _search_knowledge))
    registry.register(FunctionTool(RETRIEVE_CONCEPT_CARDS, _retrieve_concept_cards))


register_all()
