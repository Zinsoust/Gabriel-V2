"""Voix humaine / anti-IA du Créateur.

Seule méthodologie de Gabriel implémentée **deux fois** avant ce chantier :
une fois en consigne de rédaction (le bloc injecté au modèle), une fois en
validateur (la regex de `content_quality.check`). Les deux ont divergé — le
Skill le déclare au lieu de le masquer, et `allowed_tools` relie la méthode
à son vérificateur.
"""

from skills.base import CatalogSkill, SkillSpec
from skills.registry import registry


def _human_voice_skill() -> CatalogSkill:
    from agents.createur import _HUMAN_VOICE
    return CatalogSkill(
        spec=SkillSpec(
            id='writing.human_voice',
            name='Voix humaine (anti-IA)',
            description=(
                "Interdit les formules qui trahissent l'écriture machine et "
                "impose d'écrire depuis la position d'une personne réelle "
                "s'adressant à une seule autre, pas d'une IA à « une "
                "audience »."),
            domain='writing',
            source='agents/createur.py:_HUMAN_VOICE',
            accepts_free_text=False,
            solves=(
                "Empêche un contenu techniquement correct de sonner "
                "artificiel — le défaut le plus coûteux d'un texte généré, "
                "parce qu'il détruit la confiance sans produire d'erreur "
                "visible."),
            when_to_use=(
                "Systématiquement, pour toute génération de contenu du "
                "Créateur — il ne varie jamais selon le format ou la "
                "tonalité."),
            required_info=(),
            methodology_summary=(
                "Une liste de formules interdites (« il est temps de », "
                "« libérer ton potentiel », métaphores de voyage…), un test "
                "par phrase (« un humain dirait-il vraiment ça à un ami ? ») "
                "et une règle d'ancrage : utiliser les mots exacts de "
                "l'audience plutôt que des mots génériques."),
            allowed_tools=('content_quality.check',),
            limitations=(
                "La consigne et son validateur avaient divergé sur six "
                "interdictions. Trois sont désormais vérifiées — des formules "
                "d'ouverture (« bonjour à tous », « bienvenue sur », « nous "
                "vivons dans une époque ») mesurées à zéro faux positif. "
                "Trois restent hors du validateur, délibérément : "
                "« se transformer », « meilleure version » et les métaphores "
                "de voyage sont du vocabulaire marketing français courant — "
                "les détecter signalerait « le parcours client » ou « la "
                "meilleure version de ton offre » comme artificiels. L'écart "
                "restant est figé par des tests, des deux côtés."),
            output_format=(
                "Bloc de texte fixe à injecter dans le prompt, entre la "
                "discipline de tonalité et le brief de rédaction."),
        ),
        catalog={'createur': _HUMAN_VOICE},
        normalizer=lambda _requested: 'createur',
    )


def register_all() -> None:
    registry.register(_human_voice_skill())
