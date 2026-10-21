"""Le pipeline du Psychologue passe bien par les outils du registre.

`analyze_comments` a été rebranché sur trois outils déterministes. Le risque
introduit par ce rebranchement n'est pas le calcul lui-même (prouvé identique
dans test_tool_equivalence) mais le *câblage* : une sortie nommée mal
déballée donnerait des KPIs et une distribution intervertis, sans erreur.
Ce test fait tourner le vrai pipeline, IA neutralisée.
"""

import core.analyzer as analyzer
import tools as tools_pkg


COMMENTAIRES = [
    {"text": "Merci, ça m'a débloqué sur mon offre.", "likes": 30},
    {"text": "Pas convaincu, tu simplifies trop le sujet.", "likes": 5},
    {"text": "Combien de temps avant les premiers résultats ?", "likes": 12},
    {"text": "Le tarif me freine vraiment.", "likes": 9},
    {"text": "Excellent, je m'abonne.", "likes": 55},
]


def _sans_ia(monkeypatch):
    """Neutralise l'IA et le NLP lourd : ce test porte sur le câblage des
    outils déterministes, pas sur la qualité de l'analyse. Le LLM renvoie un
    JSON minimal valide — un texte vide ferait échouer le parseur, ce qui
    masquerait ce qu'on cherche à vérifier."""
    monkeypatch.setattr(analyzer, "call_llm", lambda *a, **k: '{"placeholder": true}')
    monkeypatch.setattr(analyzer, "_NLP_AVAILABLE", False)


def test_le_pipeline_produit_kpis_et_distribution_non_intervertis(
        monkeypatch, deterministic_vader):
    _sans_ia(monkeypatch)
    resultat = analyzer.analyze_comments(COMMENTAIRES, title="Structurer son offre")

    kpis = resultat["kpis"]
    distribution = resultat["distribution"]

    attendu = tools_pkg.registry.get("audience.compute_kpis").run(
        comments=COMMENTAIRES,
        scores=[c["score"] for c in tools_pkg.registry.get(
            "audience.score_comments").run(
                comments=COMMENTAIRES, nlp_data=None,
                title="Structurer son offre")],
        title="Structurer son offre")

    assert kpis == attendu["kpis"]
    assert distribution == attendu["distribution"]
    assert kpis != distribution  # sinon la comparaison ci-dessus ne prouve rien


def test_le_pipeline_produit_un_dashboard_coherent(
        monkeypatch, deterministic_vader):
    _sans_ia(monkeypatch)
    resultat = analyzer.analyze_comments(COMMENTAIRES, title="Structurer son offre")
    dashboard = resultat["dashboard"]
    assert dashboard["total_comments"] == len(COMMENTAIRES)
    assert "dominant_emotion" in dashboard
