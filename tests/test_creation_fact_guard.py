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


def test_l_outil_gabriel_n_est_jamais_presente_comme_le_produit():
    from agents.creation.fact_guard import SOURCE_RULE
    from agents.createur import _SYSTEM_PROMPTS
    assert "Gabriel est l'outil qui t'aide à écrire" in SOURCE_RULE
    assert all('LE CRÉATEUR de Gabriel' not in p for p in _SYSTEM_PROMPTS.values())


# ── Étape 2 (24/09/2026) : quantités en Go, scènes inventées, emplacements chiffrés ──

def test_les_quantites_en_go_non_sourcees_sont_retirees_mais_celles_de_l_audience_restent():
    from agents.creation.fact_guard import guard_numbers, PLACEHOLDER
    texte = {'texte': "Llama 2 tient dans 10 Go, Stable Diffusion demande 16 Go, et vous craignez les 80 Go."}
    propre, retires = guard_numbers(texte, "Un commentaire de l'audience : installer jusqu'à 80 GB sur mon ordinateur.")
    assert '10 Go' not in propre['texte'] and '16 Go' not in propre['texte']
    assert '80 Go' in propre['texte']          # « 80 GB » et « 80 Go » : même affirmation, dite par l'audience
    assert propre['texte'].count(PLACEHOLDER) == 2
    assert set(retires) == {'10 Go', '16 Go'}


def test_les_scenes_dialoguees_presentees_comme_reelles_declenchent_la_verification():
    from agents.creation.fact_guard import _SUSPECT
    # Une phrase par motif : chacune ne doit être attrapée que par « son » motif.
    for phrase in ("Extrait d'un Discord, voici la discussion.",
                   "Capture d'écran d'un forum ouverte à l'écran.",
                   "Un débutant répond : « Ça marche ! Merci ! »",
                   "Moi aussi, j'ai été là."):
        assert _SUSPECT.search(phrase), phrase
    assert not _SUSPECT.search("Imaginez une scène où quelqu'un hésite devant son écran.")


def test_la_regle_des_sources_interdit_les_emplacements_chiffres_et_les_scenes_inventees():
    from agents.creation.fact_guard import SOURCE_RULE
    assert 'Aucun emplacement entre crochets pour un chiffre' in SOURCE_RULE
    assert 'Aucune scène dialoguée présentée comme réelle' in SOURCE_RULE


def _ctx(final):
    from agents.creation.pipeline import CreationContext
    ctx = CreationContext(content_type='youtube', user_request='Un script')
    ctx.final = final
    return ctx


def test_seuls_les_passages_fautifs_sont_envoyes_a_la_reecriture(monkeypatch):
    import agents.createur as createur
    from agents.creation import fact_guard
    prompts = []

    def faux_llm(prompt, **kw):
        prompts.append(prompt)
        return '{"0": "Beaucoup de débutants abandonnent avant la première installation."}'
    monkeypatch.setattr(createur, '_call_llm', faux_llm)
    ctx = _ctx({'introduction': "Ici on parle simplement de ce que vous ressentez devant un écran noir.",
                'partie': "90 % des débutants abandonnent avant la première installation.",
                'cta': "Abonnez-vous et dites-moi en commentaire ce qui vous bloque le plus."})
    fact_guard.run(ctx)
    assert len(prompts) == 1
    assert '90 %' in prompts[0] and 'écran noir' not in prompts[0] and 'Abonnez-vous' not in prompts[0]
    assert ctx.final['partie'] == "Beaucoup de débutants abandonnent avant la première installation."
    assert ctx.final['introduction'].startswith("Ici on parle simplement")     # intact
    assert ctx.final['cta'].startswith("Abonnez-vous")                           # intact


def test_les_emplacements_chiffres_et_les_scenes_inventees_sont_reecrits(monkeypatch):
    import agents.createur as createur
    from agents.creation import fact_guard
    recu = []

    def faux_llm(prompt, **kw):
        recu.append(prompt)
        return '{"0": "Votre PC modeste suffit largement pour démarrer.", "1": "[Scène à tourner : un débutant montre son écran et pose sa question.]", "2": "Imaginez quelqu\'un qui automatise ses étiquettes avec un petit script."}'
    monkeypatch.setattr(createur, '_call_llm', faux_llm)
    ctx = _ctx({'a': "Un PC à [montant réel à insérer] suffit largement pour démarrer.",
                'b': "Extrait d'un fil Reddit où un débutant demande : « Comment faire sans GPU ? »",
                'c': "Un artisan a automatisé ses étiquettes, voici les projets réels de la semaine."})
    fact_guard.run(ctx)
    assert '[montant réel à insérer]' not in json.dumps(ctx.final, ensure_ascii=False)
    assert 'Reddit' not in ctx.final['b'] and ctx.final['b'].startswith('[Scène à tourner')
    assert 'artisan' not in ctx.final['c']


def test_une_reponse_coupee_ne_remplace_jamais_le_texte_d_origine(monkeypatch):
    import agents.createur as createur
    from agents.creation import fact_guard
    monkeypatch.setattr(createur, '_call_llm', lambda p, **kw: '{"0": "ok"}')
    original = "Un PC à [montant réel à insérer] suffit largement pour démarrer sans rien acheter du tout."
    ctx = _ctx({'a': original})
    fact_guard.run(ctx)
    assert ctx.final['a'] == original


def test_la_reecriture_s_arrete_apres_deux_tours(monkeypatch):
    import agents.createur as createur
    from agents.creation import fact_guard
    appels = []
    # Chaque réponse est différente et garde un emplacement chiffré : sans plafond, la boucle continuerait.
    monkeypatch.setattr(createur, '_call_llm', lambda p, **kw: appels.append(1) or json.dumps({"0": f"Version {len(appels)} : un PC à [prix réel à insérer] pour démarrer sans souci."}))
    ctx = _ctx({'a': "Un PC à [montant réel à insérer] suffit largement pour démarrer."})
    fact_guard.run(ctx)
    assert len(appels) == 2


def test_un_texte_propre_ne_declenche_aucun_appel(monkeypatch):
    import agents.createur as createur
    from agents.creation import fact_guard
    appels = []
    monkeypatch.setattr(createur, '_call_llm', lambda p, **kw: appels.append(1) or '{}')
    ctx = _ctx({'a': "Vous avez le droit d'apprendre à votre rythme, avec le matériel que vous avez déjà."})
    fact_guard.run(ctx)
    assert appels == []
    assert ctx.final['a'].startswith("Vous avez le droit")


def test_les_fausses_preuves_sociales_sont_reperees_pour_la_reecriture():
    from agents.creation.fact_guard import _fautif
    for texte in ("Preuve sociale : 'Je croyais avoir besoin d'un serveur. En réalité, mon PC a suffi.'",
                  "Cas réel : capture d'une configuration fonctionnelle sur un PC d'occasion, CPU Intel i5.",
                  "Extrait d'une discussion : 'On a cru que ça ne marcherait jamais avec si peu de RAM.'"):
        assert _fautif(texte, set(), set()), texte
    assert not _fautif("Vous avez le droit d'apprendre à votre rythme, avec le matériel que vous avez déjà.", set(), set())
