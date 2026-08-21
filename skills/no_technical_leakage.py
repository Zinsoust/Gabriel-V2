"""Interdiction de laisser fuiter les identifiants techniques.

Gabriel puise dans des bases de connaissances qui portent des identifiants
internes — noms de signaux, codes de patterns, références de cartes. Rien
n'empêche un modèle de les recopier tels quels dans un texte destiné à
l'utilisateur : « L'audience montre un signal : 'confusion technique'
(pattern [confused_audience] : valeur = clarté). »

Cette consigne existait en **trois variantes distinctes** dans le dépôt, dont
deux copies strictement identiques (434 caractères, au caractère près) dans
les deux interprétations du Psychologue. Ce sont ces deux-là qui sont
unifiées ici : le texte injecté n'a pas bougé d'un octet.

Les deux autres variantes ne sont **pas** touchées, et c'est délibéré :

* ``core/analyzer.py`` (analyse principale) emploie une formulation plus
  courte, avec ses propres exemples ;
* ``agents/stratege.py`` en a une troisième, adaptée à son vocabulaire.

Les unifier changerait le texte réellement envoyé au modèle à deux endroits
supplémentaires — une décision produit, pas une correction mécanique. La
dette restante est donc mesurée et nommée plutôt que masquée : trois textes,
pas quatre variantes mystérieuses.
"""

from skills.base import CatalogSkill, SkillSpec
from skills.registry import registry


def _no_technical_leakage_skill() -> CatalogSkill:
    from core.analyzer import _NO_TECHNICAL_LEAKAGE
    return CatalogSkill(
        spec=SkillSpec(
            id='writing.no_technical_leakage',
            name='Pas de fuite technique',
            description=(
                "Impose de traduire tout identifiant interne (signal, pattern, "
                "code de concept) en langage naturel avant qu'il n'atteigne "
                "l'utilisateur."),
            domain='writing',
            source='core/analyzer.py:_NO_TECHNICAL_LEAKAGE',
            accepts_free_text=False,
            solves=(
                "Empêche un rapport de trahir la mécanique interne de Gabriel "
                "— ce qui détruit la crédibilité d'une analyse même juste, "
                "parce que le lecteur y voit une machine plutôt qu'un avis."),
            when_to_use=(
                "Dans tout prompt qui reçoit du contexte issu d'une base de "
                "connaissances : sans elle, les identifiants ressortent tels "
                "quels dans le texte visible."),
            required_info=(),
            methodology_summary=(
                "Une interdiction explicite, un exemple de ce qui est interdit "
                "et un exemple de la reformulation attendue — le contraste "
                "faisant plus que la règle seule."),
            limitations=(
                "Deux autres formulations de cette même règle subsistent "
                "ailleurs (analyse principale, Stratège), avec leurs propres "
                "exemples. Les unifier changerait le texte envoyé au modèle à "
                "ces endroits : décision produit assumée, pas oubli."),
            output_format="Bloc de texte fixe à injecter dans le prompt système.",
        ),
        catalog={'gabriel': _NO_TECHNICAL_LEAKAGE},
        normalizer=lambda _requested: 'gabriel',
    )


def register_all() -> None:
    registry.register(_no_technical_leakage_skill())
