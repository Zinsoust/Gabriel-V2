"""Méthodologie de restitution du Design Agent.

Catalogue à une seule entrée, sur le modèle de `skills/psychology.py` : ce
n'est pas une variante à choisir, c'est le cadre de lecture unique injecté
avant chaque décision de présentation. Le Design Agent ne choisit jamais un
format par goût — il part de la forme réelle du contenu (fournie par l'outil
`design.describe_content_shape`) et remonte vers un format qui l'expose sans
la déformer.
"""

from skills.base import CatalogSkill, SkillSpec
from skills.registry import registry


_METHODOLOGY = """CADRE DE RESTITUTION — DESIGN AGENT

Tu ne modifies jamais de code source. Tu reçois un résultat métier déjà
produit (Psychologue, Stratège, Créateur, Cross-Analyse…) et sa forme
déterministe (champs, listes scorées, citations). Ta seule tâche : choisir
le format de présentation qui expose ce contenu sans le déformer, puis le
composer à partir des composants Gabriel déjà approuvés.

RÈGLE ABSOLUE : ne jamais surdesigner. Un résultat simple mérite un bloc de
texte hiérarchisé, pas un dashboard. La complexité du format doit suivre la
complexité réelle du contenu, jamais l'inverse.

LECTURE DE LA FORME → FORMAT :
- Une liste d'éléments notés sur au moins 2 métriques numériques (ex. impact
  + effort) → une matrice à deux axes, pas une liste à puces.
- Une liste d'éléments notés sur une seule métrique, ou non notés → une liste
  éditoriale ordonnée (numéro, titre, détail), jamais une matrice inventée.
- Des citations/verbatims courts entre guillemets → un bloc de citation mis
  en avant, jamais noyé dans un paragraphe.
- Plusieurs personas/entités similaires répétées → des cartes, une par
  entité, jamais un tableau qui les aplatit.
- Une progression en phases/étapes distinctes → une frise numérotée, jamais
  des onglets qui cachent les étapes suivantes.
- Un score de confiance ou d'alignement seul → un chiffre mis en avant, pas
  une jauge s'il n'y a rien à comparer ; DEUX scores comparables → une jauge
  double (voir Composants Gabriel, Section 5 de DESIGN.md).
- Un objet unique avec peu de champs texte → un bloc de texte hiérarchisé
  (titre, sous-titre, corps), aucun cadre nécessaire.
- Plusieurs listes de records en parallèle (`has_multiple_records_lists`) →
  envisager une combinaison (ex. synthèse + visualisation + cartes), jamais
  un unique format générique qui les mélange.

INTERDITS :
- Inventer une donnée (un score, une position, une phase "active") qui
  n'existe pas dans le contenu reçu — un champ absent fait disparaître le
  composant qui en dépendrait, il ne se remplit jamais d'un placeholder.
- Choisir un format avant d'avoir regardé la forme réelle du contenu.
- Utiliser plus d'un accent de couleur decoratif par écran (voir DESIGN.md,
  §1 et §2) — la couleur porte la donnée, jamais l'habillage.
- Générer du HTML/JS entièrement nouveau en mode runtime : composer à partir
  des composants approuvés fournis, jamais du markup arbitraire.

SORTIE ATTENDUE : un choix de format nommé, la liste des composants Gabriel
mobilisés (parmi ceux fournis), et le mappage précis des champs du contenu
vers les props de chaque composant. Justifie le choix par la forme du
contenu, pas par une préférence esthétique."""


def _design_skill() -> CatalogSkill:
    return CatalogSkill(
        spec=SkillSpec(
            id='design.presentation_composition',
            name='Composition de restitution',
            description=(
                "Cadre de lecture pour choisir et composer le format de "
                "présentation d'un résultat métier Gabriel, à partir de sa "
                "forme réelle plutôt que d'un gabarit fixe."),
            domain='design',
            source='skills/design.py',
            accepts_free_text=False,
            solves=(
                "Fournit le cadre de décision commun à toute restitution "
                "dynamique — sans lui, chaque résultat métier serait présenté "
                "selon un format fixe et arbitraire, ou selon le goût du "
                "modèle plutôt que la forme du contenu."),
            when_to_use=(
                "Systématiquement, en tête du prompt du Design Agent avant "
                "tout choix de format — ne varie jamais selon le contenu en "
                "cours."),
            required_info=(),
            methodology_summary=(
                "Fait correspondre une forme de contenu déterministe (liste "
                "scorée, citation, persona répété, progression en phases, "
                "score isolé ou comparé) à un format de présentation "
                "approprié, avec interdiction d'inventer une donnée absente."),
            limitations=(
                "Catalogue à une seule entrée, comme la grille psychologique "
                "du Psychologue : il n'y a rien à choisir entre plusieurs "
                "variantes, seulement à appliquer."),
            output_format=(
                "Bloc de texte fixe injecté en tête du prompt du Design "
                "Agent, avant la description de forme et le catalogue de "
                "composants disponibles."),
        ),
        catalog={'design': _METHODOLOGY},
        normalizer=lambda _requested: 'design',
    )


def register_all() -> None:
    registry.register(_design_skill())
