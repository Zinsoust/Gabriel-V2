"""core/analyzer.py — les personas individuels doivent être vérifiablement
ancrés dans des clusters mesurés, pas seulement le prétendre.

Avant ce correctif : le prompt affirmait "RÈGLE ABSOLUE : le persona doit
provenir d'un cluster mesuré" même quand aucun cluster n'existait (contexte
vide), et rien ne vérifiait après coup que le cluster_source / signaux_mesures
déclarés par le LLM correspondaient à un vrai cluster.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import core.analyzer as analyzer


CLUSTERS = [
    {'cluster_id': 0, 'pct': 62.0, 'size': 31, 'top_tokens': ['prix', 'cher', 'budget'], 'samples': ['x', 'y']},
    {'cluster_id': 1, 'pct': 38.0, 'size': 19, 'top_tokens': ['confiance', 'doute', 'peur'], 'samples': ['a', 'b']},
]


class TestGroundPersonaAgainstClusters:

    def test_no_clusters_available_is_flagged_not_hidden(self):
        persona = {'nom': 'Test', 'signaux_mesures': ['prix']}
        analyzer._ground_persona_against_clusters(persona, 'Cluster 0', clusters=[])
        assert persona['cluster_grounded'] is False
        assert persona['cluster_grounding_reason'] == 'aucun_cluster_mesure'

    def test_hybride_is_accepted_without_requiring_a_specific_cluster(self):
        persona = {'nom': 'Test'}
        analyzer._ground_persona_against_clusters(persona, 'hybride', CLUSTERS)
        assert persona['cluster_grounded'] == 'hybride'

    def test_unknown_cluster_source_is_flagged(self):
        persona = {'nom': 'Test', 'signaux_mesures': ['prix']}
        analyzer._ground_persona_against_clusters(persona, 'Cluster 9', CLUSTERS)
        assert persona['cluster_grounded'] is False
        assert persona['cluster_grounding_reason'] == 'cluster_source_inconnu'

    def test_real_cluster_with_matching_signals_is_grounded(self):
        persona = {'nom': 'Test', 'signaux_mesures': ['le prix', 'trop cher']}
        analyzer._ground_persona_against_clusters(persona, 'Cluster 0', CLUSTERS)
        assert persona['cluster_grounded'] is True
        assert 'cluster_grounding_reason' not in persona

    def test_real_cluster_but_invented_signals_is_flagged_not_silently_accepted(self):
        """L'exemple exact de l'audit : cluster_source valide, mais les
        signaux revendiqués n'existent dans aucun token mesuré du cluster."""
        persona = {'nom': 'Test', 'signaux_mesures': ['licorne', 'voyage sur mars']}
        analyzer._ground_persona_against_clusters(persona, 'Cluster 0', CLUSTERS)
        assert persona['cluster_grounded'] is False
        assert persona['cluster_grounding_reason'] == 'signaux_non_retrouves_dans_le_cluster'


class TestPersonaPromptHonesty:
    """Le prompt ne doit jamais affirmer une règle d'ancrage qu'il ne peut pas
    respecter — vérifié en capturant le prompt réellement envoyé au LLM."""

    def _run_with_nlp_data(self, monkeypatch, nlp_data):
        captured_prompts = []

        def fake_call_claude(prompt, max_tokens=3000, fast=False, label=""):
            captured_prompts.append(prompt)
            return '{"nom": "Test", "mission_cachee": "x", "besoin_d_appartenance": "x", "desir_de_legacy": "x", "tension_existentielle": "x"}'

        monkeypatch.setattr(analyzer, 'call_llm', fake_call_claude)
        comment = {'text': 'Un commentaire quelconque.', 'likes': 0}
        analyzer._analyze_personas(
            filtered=[(comment, 0.5)],
            brain_context='',
            main_data={'emotions': {}, 'psychologie': {}, 'aspirations': {}, 'identitaire': {}},
            kpis={'polarisation': {'score': 0}},
            nlp_data=nlp_data,
        )
        return captured_prompts

    def test_no_cluster_data_drops_the_false_absolute_rule(self, monkeypatch):
        prompts = self._run_with_nlp_data(monkeypatch, nlp_data=None)
        assert prompts
        for prompt in prompts:
            assert "RÈGLE ABSOLUE : le persona doit provenir d un cluster mesuré" not in prompt
            assert "Aucun cluster comportemental mesuré n'est disponible" in prompt

    def test_real_cluster_data_keeps_the_absolute_rule(self, monkeypatch):
        prompts = self._run_with_nlp_data(monkeypatch, nlp_data={'cluster_summary': CLUSTERS})
        assert prompts
        for prompt in prompts:
            assert "RÈGLE ABSOLUE : le persona doit provenir d un cluster mesuré" in prompt
