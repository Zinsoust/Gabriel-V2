"""Contrat du registre d'outils.

Le registre existe pour qu'un futur planificateur puisse raisonner sur des
capacités réelles : savoir ce qui existe, ce que ça demande, ce que ça produit,
ce qui est parallélisable et qui a le droit de l'utiliser.
"""

import pytest

import tools as tools_pkg
from tools import FunctionTool, ToolInput, ToolInputError, ToolSpec
from tools.registry import ToolNotAllowed, ToolNotFound, ToolRegistry


def _spec(tool_id="test.echo", **kwargs):
    defaults = dict(
        id=tool_id, name="Écho", description="Renvoie ce qu'on lui donne",
        category="test",
        inputs=(ToolInput("valeur", "La valeur à renvoyer"),
                ToolInput("suffixe", "Ajout facultatif", required=False)),
        output="La valeur, éventuellement suffixée",
    )
    defaults.update(kwargs)
    return ToolSpec(**defaults)


def _echo(valeur, suffixe=""):
    return f"{valeur}{suffixe}"


class TestValidationDesEntrees:
    def test_une_entree_requise_manquante_est_refusee_avec_un_message_clair(self):
        """Sans cette garde, l'absence remonterait en KeyError depuis le fond
        de l'implémentation — illisible pour qui appelle l'outil."""
        outil = FunctionTool(_spec(), _echo)
        with pytest.raises(ToolInputError, match="valeur"):
            outil.run()

    def test_une_entree_inconnue_est_refusee(self):
        """Une faute de frappe sur un nom de paramètre ferait sinon tourner
        l'outil sur ses valeurs par défaut, sans que personne ne le remarque."""
        outil = FunctionTool(_spec(), _echo)
        with pytest.raises(ToolInputError, match="sufixe"):
            outil.run(valeur="a", sufixe="!")

    def test_les_entrees_facultatives_restent_facultatives(self):
        outil = FunctionTool(_spec(), _echo)
        assert outil.run(valeur="a") == "a"
        assert outil.run(valeur="a", suffixe="!") == "a!"


class TestPermissions:
    def test_un_outil_sans_liste_blanche_est_ouvert_a_tous(self):
        assert _spec().is_allowed_for("psychologue") is True

    def test_une_liste_blanche_restreint_reellement(self):
        spec = _spec(allowed_agents=("psychologue",))
        assert spec.is_allowed_for("psychologue") is True
        assert spec.is_allowed_for("createur") is False

    def test_le_registre_refuse_un_agent_non_autorise(self):
        r = ToolRegistry()
        r.register(FunctionTool(_spec(allowed_agents=("psychologue",)), _echo))
        r.get("test.echo", agent="psychologue")
        with pytest.raises(ToolNotAllowed):
            r.get("test.echo", agent="createur")

    def test_outil_inconnu_et_outil_interdit_sont_deux_erreurs_distinctes(self):
        """Les confondre empêcherait de diagnostiquer une permission oubliée."""
        r = ToolRegistry()
        r.register(FunctionTool(_spec(allowed_agents=("psychologue",)), _echo))
        with pytest.raises(ToolNotFound):
            r.get("test.inexistant", agent="psychologue")
        with pytest.raises(ToolNotAllowed):
            r.get("test.echo", agent="createur")


class TestRegistre:
    def test_un_identifiant_en_double_est_refuse(self):
        """Deux implémentations sous un même identifiant se masqueraient
        silencieusement — le registre perdrait sa raison d'être."""
        r = ToolRegistry()
        r.register(FunctionTool(_spec(), _echo))
        with pytest.raises(ValueError, match="déjà enregistré"):
            r.register(FunctionTool(_spec(), _echo))

    def test_l_erreur_d_outil_inconnu_liste_les_outils_connus(self):
        r = ToolRegistry()
        r.register(FunctionTool(_spec(), _echo))
        with pytest.raises(ToolNotFound, match="test.echo"):
            r.get("test.absent")

    def test_filtrage_par_agent_et_par_categorie(self):
        r = ToolRegistry()
        r.register(FunctionTool(_spec("a.un", category="a"), _echo))
        r.register(FunctionTool(_spec("b.un", category="b",
                                      allowed_agents=("stratege",)), _echo))
        assert len(r.all()) == 2
        assert [t.spec.id for t in r.for_agent("createur")] == ["a.un"]
        assert [t.spec.id for t in r.by_category("b")] == ["b.un"]
        assert r.categories() == ("a", "b")


class TestCatalogueLisibleParLeCore:
    """Ce que le futur Planner lira pour construire un plan."""

    def test_le_catalogue_expose_ce_qu_il_faut_pour_raisonner(self):
        description = tools_pkg.registry.describe()[0]
        for champ in ("id", "name", "description", "inputs", "output",
                      "deterministic", "parallel_safe", "allowed_agents"):
            assert champ in description, champ

    def test_le_catalogue_se_restreint_a_un_agent(self):
        r = ToolRegistry()
        r.register(FunctionTool(_spec("a.un"), _echo))
        r.register(FunctionTool(_spec("b.un", allowed_agents=("stratege",)), _echo))
        assert [d["id"] for d in r.describe(agent="createur")] == ["a.un"]

    def test_les_entrees_requises_sont_distinguees_des_facultatives(self):
        entrees = {i["name"]: i["required"] for i in _spec().describe()["inputs"]}
        assert entrees == {"valeur": True, "suffixe": False}


class TestOutilsDAudienceEnregistres:
    def test_les_trois_outils_deterministes_sont_disponibles(self):
        for tool_id in ("audience.score_comments", "audience.compute_kpis",
                        "audience.compute_dashboard"):
            assert tool_id in tools_pkg.registry

    def test_ils_sont_declares_deterministes_et_parallelisables(self):
        """Cette déclaration est ce qui autorisera le graphe d'exécution à les
        lancer ensemble — une erreur ici produirait des résultats corrompus."""
        for outil in tools_pkg.registry.by_category("audience"):
            assert outil.spec.deterministic is True
            assert outil.spec.parallel_safe is True
            assert outil.spec.timeout_s is None  # calcul local, pas de réseau
