"""Savoir-faire d'écriture du Créateur.

Ces méthodologies existent déjà et sont éprouvées en production. On ne les
réécrit pas : on les *déclare*. Les catalogues sont référencés par leur objet
d'origine dans `agents.createur`, jamais recopiés — une divergence entre le
Skill et le code historique serait invisible et durable.
"""

from skills.base import CatalogSkill, SkillSpec
from skills.registry import registry


def _tone_skill() -> CatalogSkill:
    from agents.createur import _TONE_ALIASES, _TONE_DISCIPLINES
    return CatalogSkill(
        spec=SkillSpec(
            id='writing.tone_discipline',
            name="Disciplines de tonalité",
            description=(
                "Chaque tonalité est une discipline d'écriture — une logique de "
                "pensée, une structure et une séquence imposées — et non un "
                "habillage stylistique."),
            domain='writing',
            source='agents/createur.py:_TONE_DISCIPLINES',
            accepts_free_text=False,
            solves=(
                "Imposer une logique de pensée et une séquence d'écriture "
                "cohérentes avec la tonalité demandée, plutôt qu'un vocabulaire "
                "de surface."),
            when_to_use=(
                "Avant toute rédaction du Créateur, dès qu'une tonalité est "
                "précisée par l'utilisateur ou déduite du profil business."),
            required_info=('tone',),
            methodology_summary=(
                "Catalogue fermé de 10 disciplines nommées (expert, éducatif, "
                "premium, storytelling…), chacune avec Inspiration / Intention / "
                "Règles / Séquence obligatoire."),
            limitations=(
                "Fermé : une tonalité hors catalogue et hors alias ne produit "
                "rien (chaîne vide), contrairement à writing.emotion_directive."),
            output_format="Bloc de texte à injecter tel quel dans le prompt système.",
        ),
        catalog=_TONE_DISCIPLINES,
        aliases=_TONE_ALIASES,
    )


def _emotion_skill() -> CatalogSkill:
    from agents.createur import (_EMOTION_DIRECTIVES, _normalize_emotion_key,
                                 _free_emotion_directive)
    return CatalogSkill(
        spec=SkillSpec(
            id='writing.emotion_directive',
            name="Directives d'émotion cible",
            description=(
                "Traduit l'émotion que l'audience doit ressentir en leviers "
                "d'écriture concrets. Accepte une émotion hors catalogue via un "
                "gabarit générique, la saisie étant alors neutralisée."),
            domain='writing',
            source='agents/createur.py:_EMOTION_DIRECTIVES',
            accepts_free_text=True,
            solves=(
                "Orienter l'écriture vers un ressenti précis chez le lecteur, "
                "avec des leviers concrets plutôt qu'une consigne abstraite."),
            when_to_use=(
                "Quand une émotion cible est choisie (puce prédéfinie ou texte "
                "libre) pour la génération de contenu."),
            required_info=('emotion',),
            methodology_summary=(
                "15 émotions cataloguées avec leur bloc de directives calibré ; "
                "toute émotion hors catalogue reçoit un gabarit générique qui "
                "l'oriente sans prétendre la maîtriser."),
            limitations=(
                "Le gabarit générique est un repli, pas une méthode : "
                "`SkillFragment.known` reste faux pour une émotion libre."),
            output_format="Bloc de texte à injecter tel quel dans le prompt système.",
        ),
        catalog=_EMOTION_DIRECTIVES,
        normalizer=_normalize_emotion_key,
        fallback=_free_emotion_directive,
    )


def _content_structure_skill() -> CatalogSkill:
    from agents.createur import _FORMAT_LABEL, _SYSTEM_PROMPTS

    def _normalize_format(requested: str) -> str:
        # Reproduit exactement `fmt_key` tel que calculé aux deux sites
        # d'appel (agents/createur.py:1029, 1226) : un contenu vide devient
        # 'hooks' *avant* la normalisation, pas après.
        return (requested or 'hooks').strip().lower().replace('-', '_').replace(' ', '_')

    formats_lisibles = ', '.join(f"{k} ({v})" for k, v in sorted(_FORMAT_LABEL.items()))
    return CatalogSkill(
        spec=SkillSpec(
            id='writing.content_structure',
            name="Structures de contenu",
            description=(
                "Impose la structure et le contrat de sortie JSON propres à "
                "chaque format (hook, script, post, email…) — la charpente "
                "d'un contenu, pas son style."),
            domain='writing',
            source='agents/createur.py:_SYSTEM_PROMPTS',
            accepts_free_text=False,
            solves=(
                "Produire un contenu dans la structure exacte attendue par le "
                "format demandé — séquence obligatoire et schéma JSON de "
                "sortie inclus dans la méthodologie elle-même."),
            when_to_use="Toujours, en tête du prompt système du Créateur.",
            required_info=('content_type',),
            methodology_summary=(
                f"12 formats + 4 alias, chacun avec sa propre séquence "
                f"obligatoire et son schéma JSON de sortie : {formats_lisibles}."),
            limitations=(
                "Un format non reconnu se rabat silencieusement sur 'hooks' — "
                "comportement historique conservé, pas une omission : "
                "`SkillFragment.known` reste faux dans ce cas (origin='default')."),
            output_format=(
                "Prompt système complet incluant le schéma JSON attendu — "
                "varie par format, voir chaque entrée du catalogue."),
        ),
        catalog=_SYSTEM_PROMPTS,
        normalizer=_normalize_format,
        default_key='hooks',
    )


def register_all() -> None:
    registry.register(_tone_skill())
    registry.register(_emotion_skill())
    registry.register(_content_structure_skill())
