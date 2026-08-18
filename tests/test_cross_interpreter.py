"""L'interprétation LLM Cross ne doit jamais exposer une citation inventée.

Le LLM reçoit un pack de preuves borné (insight_id, source_id mesurés). Rien
ne l'empêche techniquement de citer une référence qui n'existe pas — ces
tests vérifient que ces citations sont retirées avant d'atteindre
l'utilisateur, plutôt qu'acceptées avec un statut "completed" trompeur.
"""

import json

from core.cross_analysis import build_cross_analysis, normalize_cross_sources
from core.cross_interpreter import build_counter_evidence_pack, interpret_cross_analysis, run_dialectic_review


def _cross_result():
    source_a, source_b = normalize_cross_sources([
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'label': 'Audience A'},
        {'url': 'https://youtu.be/9bZkp7q19f0', 'label': 'Audience B'},
    ])
    source_analyses = [
        {
            'source_id': source_a['source_id'],
            'comment_stats': {'total_comments': 40, 'confidence_score': 80},
            'emotions': [{'label': 'Espoir', 'weight': 60}],
        },
        {
            'source_id': source_b['source_id'],
            'comment_stats': {'total_comments': 35, 'confidence_score': 75},
            'emotions': [{'label': 'Espoir', 'weight': 55}],
        },
    ]
    return build_cross_analysis(source_analyses), source_a['source_id'], source_b['source_id']


def _cross_result_with_divergence():
    """Deux sources qui convergent sur l'émotion mais divergent nettement sur
    un thème (écart d'intensité ≥ 25 points) — de quoi produire une vraie
    divergence mesurée, pas seulement une convergence."""
    source_a, source_b = normalize_cross_sources([
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'label': 'Audience A'},
        {'url': 'https://youtu.be/9bZkp7q19f0', 'label': 'Audience B'},
    ])
    source_analyses = [
        {
            'source_id': source_a['source_id'],
            'comment_stats': {'total_comments': 40, 'confidence_score': 80},
            'emotions': [{'label': 'Espoir', 'score': 60}],
            'themes': [{'label': 'Accompagnement', 'score': 80}],
        },
        {
            'source_id': source_b['source_id'],
            'comment_stats': {'total_comments': 35, 'confidence_score': 75},
            'emotions': [{'label': 'Espoir', 'score': 55}],
            'themes': [{'label': 'Accompagnement', 'score': 20}],
        },
    ]
    return build_cross_analysis(source_analyses), source_a['source_id'], source_b['source_id']


class TestCounterEvidencePack:

    def test_excludes_convergences_but_keeps_divergences_and_count(self):
        cross_result, _a, _b = _cross_result_with_divergence()
        pack = build_counter_evidence_pack(cross_result)

        assert 'convergences' not in pack
        assert pack['divergences'], "la divergence mesurée (Accompagnement) doit apparaître"
        assert pack['counter_evidence_item_count'] >= 1

    def test_zero_counter_evidence_when_sources_only_converge(self):
        cross_result, _a, _b = _cross_result()
        pack = build_counter_evidence_pack(cross_result)
        assert pack['counter_evidence_item_count'] == 0


class TestDialecticReviewCoverage:

    def test_prompt_carries_divergences_not_convergences(self, monkeypatch):
        cross_result, _a, _b = _cross_result_with_divergence()
        captured = {}

        def fake_call_claude(prompt, max_tokens=2200, fast=False, label=""):
            captured['prompt'] = prompt
            return json.dumps({
                'status': 'completed', 'challenges': [], 'alternative_hypotheses': [],
                'retained_conclusion': '...', 'confidence_level': 'exploratory',
            })

        monkeypatch.setattr('core.cross_interpreter.call_llm', fake_call_claude)
        run_dialectic_review(cross_result, {})

        assert 'Accompagnement' in captured['prompt']  # la divergence est bien transmise

    def test_empty_critique_with_available_counter_evidence_is_flagged_unengaged(self, monkeypatch):
        """Il existe une vraie divergence mesurée, mais le LLM ne soulève
        aucune contestation : le résultat doit le rendre visible plutôt que
        de présenter silencieusement une critique vide comme équivalente."""
        cross_result, _a, _b = _cross_result_with_divergence()
        monkeypatch.setattr('core.cross_interpreter.call_llm', lambda *a, **k: json.dumps({
            'status': 'completed', 'challenges': [], 'alternative_hypotheses': [],
            'retained_conclusion': '...', 'confidence_level': 'exploratory',
        }))

        review = run_dialectic_review(cross_result, {})

        assert review['coverage']['counter_evidence_available'] >= 1
        assert review['coverage']['challenges_raised'] == 0
        assert review['coverage']['engaged_available_counter_evidence'] is False

    def test_no_counter_evidence_available_is_not_flagged_as_unengaged(self, monkeypatch):
        """Rien à contredire : une critique vide est légitime, pas suspecte."""
        cross_result, _a, _b = _cross_result()
        monkeypatch.setattr('core.cross_interpreter.call_llm', lambda *a, **k: json.dumps({
            'status': 'completed', 'challenges': [], 'alternative_hypotheses': [],
            'retained_conclusion': '...', 'confidence_level': 'exploratory',
        }))

        review = run_dialectic_review(cross_result, {})

        assert review['coverage']['counter_evidence_available'] == 0
        assert review['coverage']['engaged_available_counter_evidence'] is True


def test_interpretation_drops_a_persona_built_only_on_unknown_sources(monkeypatch):
    cross_result, source_a_id, source_b_id = _cross_result()
    real_insight_id = next(iter(cross_result['evidence_index']))

    fake_response = json.dumps({
        "executive_summary": {"text": "Deux audiences partagent une forme d'espoir.", "confidence_level": "moderate"},
        "common_psychological_core": {
            "observation": "Espoir partagé", "interpretation": "Lecture nuancée",
            "confidence_level": "moderate", "source_ids": [source_a_id, "src_invented_ghost"],
        },
        "convergence_interpretations": [
            # Une affirmation ancrée dans une preuve réelle : doit survivre.
            {"insight_id": real_insight_id, "interpretation": "Espoir partagé et mesuré.",
             "confidence_level": "moderate", "source_ids": [source_a_id, source_b_id]},
            # Un insight_id qui n'existe dans aucune preuve mesurée : doit être rejeté.
            {"insight_id": "cross:emotions:invented-signal", "interpretation": "Signal halluciné.",
             "confidence_level": "strong", "source_ids": [source_a_id]},
        ],
        "divergence_interpretations": [],
        "cross_personas": [
            # Persona entièrement fondé sur une source inconnue — l'exemple exact de l'audit.
            {"name": "Persona fantôme", "description": "N'existe dans aucune source.",
             "source_ids": ["unknown"], "signals": ["mystère"], "confidence_level": "strong"},
            # Persona mêlant une vraie source et une source inventée : doit survivre, filtré.
            {"name": "Persona partiellement fondé", "description": "Appuyé sur une vraie audience.",
             "source_ids": [source_a_id, "src_invented_ghost"], "signals": ["espoir"],
             "confidence_level": "moderate"},
        ],
    })
    monkeypatch.setattr('core.cross_interpreter.call_llm', lambda *a, **k: fake_response)

    interpretation = interpret_cross_analysis(cross_result)

    assert interpretation['status'] == 'completed'

    # La citation ancrée dans une vraie preuve survit intacte.
    kept_convergences = interpretation['convergence_interpretations']
    assert len(kept_convergences) == 1
    assert kept_convergences[0]['insight_id'] == real_insight_id
    assert set(kept_convergences[0]['source_ids']) == {source_a_id, source_b_id}

    # L'insight_id halluciné n'apparaît nulle part dans la sortie.
    assert interpretation['validation']['convergence_rejected'] == 1
    assert all(item['insight_id'] != 'cross:emotions:invented-signal' for item in kept_convergences)

    # Le persona 100% inventé a disparu ; l'autre survit mais sans la source fantôme.
    personas = interpretation['cross_personas']
    assert len(personas) == 1
    assert personas[0]['name'] == 'Persona partiellement fondé'
    assert personas[0]['source_ids'] == [source_a_id]
    assert 'src_invented_ghost' not in personas[0]['source_ids']
    assert interpretation['validation']['cross_personas_rejected'] == 1

    # Le noyau commun perd sa référence inventée mais garde la vraie.
    assert interpretation['common_psychological_core']['source_ids'] == [source_a_id]


def test_interpretation_survives_a_response_naming_zero_real_sources(monkeypatch):
    """Cas dégradé : tout ce que le LLM cite est inventé. Le statut reste
    'completed' (le JSON était valide), mais chaque section grounded est vide —
    jamais une conclusion fantôme présentée comme fiable."""
    cross_result, _source_a_id, _source_b_id = _cross_result()
    fake_response = json.dumps({
        "executive_summary": {"text": "Résumé.", "confidence_level": "nonsense-level"},
        "common_psychological_core": {"source_ids": ["ghost-1", "ghost-2"]},
        "convergence_interpretations": [
            {"insight_id": "cross:emotions:ghost", "interpretation": "...", "source_ids": ["ghost-1"]}
        ],
        "divergence_interpretations": [],
        "cross_personas": [
            {"name": "Fantôme", "description": "...", "source_ids": ["ghost-1"], "confidence_level": "strong"}
        ],
    })
    monkeypatch.setattr('core.cross_interpreter.call_llm', lambda *a, **k: fake_response)

    interpretation = interpret_cross_analysis(cross_result)

    assert interpretation['convergence_interpretations'] == []
    assert interpretation['cross_personas'] == []
    assert interpretation['common_psychological_core']['source_ids'] == []
    # Un niveau de confiance hors énumération ne doit jamais fuiter tel quel.
    assert interpretation['executive_summary']['confidence_level'] == 'exploratory'
    assert interpretation['validation'] == {
        'convergence_rejected': 1, 'divergence_rejected': 0, 'cross_personas_rejected': 1,
    }


def test_dialectic_review_drops_challenges_citing_unknown_sources(monkeypatch):
    cross_result, source_a_id, _source_b_id = _cross_result()
    fake_response = json.dumps({
        "status": "completed",
        "challenges": [
            {"claim": "Le prix explique tout.", "counter_evidence": "Preuve réelle.", "source_ids": [source_a_id]},
            {"claim": "Hypothèse non sourcée.", "counter_evidence": "...", "source_ids": ["ghost"]},
        ],
        "alternative_hypotheses": ["La valeur perçue plutôt que le prix."],
        "retained_conclusion": "Conclusion nuancée.",
        "confidence_level": "moderate",
    })
    monkeypatch.setattr('core.cross_interpreter.call_llm', lambda *a, **k: fake_response)

    review = run_dialectic_review(cross_result, {})

    assert review['status'] == 'completed'
    assert len(review['challenges']) == 1
    assert review['challenges'][0]['source_ids'] == [source_a_id]
    assert review['validation']['challenges_rejected'] == 1
