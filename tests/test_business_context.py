"""Source de vérité du contexte business.

Trois magasins ont coexisté : des fichiers JSON à la racine (morts), un fichier
par utilisateur (`data/profiles/`), et la table de l'Entretien stratégique
(`gabriel_context_fields`) — cette dernière étant désignée « source de vérité »
dans les commentaires du code.

Deux défauts en découlaient :
  1. l'Entretien stratégique nomme ses champs autrement (`activity` vs
     `activite`). Les lire sans les traduire renvoyait des valeurs vides : les
     agents croyaient le contexte absent alors qu'il était rempli ;
  2. l'orchestrateur lisait l'ancien magasin, jamais la source de vérité.
"""

import app


CB_FIELDS = {
    "user_role": "fondateur",
    "activity": "conseil en IA",
    "priority_offer": "accompagnement 3 mois",
    "target_audience": "dirigeants de PME",
    "business_model": "abonnement",
    "current_results": "12 clients",
    "main_objectives": "doubler le CA",
}


class TestTraductionDesChamps:
    def test_les_champs_de_l_entretien_sont_traduits(self, monkeypatch):
        """Sans traduction, un contexte pourtant complet apparaît vide."""
        monkeypatch.setattr(app._db, "get_context_fields", lambda uid: dict(CB_FIELDS))
        resolved = app._resolve_business_context({}, "user-1")

        assert resolved.get("activite") == "conseil en IA"
        assert resolved.get("offre") == "accompagnement 3 mois"
        assert resolved.get("cible") == "dirigeants de PME"

    def test_un_contexte_complet_n_est_pas_signale_comme_manquant(self, monkeypatch):
        """C'est ce qui bloquait l'utilisateur : sept champs déclarés manquants
        alors que l'entretien les avait tous collectés."""
        monkeypatch.setattr(app._db, "get_context_fields", lambda uid: dict(CB_FIELDS))
        resolved = app._resolve_business_context({}, "user-1")

        assert app._missing_required_business_fields(resolved) == []

    def test_le_contexte_est_reellement_lisible_par_les_agents(self, monkeypatch):
        """Le bloc injecté dans les prompts doit contenir les valeurs, pas des vides."""
        monkeypatch.setattr(app._db, "get_context_fields", lambda uid: dict(CB_FIELDS))
        bloc = app._format_brain_context(app._resolve_business_context({}, "user-1"))

        assert "conseil en IA" in bloc
        assert "dirigeants de PME" in bloc


class TestOrdreDePriorite:
    def test_le_corps_de_requete_prime_sur_tout(self, monkeypatch):
        monkeypatch.setattr(app._db, "get_context_fields", lambda uid: dict(CB_FIELDS))
        resolved = app._resolve_business_context(
            {"business_context": {"activite": "fourni explicitement"}}, "user-1")
        assert resolved["activite"] == "fourni explicitement"

    def test_repli_sur_l_ancien_magasin_si_l_entretien_est_vide(self, monkeypatch):
        """Les comptes antérieurs à l'Entretien stratégique doivent continuer
        de fonctionner."""
        monkeypatch.setattr(app._db, "get_context_fields", lambda uid: {})
        monkeypatch.setattr(app, "_get_user_profile", lambda uid: {"activite": "ancien profil"})
        resolved = app._resolve_business_context({}, "user-1")
        assert resolved["activite"] == "ancien profil"

    def test_aucune_source_ne_casse_rien(self, monkeypatch):
        monkeypatch.setattr(app._db, "get_context_fields", lambda uid: {})
        monkeypatch.setattr(app, "_get_user_profile", lambda uid: {})
        assert app._resolve_business_context({}, "user-1") == {}
