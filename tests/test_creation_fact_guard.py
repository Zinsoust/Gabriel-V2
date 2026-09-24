"""Aucun chiffre inventé dans une création (promesse Gabriel.ai).

Les exemples viennent d'une vraie génération du 13/09/2026, faite malgré la
consigne « n'invente jamais de chiffre » : 3h par semaine, 80 %, 2x plus
rapides, un tableau avant/après… Les chiffres réellement cités par l'audience
(80 Go, 15 Mb/s dans les commentaires) doivent, eux, être conservés.
"""
import json
import os

from agents.creation.fact_guard import PLACEHOLDER, guard_numbers, guard_result, sources_text

FIXTURE = os.path.join(os.path.dirname(__file__), '..', 'frontend-react', 'src', 'gabriel-v2',
                       'components', '__tests__', 'fixtures', 'psychologue-analyse-youtube.json')
DEMANDE = "Script vidéo YouTube de 60 secondes pour vendre une formation IA locale"


def _sources():
    with open(FIXTURE, encoding='utf-8') as f:
        return sources_text(DEMANDE, json.load(f))


def test_les_chiffres_inventes_sont_remplaces_par_un_emplacement():
    contenu = {'sections': [
        {'section': 'Tension', 'secondes': '3-15', 'texte': 'Vous passez **3h par semaine** à attendre.'},
        {'section': 'Preuve', 'secondes': '45-55', 'texte': 'Il a réduit son temps de validation de **80%** et va 2x plus vite.'},
    ]}
    propre, retires = guard_numbers(contenu, _sources())
    textes = json.dumps(propre, ensure_ascii=False)
    for invente in ('3h', '80%', '2x'):
        assert invente not in textes
    assert propre['sections'][0]['texte'] == f'Vous passez **{PLACEHOLDER} par semaine** à attendre.'
    assert set(retires) == {'3h', '80%', '2x'}


def test_les_chiffres_de_l_audience_et_de_la_demande_sont_conserves():
    contenu = {'texte': 'Pas besoin de 80 Go ni de 15 Mb/s. En 60 secondes, voici comment.'}
    sources = _sources() + "\nverbatim : 80 Go et une connexion à 15 Mb/s"
    propre, retires = guard_numbers(contenu, sources)
    assert propre == contenu
    assert retires == []


def test_les_indications_de_tournage_ne_sont_pas_touchees():
    contenu = {'sections': [{'secondes': '0-3', 'texte': 'Accroche', 'note_realisateur': 'Témoignage vidéo (15s), pause de 2 min'}],
               'duree_estimee': '60s'}
    propre, retires = guard_numbers(contenu, DEMANDE)
    assert propre == contenu and retires == []


def test_le_resultat_complet_signale_ce_qui_a_ete_retire():
    resultat = {'content': {'texte': 'Coût : 50€/an contre 1200€'}, 'full_text': 'Coût : 50€/an contre 1200€'}
    propre = guard_result(resultat, DEMANDE)
    assert PLACEHOLDER in propre['full_text'] and '50€' not in propre['full_text']
    assert propre['unverified_figures'] == ['1200€', '50€']


def test_une_annee_ou_un_numero_seul_n_est_pas_une_affirmation():
    contenu = {'texte': 'Même avec un PC de 2017, étape 1 puis étape 2.'}
    assert guard_numbers(contenu, '')[0] == contenu


def test_une_duree_inventee_en_secondes_est_aussi_verifiee():
    propre, retires = guard_numbers({'texte': 'On génère un brief en 10 secondes.'}, DEMANDE)
    assert retires == ['10 secondes'] and PLACEHOLDER in propre['texte']
    # « 60 secondes » vient de la demande : conservé.
    assert guard_numbers({'texte': 'En 60 secondes chrono.'}, DEMANDE)[1] == []


def test_un_temoignage_attribue_declenche_la_verification_des_faits():
    from agents.creation.fact_guard import _SUSPECT
    assert _SUSPECT.search("*'Avant, je devais relancer mon prompt plusieurs fois.'* — **[Léa, graphiste]**")


def test_formes_echappees_lors_du_test_reel():
    """Troisième génération réelle : ces formes passaient encore."""
    texte = {'texte': 'Un graphiste perd 1h30/semaine, débugge en 10s, facture +15% et signe 3 projets/semaine.'}
    propre, retires = guard_numbers(texte, sources_text(DEMANDE, {'dashboard': {'note': '15% des commentaires'}}))
    assert set(retires) == {'1h30', '10s', '+15%', '3 projets'}
    assert '15%' not in propre['texte']


# ── 14/09/2026 : génération réelle depuis une Cross Analyse ────────────────

def test_pseudos_et_montants_devise_devant_inventes_sont_retires():
    from agents.creation.fact_guard import guard_numbers, HANDLE_PLACEHOLDER, PLACEHOLDER
    texte = {'texte': "Capture Reddit de @TechFail2023 : facture de $49,87. Merci @Gabriel_ai et à vous pour 12€."}
    propre, retires = guard_numbers(texte, "L'audience cite @Gabriel_ai et un budget de 12 €.")
    assert '@TechFail2023' not in propre['texte'] and HANDLE_PLACEHOLDER in propre['texte']
    assert '$49,87' not in propre['texte'] and PLACEHOLDER in propre['texte']
    assert '@Gabriel_ai' in propre['texte'] and '12€' in propre['texte']
    assert {'@TechFail2023', '$49,87'} <= set(retires)


def test_les_anecdotes_personnelles_declenchent_la_verification_qualitative():
    from agents.creation.fact_guard import _SUSPECT
    assert _SUSPECT.search("avant de lancer Llama sur mon Dell XPS 13")
    assert _SUSPECT.search("des captures de mes erreurs CUDA")
    assert not _SUSPECT.search("Vous voulez créer sans limites, sans jargon.")


def test_chaque_etape_qui_ecrit_ou_juge_recoit_la_regle_des_sources(monkeypatch):
    import agents.createur as createur
    from agents.creation import planning, writing, dialectic, optimization
    from agents.creation.pipeline import CreationContext
    prompts = []

    def faux_llm(prompt, **kw):
        prompts.append(prompt)
        return '{"texte": "ok", "faiblesses": [{"zone": "hook", "probleme": "faible", "gravite": "critique"}], "verdict": "a_ameliorer"}'
    monkeypatch.setattr(createur, '_call_llm', faux_llm)
    ctx = CreationContext(content_type='youtube', user_request='Un script')
    for etape in (planning, writing, dialectic, optimization):
        etape.run(ctx)
    assert len(prompts) >= 4
    assert all('RÈGLE DES SOURCES' in p or 'Tu ne demandes JAMAIS' in p for p in prompts)


def test_la_verification_recoit_la_liste_des_chiffres_a_reformuler(monkeypatch):
    import agents.createur as createur
    from agents.creation import fact_guard
    from agents.creation.pipeline import CreationContext
    recu = []
    monkeypatch.setattr(createur, '_call_llm', lambda prompt, **kw: recu.append(prompt) or '{"texte": "Beaucoup de débutants abandonnent."}')
    ctx = CreationContext(content_type='youtube', user_request='Un script')
    ctx.final = {'texte': '90 % des débutants abandonnent en 3 jours.'}
    fact_guard.run(ctx)
    assert recu, "des chiffres non sourcés doivent déclencher la reformulation"
    assert 'CHIFFRES NON SOURCÉS À REFORMULER SANS CHIFFRE : 3 jours, 90 %' in recu[0]
    assert ctx.final['texte'] == 'Beaucoup de débutants abandonnent.'


def test_l_outil_gabriel_n_est_jamais_presente_comme_le_produit():
    from agents.creation.fact_guard import SOURCE_RULE
    from agents.createur import _SYSTEM_PROMPTS
    assert "Gabriel est l'outil qui t'aide à écrire" in SOURCE_RULE
    assert all('LE CRÉATEUR de Gabriel' not in p for p in _SYSTEM_PROMPTS.values())
