"""Ariane n'invente ni prix ni statistique.

Constaté le 24/09/2026 sur une vraie stratégie : « atelier à 9 € », « upsell à 49 € »,
« si 80 % paient 5 €, le modèle à 49 € est irréaliste ». Le prompt demandait lui-même une
fourchette de prix et un budget estimé, et la relecture critique inventait à son tour.
"""
import json
import re

import pytest

from agents import strategy_guard as g

BRAIN = "Offre actuelle : formation à 1 200 € (réductions jusqu'à 15 %). Cible : dirigeants de PME."
PSYCHO = '{"distribution": {"positif_pct": 53, "negatif_pct": 20}, "verbatims": ["installer 80 Go sur mon PC, non merci"]}'
SOURCES = g.sources_for(BRAIN, PSYCHO, "Vidéo IA locale")


def _claims(texte):
    a, p = g.allowed_numbers(SOURCES)
    return g.unsupported_claims(texte, a, p)


# ── Ce qui est réellement connu ─────────────────────────────────────────────

def test_les_chiffres_autorises_viennent_des_donnees_reelles():
    montants, pourcents = g.allowed_numbers(SOURCES)
    assert montants == {'1200'}
    assert pourcents == {'15', '53', '20'}           # « 15 % » du profil, champs *_pct du rapport
    assert '80' not in pourcents, "« 80 Go » cité par l'audience ne cautionne pas « 80 % »"


def test_un_montant_ou_un_pourcentage_inventes_sont_reperes():
    assert _claims("Un atelier à 9 € puis un upsell à 49 €.") == ['9 €', '49 €']
    assert _claims("Si 80 % paient 5 €, le modèle est irréaliste.") == ['5 €', '80 %']
    assert _claims("Une offre à $49,87 par mois.") == ['$49,87']
    assert _claims("Entre 9 et 49 € selon le palier.") == ['9 et 49 €'] or _claims("de 9 à 49 €") == ['9 à 49 €']


def test_ce_qui_figure_dans_les_donnees_est_conserve():
    assert _claims("Gardez votre formation à 1 200 € et limitez les remises à 15 %.") == []
    assert _claims("53 % de commentaires favorables, 20 % d'opposés.") == []


def test_les_durees_et_les_cadences_ne_sont_pas_des_chiffres_inventes():
    assert _claims("Plan sur 90 jours : semaines 1 à 4, puis 3 mois de test, 2 posts par semaine.") == []


# ── Correction du document ──────────────────────────────────────────────────

STRATEGIE = {
    'executive_decision': {'one_sentence_decision': "Lancer un atelier d'entrée pour débutants.", 'confidence_score': 0.8},
    'pricing_logic': {'recommended_price_range': "Atelier à 9 €, puis extension à 49 €.",
                      'pricing_reasoning': "Si 80 % paient 5 €, on reste sur l'entrée."},
    'offre_recommandee': {'prix_recommande': "Votre formation à 1 200 € reste l'offre principale."},
    'plan_90_jours': {'phase_1': {'periode': 'Jours 1-30', 'taches': ["Tester l'atelier auprès de quelques acheteurs"]}},
}


def test_sans_modele_de_reecriture_les_chiffres_inventes_deviennent_des_emplacements():
    propre, retires = g.guard_strategy(STRATEGIE, SOURCES)
    texte = json.dumps(propre, ensure_ascii=False)
    assert '9 €' not in texte and '49 €' not in texte and '80 %' not in texte and '5 €' not in texte
    assert g.AMOUNT_PLACEHOLDER in propre['pricing_logic']['recommended_price_range']
    assert g.PERCENT_PLACEHOLDER in propre['pricing_logic']['pricing_reasoning']
    assert set(retires) == {'9 €', '49 €', '80 %', '5 €'}
    # Ce qui est vrai ou structurel est intact.
    assert propre['offre_recommandee']['prix_recommande'] == STRATEGIE['offre_recommandee']['prix_recommande']
    assert propre['plan_90_jours'] == STRATEGIE['plan_90_jours']
    assert propre['executive_decision']['confidence_score'] == 0.8
    assert 'Atelier à 9 €' in json.dumps(STRATEGIE, ensure_ascii=False), "l'original ne doit jamais être modifié"


def test_les_passages_fautifs_sont_reecrits_un_par_un_et_les_autres_ne_bougent_pas():
    envoyes = []

    def faux_llm(prompt):
        envoyes.append(prompt)
        extraits = json.loads(prompt.split('EXTRAITS :\n', 1)[1])
        return json.dumps({n: re.sub(r'\d+\s?(?:€|%)', 'un tarif accessible', t) for n, t in extraits.items()})

    propre, retires = g.guard_strategy(STRATEGIE, SOURCES, faux_llm, json.loads)
    assert len(envoyes) == 1
    assert '1 200' not in envoyes[0].split('EXTRAITS :\n', 1)[1], "un passage sans chiffre inventé n'est jamais envoyé à la réécriture"
    assert 'Tester l' not in envoyes[0].split('EXTRAITS :\n', 1)[1]
    assert propre['pricing_logic']['recommended_price_range'] == "Atelier à un tarif accessible, puis extension à un tarif accessible."
    assert g.AMOUNT_PLACEHOLDER not in json.dumps(propre, ensure_ascii=False)         # la réécriture a suffi
    assert propre['offre_recommandee'] == STRATEGIE['offre_recommandee']


def test_une_reecriture_qui_garde_un_chiffre_inventé_est_rattrapee_par_le_remplacement():
    propre, _ = g.guard_strategy(STRATEGIE, SOURCES, lambda p: '{"0": "Atelier à 9 € seulement.", "1": "ok"}', json.loads)
    assert '9 €' not in json.dumps(propre, ensure_ascii=False)


def test_un_modele_indisponible_ou_une_reponse_illisible_ne_laisse_passer_aucun_chiffre():
    def panne(prompt):
        raise RuntimeError('quota')
    for llm, parse in ((panne, json.loads), (lambda p: 'pas du json', json.loads)):
        propre, retires = g.guard_strategy(STRATEGIE, SOURCES, llm, parse)
        assert '49 €' not in json.dumps(propre, ensure_ascii=False) and retires


def test_la_reecriture_ne_tourne_que_deux_tours_au_plus():
    appels = []

    def obstine(prompt):
        appels.append(1)
        extraits = json.loads(prompt.split('EXTRAITS :\n', 1)[1])
        return json.dumps({n: f"Version {len(appels)} à {len(appels) + 10} €" for n in extraits})
    g.guard_strategy(STRATEGIE, SOURCES, obstine, json.loads)
    assert len(appels) == 2


def test_une_strategie_sans_chiffre_inventé_ne_declenche_aucun_appel():
    appels = []
    propre, retires = g.guard_strategy({'a': "Votre formation à 1 200 € sur 90 jours."}, SOURCES, lambda p: appels.append(p) or '{}', json.loads)
    assert appels == [] and retires == [] and propre == {'a': "Votre formation à 1 200 € sur 90 jours."}


# ── Dans le Stratège lui-même ───────────────────────────────────────────────

def _lancer(monkeypatch, brain_context, psycho, reponses):
    from agents import stratege
    prompts = []

    def faux_llm(prompt, max_tokens=5000, label=''):
        prompts.append((label, prompt))
        if label == 'strategie_garde':
            extraits = json.loads(prompt.split('EXTRAITS :\n', 1)[1])
            return json.dumps({n: re.sub(r'\d+\s?(?:€|%)', 'un tarif à définir', t) for n, t in extraits.items()})
        return json.dumps(reponses[label])
    monkeypatch.setattr(stratege, '_call_llm', faux_llm)
    monkeypatch.setattr(stratege, '_load_rag_rules', lambda *a, **k: '')
    from agents.context import AnalysisContext
    ctx = AnalysisContext(comments=[], brain_context=brain_context, video_context='', title='Vidéo IA locale')
    ctx.add('psychologue', psycho)
    stratege.Stratege().run(ctx)
    return ctx.get('stratege')['strategie'], prompts


REPONSES = {
    'strategie': {'strategie': {
        'pricing_logic': {'recommended_price_range': "Atelier à 9 €, puis 49 €."},
        'offre_recommandee': {'prix_recommande': "9 €", 'justification_prix': "Formation actuelle à 1 200 €."},
        'plan_90_jours': {'phase_1': {'periode': 'Jours 1-30'}}}},
    'critique': {'point_faible_principal': "Rien de mesuré.", 'angle_contrarien': "Si 80 % paient 5 €, viser 49 €.",
                 'risque_non_couvert': "x", 'ajustement_recommande': "Un atelier à 9 €.",
                 'confidence_score_independant': 0.5, 'verdict': 'à ajuster'},
}


def test_le_stratege_livre_une_strategie_et_une_critique_sans_chiffre_invente(monkeypatch):
    strat, prompts = _lancer(monkeypatch, BRAIN, {'brief': {'insight': 'audience frustrée'}}, REPONSES)
    texte = json.dumps({k: v for k, v in strat.items() if k != 'chiffres_retires'}, ensure_ascii=False)   # la liste des chiffres retirés les cite forcément
    for invente in ('9 €', '49 €', '80 %', '5 €'):
        assert invente not in texte, f"« {invente} » a survécu : {texte[:300]}"
    assert '1 200 €' in strat['offre_recommandee']['justification_prix']            # donnée de l'utilisateur : conservée
    assert strat['plan_90_jours']['phase_1']['periode'] == 'Jours 1-30'
    assert {'9 €', '49 €', '80 %', '5 €'} <= set(strat['chiffres_retires'])
    assert 'critique_strategique' in strat


def test_le_prompt_ne_demande_plus_de_prix_inventes_et_la_relecture_recoit_la_regle(monkeypatch):
    _, prompts = _lancer(monkeypatch, BRAIN, {'brief': {'insight': 'x'}}, REPONSES)
    generation = [p for label, p in prompts if label == 'strategie'][0]
    critique = [p for label, p in prompts if label == 'critique'][0]
    assert 'RÈGLE DES CHIFFRES' in generation and 'RÈGLE DES CHIFFRES' in critique
    assert 'Fourchette de prix recommandée avec justification' not in generation
    assert 'budget estimé de la cible' not in generation
    assert '[montant à définir]' in generation


def test_sans_profil_business_aucun_montant_n_est_autorise(monkeypatch):
    strat, _ = _lancer(monkeypatch, '', {'brief': {'insight': 'x'}}, REPONSES)
    assert not re.search(r'\d\s?€', json.dumps({k: v for k, v in strat.items() if k != 'chiffres_retires'}, ensure_ascii=False))
    assert '1 200 €' in strat['chiffres_retires']            # même le montant de l'ancien profil : absent des données de CE test


def test_une_reponse_coupee_ne_remplace_jamais_le_texte_d_origine():
    longue = {'a': "Proposez d'abord une offre d'entrée à 9 € pour rassurer les débutants hésitants, puis une offre principale."}
    propre, _ = g.guard_strategy(longue, SOURCES, lambda p: '{"0": "ok"}', json.loads)
    assert propre['a'].startswith("Proposez d'abord une offre d'entrée à ") and g.AMOUNT_PLACEHOLDER in propre['a']


# ── La mémoire de cas ne cautionne jamais un chiffre ────────────────────────

MEMOIRE = ("▸ Cas [2026-09-14] — similarité 45/100\n  Décision choisie : atelier hybride à 49–99 €\n"
           "  Offre : Atelier — débutants — 99 €\n  Feedback : positif (60 % de conversion)")


def test_les_chiffres_de_la_memoire_ne_sont_pas_des_sources():
    a, p = g.allowed_numbers(g.sources_for(BRAIN, PSYCHO, "titre"))
    assert '99' not in a and '49' not in a and '60' not in p
    assert 'mémoire' not in g.sources_for.__code__.co_varnames


def test_la_memoire_injectee_dans_le_prompt_ne_suggere_aucun_prix(monkeypatch):
    from agents import stratege
    prompts = []

    def faux_llm(prompt, max_tokens=5000, label=''):
        prompts.append((label, prompt))
        return json.dumps({'strategie': {'decision_centrale': "Un atelier d'entrée pour débutants curieux d'IA locale."}})
    monkeypatch.setattr(stratege, '_call_llm', faux_llm)
    monkeypatch.setattr(stratege, '_critique_strategie', lambda *a, **k: {})
    monkeypatch.setattr(stratege, '_load_rag_rules', lambda *a, **k: '')
    from agents.context import AnalysisContext
    ctx = AnalysisContext(comments=[], brain_context=BRAIN, video_context='', title='', memory_context=MEMOIRE)
    ctx.add('psychologue', {'brief': {'insight': 'x'}})
    stratege.Stratege().run(ctx)
    prompt = [p for label, p in prompts if label == 'strategie'][0]
    memoire_du_prompt = prompt.split('CAS SIMILAIRES PASSÉS :', 1)[1].split('━━━', 1)[0]
    assert 'atelier hybride' in memoire_du_prompt                       # la décision passée reste utile
    assert '49' not in memoire_du_prompt and '99' not in memoire_du_prompt and '60 %' not in memoire_du_prompt
    assert g.AMOUNT_PLACEHOLDER in memoire_du_prompt


def test_un_prix_de_la_memoire_repris_par_le_modele_est_retire_de_la_strategie(monkeypatch):
    reponses = {'strategie': {'strategie': {'pricing_logic': {'recommended_price_range': "Comme les cas passés : 49–99 €."}}},
                'critique': {'point_faible_principal': 'x', 'angle_contrarien': 'y', 'risque_non_couvert': 'z',
                             'ajustement_recommande': 'w', 'confidence_score_independant': 0.5, 'verdict': 'solide'}}
    from agents import stratege
    monkeypatch.setattr(stratege, '_call_llm', lambda prompt, max_tokens=5000, label='': (
        json.dumps({n: 'Comme les cas passés.' for n in json.loads(prompt.split('EXTRAITS :\n', 1)[1])}) if label == 'strategie_garde'
        else json.dumps(reponses[label])))
    monkeypatch.setattr(stratege, '_load_rag_rules', lambda *a, **k: '')
    from agents.context import AnalysisContext
    ctx = AnalysisContext(comments=[], brain_context=BRAIN, video_context='', title='', memory_context=MEMOIRE)
    ctx.add('psychologue', {'brief': {'insight': 'x'}})
    stratege.Stratege().run(ctx)
    strat = ctx.get('stratege')['strategie']
    assert '49' not in json.dumps({k: v for k, v in strat.items() if k != 'chiffres_retires'})
