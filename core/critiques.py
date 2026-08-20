"""Les examens critiques déclarés de Gabriel.

Deux fiches, deux politiques d'échec délibérément opposées — celles déjà en
place, reproduites telles quelles :

* **Stratège** : sans critique, la stratégie part simplement sans relecture.
  L'erreur remonte à l'appelant, qui l'absorbe. Rien ne doit se substituer à un
  avis qui n'a pas été rendu.
* **Créateur** : la critique pilote la boucle d'amélioration. Sans elle, il
  faut un objet neutre, sinon le texte n'est jamais livré à l'utilisateur.
"""

from core.critic import CritiqueSpec, registry


def _normalize_creation(data: dict) -> dict:
    """Complète la critique du Créateur comme le faisait `dialectic.run`.

    Le verdict par défaut se déduit des faiblesses trouvées : un texte sans
    faiblesse relevée est livrable ; sinon il reste à améliorer.
    """
    data = dict(data)
    data.setdefault('faiblesses', [])
    data.setdefault('verdict',
                    'a_ameliorer' if data['faiblesses'] else 'livrable')
    return data


STRATEGY_CRITIQUE = CritiqueSpec(
    id='critique.strategy',
    name='Revue contrarienne de stratégie',
    domain='strategy',
    expected_keys=('point_faible_principal', 'angle_contrarien',
                   'risque_non_couvert', 'ajustement_recommande',
                   'confidence_score_independant', 'verdict'),
    passing_verdicts=('solide',),
    fallback=None,          # l'appelant décide : la stratégie part sans relecture
    log_prefix='STRATÈGE',
)

CREATION_CRITIQUE = CritiqueSpec(
    id='critique.creation',
    name='Critique adverse de contenu',
    domain='writing',
    expected_keys=('faiblesses', 'risque_principal', 'verdict'),
    passing_verdicts=('livrable',),
    fallback={'faiblesses': [], 'risque_principal': '', 'verdict': 'livrable'},
    normalize=_normalize_creation,
    log_prefix='CREATION/dialectic',
)


def register_all() -> None:
    registry.register(STRATEGY_CRITIQUE)
    registry.register(CREATION_CRITIQUE)


register_all()
