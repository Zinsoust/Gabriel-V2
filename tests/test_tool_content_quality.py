"""Équivalence de l'outil de contrôle qualité de contenu.

`quality_check_content` n'utilise jamais `self` malgré sa forme de méthode :
c'est une fonction pure. Le point le plus utile à vérifier est le détecteur
de formules « IA-sounding », seule méthodologie du dépôt implémentée deux
fois avant ce chantier (prompt + regex) — ici c'est la regex.
"""

import tools as tools_pkg
from agents.createur import Createur


PSYCHO_DATA = {'psychologie': {'frustrations': ['le manque de temps pour se former'],
                               'desirs_caches': ['être reconnu comme expert']}}
STRATEGY = {'angle_positionnel': 'Accompagnement premium sur mesure'}


class TestEquivalenceAvecLaMethodeDOrigine:
    def test_loutil_rend_ce_que_quality_check_content_rend(self):
        contenu = {'hooks': [{'texte': "Le manque de temps pour se former vous freine ?"}]}
        attendu = Createur().quality_check_content(contenu, PSYCHO_DATA, STRATEGY, 'hooks')
        obtenu = tools_pkg.registry.get('content_quality.check').run(
            content_result=contenu, psycho_data=PSYCHO_DATA, strategy=STRATEGY,
            content_type='hooks')
        assert obtenu == attendu


class TestDetecteurDeStyleIA:
    def test_une_formule_generique_est_detectee(self):
        contenu = {'texte': "Il est temps de libérer ton potentiel dès aujourd'hui."}
        obtenu = tools_pkg.registry.get('content_quality.check').run(
            content_result=contenu, psycho_data={}, strategy={}, content_type='post')
        assert obtenu['ai_free'] is False
        assert obtenu['not_generic'] is False

    def test_un_texte_specifique_et_ancre_passe_les_deux_criteres(self):
        contenu = {'texte': ("Le manque de temps pour se former, on l'a tous vécu. "
                             "Voici comment j'ai structuré 3 heures par semaine, "
                             "pas plus, pour livrer mon premier module en un mois "
                             "sans sacrifier mes soirées ni mes weekends.")}
        obtenu = tools_pkg.registry.get('content_quality.check').run(
            content_result=contenu, psycho_data={}, strategy={}, content_type='post')
        assert obtenu['ai_free'] is True


class TestAncrageAudienceEtStrategie:
    def test_un_contenu_qui_reprend_une_frustration_reelle_est_ancre(self):
        contenu = {'texte': "Le manque de temps pour se former ne devrait plus être un frein."}
        obtenu = tools_pkg.registry.get('content_quality.check').run(
            content_result=contenu, psycho_data=PSYCHO_DATA, strategy={}, content_type='post')
        assert obtenu['based_on_psychology'] is True

    def test_un_contenu_sans_lien_avec_laudience_nest_pas_ancre(self):
        contenu = {'texte': "Un contenu totalement générique sans rapport."}
        obtenu = tools_pkg.registry.get('content_quality.check').run(
            content_result=contenu, psycho_data=PSYCHO_DATA, strategy={}, content_type='post')
        assert obtenu['based_on_psychology'] is False


class TestContrat:
    def test_le_contrat_se_declare_pur_et_cacheable(self):
        spec = tools_pkg.registry.get('content_quality.check').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
        assert spec.timeout_s is None
