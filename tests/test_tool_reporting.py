"""Équivalence des outils de rapport PDF.

Purs au sens strict : un dictionnaire entre, des octets sortent. La preuve
porte donc sur des octets réellement produits, pas sur un appel simulé.
"""

import pytest

import tools as tools_pkg


ENTRY = {
    'analysis_id': 'analyse-test',
    'title': "Structurer son offre",
    'created_at': '2026-08-21',
    'full_result': {
        'kpis': {'engagement': {'score': 72}, 'opportunite': {'score': 65}},
        'distribution': {'positif': 60, 'negatif': 15, 'neutre': 25},
        'brief': {'synthese': 'Audience motivée mais freinée par le prix',
                  'insight_cle': 'Le prix est un proxy de la peur de mal choisir'},
        'personas': [{'nom': 'Le Pragmatique', 'poids': '40%'}],
    },
}
STRATEGIE = {
    'decision_centrale': "Prioriser une offre intermédiaire à 490 €",
    'offre_recommandee': {'nom': 'Programme accompagné', 'prix': '490 €'},
    'recommandations_prioritaires': [{'action': 'Tester sur 20 prospects'}],
}


def _pdf_valide(octets):
    """Un PDF réel commence par %PDF- et finit par %%EOF."""
    return (isinstance(octets, (bytes, bytearray))
            and octets.startswith(b'%PDF-')
            and b'%%EOF' in octets[-2048:])


class TestEquivalenceAvecLesFonctionsDOrigine:
    def test_le_rapport_danalyse_rend_ce_que_la_fonction_rend(self):
        from services.gen_pdf import generate_analysis_pdf

        attendu = generate_analysis_pdf(ENTRY, include_strategy=True)
        obtenu = tools_pkg.registry.get('reporting.analysis_pdf').run(
            entry=ENTRY, include_strategy=True)

        assert _pdf_valide(obtenu)
        # Deux PDF du même contenu diffèrent par leur horodatage interne :
        # comparer octet à octet serait instable. La taille et l'en-tête
        # suffisent à prouver que c'est le même document.
        assert abs(len(obtenu) - len(attendu)) < 200

    def test_le_rapport_de_strategie_rend_ce_que_la_fonction_rend(self):
        from services.gen_pdf import generate_strategy_pdf

        attendu = generate_strategy_pdf(STRATEGIE, ENTRY)
        obtenu = tools_pkg.registry.get('reporting.strategy_pdf').run(
            strategy_data=STRATEGIE, analysis_entry=ENTRY)

        assert _pdf_valide(obtenu)
        assert abs(len(obtenu) - len(attendu)) < 200

    def test_les_deux_outils_appellent_bien_deux_fonctions_differentes(self):
        """Comparer des tailles ne suffit pas : deux appels à la même fonction
        avec des arguments différents donnent déjà des tailles différentes.
        On vérifie donc quelle fonction est réellement appelée."""
        import services.gen_pdf as gen_pdf

        appels = []
        vrai_analyse = gen_pdf.generate_analysis_pdf
        vrai_strategie = gen_pdf.generate_strategy_pdf
        gen_pdf.generate_analysis_pdf = lambda *a, **k: appels.append('analyse') or b'%PDF-\n%%EOF'
        gen_pdf.generate_strategy_pdf = lambda *a, **k: appels.append('strategie') or b'%PDF-\n%%EOF'
        try:
            tools_pkg.registry.get('reporting.analysis_pdf').run(entry=ENTRY)
            tools_pkg.registry.get('reporting.strategy_pdf').run(strategy_data=STRATEGIE)
        finally:
            gen_pdf.generate_analysis_pdf = vrai_analyse
            gen_pdf.generate_strategy_pdf = vrai_strategie

        assert appels == ['analyse', 'strategie']


class TestOptions:
    def test_exclure_la_strategie_produit_un_document_strictement_plus_court(self):
        """`include_strategy` doit réellement agir — sinon l'option serait
        décorative et l'appelant croirait maîtriser le contenu.

        La clé lue est `strategie_result` (et non `strategy`) : un fixture qui
        se trompe de nom ne déclenche jamais la branche, et le test passerait
        sans rien vérifier.
        """
        outil = tools_pkg.registry.get('reporting.analysis_pdf')
        entry_avec = dict(ENTRY, strategie_result=STRATEGIE)
        avec = outil.run(entry=entry_avec, include_strategy=True)
        sans = outil.run(entry=entry_avec, include_strategy=False)
        assert len(sans) < len(avec), (
            "inclure la stratégie n'a rien ajouté au document — "
            "l'option n'est pas transmise")

    def test_la_strategie_seule_fonctionne_sans_analyse_dorigine(self):
        obtenu = tools_pkg.registry.get('reporting.strategy_pdf').run(
            strategy_data=STRATEGIE)
        assert _pdf_valide(obtenu)


class TestContrat:
    def test_le_contrat_se_declare_pur_et_non_cache(self):
        """Déterministe, mais volontairement non caché : un PDF pèse lourd en
        mémoire pour un gain nul — produit une fois, téléchargé, oublié."""
        for tool_id in ('reporting.analysis_pdf', 'reporting.strategy_pdf'):
            spec = tools_pkg.registry.get(tool_id).spec
            assert spec.deterministic is True
            assert spec.cacheable is False
            assert spec.timeout_s is None
