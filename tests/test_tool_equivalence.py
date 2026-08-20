"""Équivalence stricte outil / fonction d'origine.

L'extraction en outils ne doit rien changer aux résultats. Ces tests comparent
la sortie de chaque outil à celle de la fonction historique sur les mêmes
entrées — c'est la seule preuve qui autorise à rebrancher l'agent dessus.
"""

import core.analyzer as analyzer
import tools as tools_pkg


COMMENTAIRES = [
    {"text": "Cette vidéo m'a vraiment aidé, merci beaucoup !", "likes": 42},
    {"text": "Je ne suis pas d'accord, c'est trop simpliste.", "likes": 7},
    {"text": "Quelqu'un a testé la méthode ? ça marche vraiment ?", "likes": 3},
    {"text": "Bof.", "likes": 0},
    {"text": "Contenu incroyable, ça change tout pour mon business.", "likes": 88},
    {"text": "https://spam.example.com", "likes": 0},
    {"text": "Le prix reste un frein pour moi, honnêtement.", "likes": 15},
]
TITRE = "Comment structurer son offre"


class TestEquivalence:
    def test_le_scoring_donne_le_meme_resultat(self):
        attendu = analyzer.score_comments_math(COMMENTAIRES, None, TITRE)
        obtenu = tools_pkg.registry.get("audience.score_comments").run(
            comments=COMMENTAIRES, nlp_data=None, title=TITRE)
        assert obtenu == attendu

    def test_les_kpis_donnent_le_meme_resultat(self):
        scores = [c["score"] for c in analyzer.score_comments_math(COMMENTAIRES, None, TITRE)]
        kpis_attendus, distribution_attendue = analyzer.calculate_math_kpis(
            COMMENTAIRES, scores, TITRE)

        obtenu = tools_pkg.registry.get("audience.compute_kpis").run(
            comments=COMMENTAIRES, scores=scores, title=TITRE)

        assert obtenu["kpis"] == kpis_attendus
        assert obtenu["distribution"] == distribution_attendue

    def test_le_tableau_de_bord_donne_le_meme_resultat(self):
        scored = analyzer.score_comments_math(COMMENTAIRES, None, TITRE)
        attendu = analyzer._compute_dashboard(scored, None, len(COMMENTAIRES), TITRE)
        obtenu = tools_pkg.registry.get("audience.compute_dashboard").run(
            scored_comments=scored, nlp_data=None,
            total_comments=len(COMMENTAIRES), title=TITRE)
        assert obtenu == attendu


class TestSortieNommee:
    def test_les_kpis_sont_rendus_nommes_et_non_en_tuple(self):
        """La fonction historique rend un tuple : l'appelant doit connaître
        l'ordre. Un plan généré ne peut pas le deviner — l'outil nomme donc
        ses deux sorties."""
        scores = [0.5, -0.4, 0.1]
        obtenu = tools_pkg.registry.get("audience.compute_kpis").run(
            comments=COMMENTAIRES[:3], scores=scores)
        assert set(obtenu) == {"kpis", "distribution"}


class TestCasLimites:
    def test_aucun_commentaire_ne_casse_rien(self):
        assert tools_pkg.registry.get("audience.score_comments").run(comments=[]) == []
        kpis = tools_pkg.registry.get("audience.compute_kpis").run(comments=[], scores=[])
        assert kpis == {"kpis": {}, "distribution": {}}

    def test_un_tableau_de_bord_sans_donnee_reste_exploitable(self):
        """Un dashboard vide doit rester lisible par l'affichage plutôt que
        de lever : une analyse sans commentaire qualifié reste un résultat."""
        resultat = tools_pkg.registry.get("audience.compute_dashboard").run(
            scored_comments=[], total_comments=0)
        assert resultat["total_comments"] == 0
        assert resultat["qualified_comments"] == 0

    def test_les_entrees_facultatives_le_sont_vraiment(self):
        """nlp_data absent = le pipeline NLP n'a pas tourné ; le scoring doit
        se rabattre sur ses seuls signaux lexicaux."""
        resultat = tools_pkg.registry.get("audience.score_comments").run(
            comments=COMMENTAIRES)
        assert len(resultat) == len(COMMENTAIRES)
