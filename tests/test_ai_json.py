"""Contrats du parseur JSON unique.

Quatre implémentations coexistaient, avec trois contrats d'échec différents —
dont deux fonctions portant le même nom (`_parse_json`) et faisant l'inverse
l'une de l'autre : côté Stratège elle levait une exception, côté Créateur elle
renvoyait un objet marqué en erreur. Ces tests fixent le comportement unique
qui les remplace, y compris les cas que chaque ancienne version savait traiter.
"""

import pytest

from core.ai_json import AiJsonError, parse_ai_json


class TestFormesAcceptees:
    def test_json_propre(self):
        assert parse_ai_json('{"a": 1}') == {"a": 1}

    def test_json_encadre_de_balises_markdown(self):
        """Cas que seul le parseur du Créateur savait traiter."""
        assert parse_ai_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_noye_dans_de_la_prose(self):
        """Cas que seuls les parseurs Psychologue/Stratège savaient traiter."""
        texte = 'Voici votre analyse :\n{"a": 1}\nJ\'espère que cela convient.'
        assert parse_ai_json(texte) == {"a": 1}

    def test_balises_et_prose_combinees(self):
        """Aucune des anciennes versions ne gérait les deux à la fois."""
        texte = 'Résultat :\n```json\n{"a": 1}\n```\nVoilà.'
        assert parse_ai_json(texte) == {"a": 1}

    def test_virgule_finale(self):
        assert parse_ai_json('{"a": 1,}') == {"a": 1}

    def test_caracteres_de_controle(self):
        assert parse_ai_json('{"a": "x\x08y"}')["a"].endswith("y")

    def test_json_tronque_par_la_limite_de_tokens(self):
        """Une réponse coupée doit être réparée plutôt que perdue."""
        result = parse_ai_json('{"a": 1, "b": "texte incomp')
        assert result["a"] == 1


class TestContratDechec:
    def test_mode_raise_leve_une_erreur_typee(self):
        with pytest.raises(AiJsonError):
            parse_ai_json('aucun json ici', on_error='raise')

    def test_mode_sentinel_degrade_sans_lever(self):
        """Le Créateur préfère rendre le texte brut plutôt que rien du tout."""
        result = parse_ai_json('aucun json ici', on_error='sentinel')
        assert result['parse_error'] is True
        assert result['raw'] == 'aucun json ici'

    def test_reponse_vide_en_mode_raise(self):
        with pytest.raises(AiJsonError):
            parse_ai_json('', on_error='raise')

    def test_reponse_vide_en_mode_sentinel(self):
        assert parse_ai_json('', on_error='sentinel')['parse_error'] is True

    def test_le_label_situe_l_appel_dans_le_message(self):
        with pytest.raises(AiJsonError, match=r'\[personas\]'):
            parse_ai_json('rien', label='personas')

    def test_un_mode_inconnu_est_refuse_immediatement(self):
        """Une faute de frappe sur on_error ne doit pas se traduire par un
        comportement d'échec silencieusement différent de celui attendu."""
        with pytest.raises(ValueError, match='on_error invalide'):
            parse_ai_json('{"a": 1}', on_error='ignore')


class TestNonRegressionDesTypes:
    def test_une_liste_json_n_est_pas_acceptee_comme_dict(self):
        """Tous les appelants attendent un dict ; rendre une liste casserait
        leur code plus loin, de façon difficile à diagnostiquer."""
        with pytest.raises(AiJsonError):
            parse_ai_json('[1, 2, 3]', on_error='raise')

    def test_un_dict_vide_est_traite_comme_un_echec(self):
        """Un modèle qui renvoie {} n'a rien produit d'exploitable."""
        assert parse_ai_json('{}', on_error='sentinel')['parse_error'] is True
