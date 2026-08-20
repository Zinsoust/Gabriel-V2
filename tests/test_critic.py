"""Contrat de la couche Critic.

Gabriel pratique la critique adverse à deux endroits, avec des schémas et des
politiques d'échec délibérément opposés. Cette couche uniformise la démarche —
jamais le résultat. Les tests vérifient d'abord que les deux comportements
existants sont reproduits à la lettre, avant tout rebranchement.
"""

import pytest

import core.critiques as critiques
from core.critic import (CRITIQUE_FAILED, CRITIQUE_INCOMPLETE, CRITIQUE_OK,
                         Critic, CriticError, CriticRegistry, CritiqueNotFound,
                         CritiqueSpec, registry)


def _llm(reponse):
    return lambda prompt, max_tokens=1500, **kw: reponse


def _llm_casse(message='fournisseur indisponible'):
    def _appel(prompt, max_tokens=1500, **kw):
        raise RuntimeError(message)
    return _appel


def _json_strict(text):
    """Contrat du Stratège : lève en cas d'échec."""
    import json
    return json.loads(text)


def _json_tolerant(text):
    """Contrat du Créateur : dégrade au lieu de lever."""
    import json
    try:
        return json.loads(text)
    except Exception:
        return {'raw': text, 'parse_error': True}


CRITIQUE_STRATEGIE_COMPLETE = (
    '{"point_faible_principal":"Le prix n\'est pas justifié",'
    '"angle_contrarien":"Vendre plus cher à moins de gens",'
    '"risque_non_couvert":"Dépendance à une seule plateforme",'
    '"ajustement_recommande":"Tester l\'offre haute avant de scaler",'
    '"confidence_score_independant":0.62,"verdict":"à ajuster"}'
)


class TestPolitiquesDEchecOpposees:
    """Le cœur du sujet : ces deux politiques ne doivent pas converger.

    Sans critique, la stratégie part simplement sans relecture. Sans critique,
    le texte du Créateur ne serait jamais livré — il lui faut un objet neutre.
    """

    def test_l_echec_de_la_critique_strategique_remonte_a_l_appelant(self):
        with pytest.raises(CriticError, match='fournisseur indisponible'):
            Critic().review(critiques.STRATEGY_CRITIQUE, 'peu importe',
                            call_llm=_llm_casse(), parse_json=_json_strict)

    def test_l_echec_de_la_critique_de_contenu_rend_un_objet_neutre(self):
        resultat = Critic().review(critiques.CREATION_CRITIQUE, 'peu importe',
                                   call_llm=_llm_casse(), parse_json=_json_tolerant)
        assert resultat.status == CRITIQUE_FAILED
        assert resultat.data == {'faiblesses': [], 'risque_principal': '',
                                 'verdict': 'livrable'}

    def test_une_critique_echouee_ne_vaut_pas_approbation(self):
        """Ne pas avoir d'objection parce qu'on n'a pas pu regarder n'est pas la
        même chose que ne pas en avoir après avoir regardé."""
        resultat = Critic().review(critiques.CREATION_CRITIQUE, 'x',
                                   call_llm=_llm_casse(), parse_json=_json_tolerant)
        assert resultat.verdict == 'livrable'   # le texte passe quand même…
        assert resultat.passed is False         # …mais sans caution du critique


class TestCritiqueStrategique:
    def test_une_critique_complete_est_rendue_telle_quelle(self):
        resultat = Critic().review(
            critiques.STRATEGY_CRITIQUE, 'x',
            call_llm=_llm(CRITIQUE_STRATEGIE_COMPLETE), parse_json=_json_strict)
        assert resultat.status == CRITIQUE_OK
        assert resultat.verdict == 'à ajuster'
        assert resultat.data['confidence_score_independant'] == 0.62

    def test_des_champs_manquants_n_empechent_pas_d_exploiter_le_reste(self):
        """Comportement historique : on signale, on ne jette pas — un JSON
        tronqué puis réparé reste utile."""
        resultat = Critic().review(
            critiques.STRATEGY_CRITIQUE, 'x',
            call_llm=_llm('{"verdict":"fragile"}'), parse_json=_json_strict)
        assert resultat.status == CRITIQUE_INCOMPLETE
        assert resultat.usable is True
        assert 'angle_contrarien' in resultat.missing_keys
        assert resultat.verdict == 'fragile'

    def test_un_score_nul_compte_comme_une_reponse(self):
        """Un critique qui évalue la confiance à zéro a répondu. Le traiter
        comme une omission effacerait son avis le plus tranché."""
        reponse = CRITIQUE_STRATEGIE_COMPLETE.replace('0.62', '0')
        resultat = Critic().review(critiques.STRATEGY_CRITIQUE, 'x',
                                   call_llm=_llm(reponse), parse_json=_json_strict)
        assert resultat.missing_keys == ()
        assert resultat.status == CRITIQUE_OK

    def test_seul_le_verdict_solide_vaut_approbation(self):
        for verdict, attendu in (('solide', True), ('à ajuster', False),
                                 ('fragile', False)):
            reponse = CRITIQUE_STRATEGIE_COMPLETE.replace('"à ajuster"', f'"{verdict}"')
            resultat = Critic().review(critiques.STRATEGY_CRITIQUE, 'x',
                                       call_llm=_llm(reponse), parse_json=_json_strict)
            assert resultat.passed is attendu, verdict


class TestCritiqueDeContenu:
    def test_le_verdict_se_deduit_des_faiblesses_quand_il_manque(self):
        """Règle reprise de `dialectic.run` : un texte sans faiblesse relevée
        est livrable, sinon il reste à améliorer."""
        avec = Critic().review(
            critiques.CREATION_CRITIQUE, 'x',
            call_llm=_llm('{"faiblesses":[{"zone":"hook","probleme":"plat",'
                          '"gravite":"critique"}],"risque_principal":"ignoré"}'),
            parse_json=_json_tolerant)
        sans = Critic().review(
            critiques.CREATION_CRITIQUE, 'x',
            call_llm=_llm('{"faiblesses":[],"risque_principal":"aucun"}'),
            parse_json=_json_tolerant)
        assert avec.verdict == 'a_ameliorer' and avec.passed is False
        assert sans.verdict == 'livrable' and sans.passed is True

    def test_un_verdict_explicite_n_est_pas_ecrase(self):
        resultat = Critic().review(
            critiques.CREATION_CRITIQUE, 'x',
            call_llm=_llm('{"faiblesses":[],"risque_principal":"","verdict":"a_ameliorer"}'),
            parse_json=_json_tolerant)
        assert resultat.verdict == 'a_ameliorer'

    def test_une_reponse_illisible_declenche_le_repli(self):
        """Le parseur du Créateur dégrade au lieu de lever : le sentinelle
        `parse_error` doit être reconnu comme un échec, pas pris pour une
        critique vide."""
        resultat = Critic().review(critiques.CREATION_CRITIQUE, 'x',
                                   call_llm=_llm('pas du json'),
                                   parse_json=_json_tolerant)
        assert resultat.status == CRITIQUE_FAILED
        assert resultat.data['verdict'] == 'livrable'


class TestRegistre:
    def test_les_deux_examens_sont_declares(self):
        assert 'critique.strategy' in registry
        assert 'critique.creation' in registry

    def test_le_registre_dit_lequel_est_bloquant(self):
        fiches = {s['id']: s for s in registry.describe()}
        assert fiches['critique.strategy']['blocking'] is True
        assert fiches['critique.creation']['blocking'] is False

    def test_un_identifiant_en_double_est_refuse(self):
        r = CriticRegistry()
        spec = CritiqueSpec(id='x', name='X', domain='test')
        r.register(spec)
        with pytest.raises(ValueError, match='déjà enregistrée'):
            r.register(spec)

    def test_une_critique_inconnue_liste_les_declarees(self):
        with pytest.raises(CritiqueNotFound, match='critique.strategy'):
            registry.get('critique.absente')


class TestEquivalenceAvecLesImplementationsExistantes:
    """Attentes littérales relevées sur le code d'origine avant rebranchement.

    Elles ne se comparent pas à une implémentation — elles figent ce que les
    deux agents produisaient, pour que le passage par la couche Critic ne
    change rien à ce que voit l'utilisateur.
    """

    REPONSE_STRATEGIE = (
        '{"point_faible_principal":"Le prix","angle_contrarien":"Inverse",'
        '"risque_non_couvert":"Plateforme","ajustement_recommande":"Tester",'
        '"confidence_score_independant":0.62,"verdict":"à ajuster"}'
    )

    def test_le_stratege_rend_la_critique_a_l_identique(self, monkeypatch):
        import agents.stratege as stratege
        monkeypatch.setattr(stratege, '_call_llm',
                            lambda p, max_tokens=1500, label='': self.REPONSE_STRATEGIE)
        assert stratege._critique_strategie({}, 'psy', 'biz') == {
            'point_faible_principal': 'Le prix', 'angle_contrarien': 'Inverse',
            'risque_non_couvert': 'Plateforme', 'ajustement_recommande': 'Tester',
            'confidence_score_independant': 0.62, 'verdict': 'à ajuster'}

    def test_le_stratege_rend_une_critique_tronquee_sans_la_jeter(self, monkeypatch):
        import agents.stratege as stratege
        monkeypatch.setattr(stratege, '_call_llm',
                            lambda p, max_tokens=1500, label='': '{"verdict":"fragile"}')
        assert stratege._critique_strategie({}, 'psy', 'biz') == {'verdict': 'fragile'}

    def test_une_panne_du_stratege_reste_une_RuntimeError(self, monkeypatch):
        """`Stratege.run` l'absorbe pour ne pas faire tomber la stratégie."""
        import agents.stratege as stratege

        def _casse(p, max_tokens=1500, label=''):
            raise RuntimeError('panne')

        monkeypatch.setattr(stratege, '_call_llm', _casse)
        with pytest.raises(RuntimeError):
            stratege._critique_strategie({}, 'psy', 'biz')

    def _contexte_creation(self, draft):
        from agents.creation.pipeline import CreationContext
        ctx = CreationContext(content_type='hooks', emotion='confiance')
        ctx.draft = draft
        ctx.plan = {'promesse': 'p', 'angle': 'a'}
        return ctx

    def test_le_createur_complete_le_verdict_a_l_identique(self, monkeypatch):
        import agents.createur as createur
        import agents.creation.dialectic as dialectic
        monkeypatch.setattr(createur, '_call_llm',
                            lambda p, max_tokens=3000, temperature=None:
                            '{"faiblesses":[{"zone":"hook","probleme":"plat",'
                            '"gravite":"critique"}],"risque_principal":"ignoré"}')
        ctx = self._contexte_creation({'texte': 'bonjour'})
        dialectic.run(ctx)
        assert ctx.critique == {
            'faiblesses': [{'zone': 'hook', 'probleme': 'plat', 'gravite': 'critique'}],
            'risque_principal': 'ignoré', 'verdict': 'a_ameliorer'}

    @pytest.mark.parametrize('cas', ['illisible', 'panne', 'sans_jet'])
    def test_le_createur_rend_toujours_un_objet_neutre_en_cas_d_echec(
            self, monkeypatch, cas):
        """Sans lui, le texte ne serait jamais livré à l'utilisateur."""
        import agents.createur as createur
        import agents.creation.dialectic as dialectic

        def _casse(p, max_tokens=3000, temperature=None):
            raise RuntimeError('panne')

        monkeypatch.setattr(
            createur, '_call_llm',
            _casse if cas == 'panne'
            else (lambda p, max_tokens=3000, temperature=None: 'pas du json'))
        ctx = self._contexte_creation(None if cas == 'sans_jet' else {'texte': 'bonjour'})
        dialectic.run(ctx)
        assert ctx.critique == {'faiblesses': [], 'risque_principal': '',
                                'verdict': 'livrable'}
