"""Contrat du registre d'agents.

Cette couche referme la boucle Tool → Skill → Agent. Son intérêt n'est pas de
lister des noms — `agents/__init__.py` le faisait déjà — mais de dire la
vérité sur ce que chaque agent sait réellement faire, et de refuser au
démarrage toute déclaration incohérente avec les deux autres registres.
"""

import pytest

from agents.catalog import registry
from agents.registry import (STATUS_AVAILABLE, STATUS_PLANNED,
                             STATUS_UNAVAILABLE, AgentNotFound, AgentRegistry,
                             AgentSpec, AgentUnavailable)
from skills import registry as skill_registry
from tools import registry as tool_registry


def _spec(agent_id='test.agent', **kw):
    base = dict(id=agent_id, name='Agent test', description='…')
    base.update(kw)
    return AgentSpec(**base)


class TestVeriteSurLesPointsDEntree:
    """`agents/__init__.py` présente les quatre agents comme interchangeables
    alors que deux d'entre eux lèvent une exception sur `run()`. Un
    planificateur qui s'y fierait appellerait `run()` et échouerait."""

    def test_le_createur_declare_son_vrai_point_d_entree(self):
        assert registry.spec('createur').entrypoint == 'generate_script_or_text'

    def test_les_agents_du_pipeline_declarent_run(self):
        for agent_id in ('psychologue', 'stratege'):
            assert registry.spec(agent_id).entrypoint == 'run'

    def test_un_agent_non_implemente_n_est_pas_annonce_utilisable(self):
        architecte = registry.spec('architecte')
        assert architecte.status == STATUS_PLANNED
        assert architecte.usable is False

    def test_charger_un_agent_non_utilisable_echoue_explicitement(self):
        """Plutôt que de renvoyer None, comme le faisait l'ancien chargement —
        l'appelant découvrait la panne bien plus loin, sur un AttributeError."""
        with pytest.raises(AgentUnavailable, match='architecte'):
            registry.resolve('architecte')


class TestCoherenceEntreLesTroisCouches:
    """L'apport central : une capacité déclarée mais inexistante est refusée au
    démarrage, pas au milieu d'une analyse payée par l'utilisateur."""

    def test_un_outil_inconnu_est_refuse_a_l_enregistrement(self):
        r = AgentRegistry(tool_registry=tool_registry, skill_registry=skill_registry)
        with pytest.raises(ValueError, match='outil inconnu'):
            r.register(_spec(tools=('audience.score_commentaires',)))  # faute de frappe

    def test_un_savoir_faire_inconnu_est_refuse_a_l_enregistrement(self):
        r = AgentRegistry(tool_registry=tool_registry, skill_registry=skill_registry)
        with pytest.raises(ValueError, match='savoir-faire inconnu'):
            r.register(_spec(skills=('writing.ton',)))

    def test_un_agent_ne_peut_pas_declarer_un_outil_qui_lui_est_interdit(self):
        """Les deux sens de la permission doivent concorder : sans cela, la
        liste blanche d'un outil serait contredite par la fiche de l'agent."""
        from tools import FunctionTool, ToolInput, ToolSpec
        from tools.registry import ToolRegistry

        outils = ToolRegistry()
        outils.register(FunctionTool(
            ToolSpec(id='prive.calcul', name='Calcul privé', description='…',
                     category='test', inputs=(ToolInput('x', 'x'),),
                     output='y', allowed_agents=('psychologue',)),
            lambda x: x))
        r = AgentRegistry(tool_registry=outils)
        r.register(_spec('psychologue', tools=('prive.calcul',)))  # autorisé
        with pytest.raises(ValueError, match='ne l.autorise pas'):
            r.register(_spec('createur', tools=('prive.calcul',)))

    def test_les_capacites_reellement_declarees_existent_toutes(self):
        """Vérification de bout en bout sur le vrai catalogue."""
        for agent in registry.all():
            for tool_id in agent.spec.tools:
                assert tool_id in tool_registry, f"{agent.spec.id} → {tool_id}"
            for skill_id in agent.spec.skills:
                assert skill_id in skill_registry, f"{agent.spec.id} → {skill_id}"


class TestContrainteProduitAccesDirect:
    """Règle constante du projet : chaque agent reste utilisable seul, sans
    passer par une orchestration. Elle cesse d'être une habitude pour devenir
    une propriété vérifiable."""

    def test_les_trois_agents_de_production_restent_joignables_seuls(self):
        joignables = {a.spec.id for a in registry.with_direct_access()}
        assert {'psychologue', 'stratege', 'createur'} <= joignables

    def test_chacun_declare_sa_route_directe(self):
        for agent_id in ('psychologue', 'stratege', 'createur'):
            assert registry.spec(agent_id).route == f'/{agent_id}'


class TestDependancesEntreAgents:
    def test_le_stratege_declare_avoir_besoin_du_psychologue(self):
        """`Stratege.run` lit ctx.get('psychologue') : un plan qui l'ignorerait
        produirait une stratégie sans matière, sans erreur visible."""
        assert 'psychologue' in registry.spec('stratege').consumes

    def test_chaque_agent_du_pipeline_declare_ce_qu_il_depose(self):
        """Un agent qui suit le protocole run(ctx) participe à la chaîne de
        production : il doit dire ce qu'il dépose, sinon rien ne peut consommer
        son résultat.

        Les agents de restitution en sont exclus à raison — voir le test
        suivant. Ce test ne comptait auparavant aucune exception, ce qui
        revenait à supposer que tout agent produit quelque chose.
        """
        pipeline = [a for a in registry.available() if a.spec.entrypoint == 'run']
        assert pipeline, "aucun agent de pipeline — le filtre est trop strict"
        for agent in pipeline:
            assert agent.spec.produces, agent.spec.id

    def test_un_agent_de_restitution_peut_legitimement_ne_rien_deposer(self):
        """Cas réel : le Design Agent met en forme ce que d'autres ont produit.
        Il ne dépose rien dans le contexte d'analyse, et lui exiger un
        `produces` reviendrait à lui inventer une sortie qu'il n'a pas.

        L'exclusion doit rester une règle explicite — entrypoint hors
        protocole — et non un oubli du test précédent.
        """
        design = registry.spec('design')
        assert design.produces == ''
        assert design.entrypoint != 'run'
        assert design.direct_access is False   # jamais visible dans l'UI


class TestRegistre:
    def test_un_identifiant_en_double_est_refuse(self):
        r = AgentRegistry()
        r.register(_spec())
        with pytest.raises(ValueError, match='déjà enregistré'):
            r.register(_spec())

    def test_agent_inconnu_liste_les_agents_declares(self):
        with pytest.raises(AgentNotFound, match='psychologue'):
            registry.get('le-psychologue')

    def test_declarer_facultatif_ce_qu_on_ne_consomme_pas_est_refuse(self):
        """Sinon la fiche se contredit en silence : le planificateur lirait une
        souplesse sur une dépendance qui n'existe pas."""
        with pytest.raises(ValueError, match='facultatif ce qu.il ne consomme pas'):
            _spec(consumes=('a',), optional_consumes=('b',))

    def test_un_statut_invalide_est_refuse(self):
        with pytest.raises(ValueError, match='Statut invalide'):
            _spec(status='peut-etre')

    def test_le_registre_distingue_declares_et_utilisables(self):
        """Règle, pas comptage : tout agent non utilisable doit porter un
        statut qui l'explique. Figer un chiffre faisait échouer ce test à
        chaque agent ajouté, sans rien protéger de réel.
        """
        declares = set(a.spec.id for a in registry.all())
        utilisables = set(a.spec.id for a in registry.available())
        assert utilisables < declares          # au moins un non utilisable
        for agent_id in declares - utilisables:
            assert registry.spec(agent_id).status != STATUS_AVAILABLE

    def test_les_trois_agents_de_production_restent_utilisables(self):
        """La garantie qui compte vraiment derrière l'ancien comptage."""
        utilisables = {a.spec.id for a in registry.available()}
        assert {'psychologue', 'stratege', 'createur'} <= utilisables

    def test_resoudre_un_agent_utilisable_rend_sa_classe(self):
        classe = registry.resolve('psychologue')
        assert classe.AGENT_ID == 'psychologue'


class TestStatutConstateEtNonSuppose:
    def test_un_agent_qui_ne_charge_pas_bascule_en_indisponible(self, monkeypatch):
        """Le statut ne doit pas être une promesse écrite en dur : si l'import
        casse, le registre doit le dire au lieu d'annoncer l'agent disponible."""
        import agents.catalog as catalog

        def _import_casse():
            raise ImportError('dépendance manquante')

        monkeypatch.setattr(catalog, '_loader', lambda *a: _import_casse)
        assert catalog._observed_status(
            'agents.psychologue', 'Psychologue', STATUS_AVAILABLE) == STATUS_UNAVAILABLE
