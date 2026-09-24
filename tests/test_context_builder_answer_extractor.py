# ═══════════════════════════════════════════════════════════════════════════
# Régression : `_EXTRACT_SYSTEM` a été supprimé par accident dans le commit
# bb17f4c (renommage _call_mistral → _call_llm), qui a gardé la référence à la
# ligne d'appel sans garder sa définition. Le NameError qui en résultait était
# avalé par le `except Exception` de la boucle de retry — extract_answer()
# renvoyait donc {"extracted": {}, "rejected_vague": []} sur CHAQUE message,
# quelle que soit sa précision, dès qu'il ne s'agissait pas de la toute
# première réponse de l'entretien (laquelle passe par extract_answer_freeform,
# resté correct). Symptôme observé en conditions réelles : le Stratège
# reposait indéfiniment la même question de la dimension "identity".
#
# Ces tests ne appellent jamais un vrai modèle : _call_llm est simulé, mais
# la référence à _EXTRACT_SYSTEM à l'endroit de l'appel est évaluée avant que
# Python n'invoque la fonction simulée — un _EXTRACT_SYSTEM manquant ferait
# donc échouer ces tests avec un NameError, exactement comme en production.
# ═══════════════════════════════════════════════════════════════════════════
import json

from agents.context_builder import answer_extractor as ae


def test_extract_system_est_defini():
    """Garde-fou direct : sans cette constante, tout appel à extract_answer()
    lève un NameError silencieusement avalé par la boucle de retry."""
    assert isinstance(ae._EXTRACT_SYSTEM, str) and ae._EXTRACT_SYSTEM.strip()


def test_extract_answer_extrait_les_champs_de_la_dimension(monkeypatch):
    monkeypatch.setattr(ae, '_call_llm', lambda *a, **k: json.dumps({
        'offer': 'Formation présentielle 2 jours + suivi email 30 jours',
        'target': 'Dirigeants de PME de 20 à 200 salariés',
        'format': 'Vente directe après un webinaire gratuit',
    }))
    result = ae.extract_answer('identity', 'peu importe ici, _call_llm est simulé', {})
    assert result['extracted'] == {
        'offer': 'Formation présentielle 2 jours + suivi email 30 jours',
        'target': 'Dirigeants de PME de 20 à 200 salariés',
        'format': 'Vente directe après un webinaire gratuit',
    }
    assert result['rejected_vague'] == []


def test_extract_answer_dimension_inconnue_ne_leve_pas():
    result = ae.extract_answer('dimension_qui_n_existe_pas', 'texte', {})
    assert result == {'extracted': {}, 'rejected_vague': [], 'failed': False}


def test_extract_answer_freeform_reste_correct(monkeypatch):
    """extract_answer_freeform n'a jamais été touché par le bug — vérifié
    pour distinguer clairement les deux chemins dans ce module."""
    monkeypatch.setattr(ae, '_call_llm', lambda *a, **k: json.dumps({
        'offer': 'Formations IA pour PME',
    }))
    result = ae.extract_answer_freeform('Organisme de formation, 3 ans, 4 personnes.', {})
    assert result['extracted'] == {'offer': 'Formations IA pour PME'}
