"""Salle Cross : profils par audience et synthèse sémantique ancrée sur les preuves."""
from core import cross_synthesis as cs

CROSS = {'source_analyses': [
    {'source_id': 'sa', 'analysis_id': 'an-a', 'metadata': {'title': 'IA locale'}, 'comment_stats': {'total_comments': 115},
     'fears': [{'label': "Peur de l'échec technique avec un petit matériel", 'weight': 37}],
     'aspirations': [{'label': 'Créer sans dépendre des abonnements', 'weight': 62}],
     'emotions': [{'label': 'confusion', 'weight': 37.4}]},
    {'source_id': 'sb', 'analysis_id': 'an-b', 'metadata': {'title': 'IA pour débutants'}, 'comment_stats': {'total_comments': 150},
     'fears': [{'label': 'Crainte de ne pas réussir la partie technique', 'weight': 41}],
     'aspirations': [{'label': 'Devenir autonome avec les outils IA', 'weight': 48}]},
]}


def test_les_profils_suivent_l_ordre_des_audiences_avec_leurs_lettres():
    profils = cs.build_source_profiles(CROSS)
    assert [(p['letter'], p['title'], p['analysis_id']) for p in profils] == [('A', 'IA locale', 'an-a'), ('B', 'IA pour débutants', 'an-b')]
    assert profils[0]['dimensions']['fears'][0] == {'label': "Peur de l'échec technique avec un petit matériel", 'weight': 37.0}


def test_un_rapprochement_ancre_dans_les_deux_audiences_est_garde_avec_les_intensites():
    parsed = {'rassemble': [{'dimension': 'fears', 'label': "Peur d'échouer techniquement", 'per_source': [
        {'source_id': 'sa', 'signal': "Peur de l'échec technique avec un petit matériel"},
        {'source_id': 'sb', 'signal': 'Crainte de ne pas réussir la partie technique'}]}]}
    out = cs.ground_synthesis(parsed, CROSS)
    assert len(out['rassemble']) == 1
    assert [p['weight'] for p in out['rassemble'][0]['per_source']] == [37.0, 41.0]
    assert out['validation']['rejected'] == 0


def test_un_signal_invente_ou_une_source_inconnue_est_retire_et_compte():
    parsed = {
        'rassemble': [{'dimension': 'fears', 'label': 'Inventé', 'per_source': [
            {'source_id': 'sa', 'signal': "Peur de l'échec technique avec un petit matériel"},
            {'source_id': 'sb', 'signal': 'Peur des requins'}]}],
        'sujets_qui_resolvent': [{'title': 'Sujet fantôme', 'source_ids': ['inconnue']}],
    }
    out = cs.ground_synthesis(parsed, CROSS)
    assert out['rassemble'] == [] and out['sujets_qui_resolvent'] == []
    assert out['validation']['rejected'] == 2


def test_la_synthese_est_indisponible_avec_une_seule_audience():
    assert cs.synthesize_cross({'source_analyses': CROSS['source_analyses'][:1]})['status'] == 'unavailable'


def test_la_synthese_complete_passe_par_la_verification(monkeypatch):
    import json
    reponse = {'verdict': {'rassemble': 'Autonomie', 'separe': 'Matériel', 'a_leur_dire': 'Pas à pas'},
               'rassemble': [{'dimension': 'aspirations', 'label': 'Autonomie', 'per_source': [
                   {'source_id': 'sa', 'signal': 'Créer sans dépendre des abonnements'},
                   {'source_id': 'sb', 'signal': 'Devenir autonome avec les outils IA'}]}],
               'message_commun': {'message': 'Une méthode vérifiable', 'nuances': [{'source_id': 'sb', 'nuance': 'Plus lent'}, {'source_id': 'zz', 'nuance': 'x'}]}}
    monkeypatch.setattr(cs, 'call_llm', lambda *a, **k: json.dumps(reponse))
    out = cs.synthesize_cross(CROSS)
    assert out['status'] == 'completed' and out['verdict']['a_leur_dire'] == 'Pas à pas'
    assert [n['source_id'] for n in out['message_commun']['nuances']] == ['sb']


def test_les_mots_vides_ne_deviennent_pas_des_centres_d_interet():
    cross = {'source_analyses': [
        {'source_id': 'sa', 'themes': [{'label': 'merci', 'weight': 40}, {'label': 'tes', 'weight': 20}, {'label': 'ComfyUI', 'weight': 28}]},
        {'source_id': 'sb', 'themes': [{'label': 'vidéo', 'weight': 17}, {'label': 'modèles de langage', 'weight': 12}]},
    ]}
    profils = cs.build_source_profiles(cross)
    assert [s['label'] for s in profils[0]['dimensions']['themes']] == ['ComfyUI']
    parsed = {'separe': [{'dimension': 'themes', 'label': 'DIY vs Communauté', 'kind': 'specifique',
                          'per_source': [{'source_id': 'sa', 'signal': 'tes'}, {'source_id': 'sb', 'signal': 'merci'}]}]}
    assert cs.ground_synthesis(parsed, cross)['separe'] == []


def test_cross_as_psycho_gives_the_creator_only_verified_cross_material():
    from core.cross_synthesis import cross_as_psycho
    from agents.createur import Createur
    result = {
        'source_profiles': [
            {'source_id': 's1', 'letter': 'A', 'title': 'IA locale', 'comments': 116},
            {'source_id': 's2', 'letter': 'B', 'title': 'IA débutants', 'comments': 87},
        ],
        'source_analyses': [
            {'source_id': 's1', 'evidence': [{'text': 'Il faut du matos haut de gamme', 'likes': 40},
                                             {'text': 'Promo http://pub.example', 'likes': 99}]},
            {'source_id': 's2', 'evidence': [{'text': 'Je débute et j’ai peur', 'likes': 3}]},
        ],
        'cross_synthesis': {
            'status': 'completed',
            'verdict': {'rassemble': 'Besoin de **maîtrise**', 'separe': 'A idéologique, B guidé', 'a_leur_dire': 'Vous pouvez créer'},
            'rassemble': [{'dimension': 'fears', 'label': 'Peur de l’échec', 'interpretation': 'Crainte partagée'}],
            'separe': [{'label': 'Technique vs. pédagogique', 'interpretation': 'A matériel, B social'}],
            'centres_interet': [{'label': 'Autonomie créative'}],
            'sujets_qui_resolvent': [{'title': 'Ateliers débutants', 'why': 'Rassure'}],
            'a_eviter': [{'label': 'Le jargon', 'why': 'Ils fuient'}],
            'message_commun': {'message': 'On vous guide', 'nuances': [{'source_id': 's2', 'nuance': 'Rassurer B'}]},
        },
    }
    psycho = cross_as_psycho(result)
    assert 'A = IA locale (116 commentaires)' in psycho['brief']['qui']
    assert psycho['brief']['insight'] == 'Besoin de maîtrise'
    assert psycho['psychologie']['peurs_implicites'] == ['Peur de l’échec — Crainte partagée']
    assert 'Audience B : Rassurer B' in psycho['recommandations']['nuances_par_audience']
    assert [c['text'] for c in psycho['top_comments']] == ['Il faut du matos haut de gamme', 'Je débute et j’ai peur']

    brief = Createur().build_writing_brief('script_video', 'youtube', 'direct', '', psycho, {}, None, {}, 'Un script')
    assert 'ne pas les fusionner' in brief and 'Audience B : Rassurer B' in brief
    assert 'Le jargon : Ils fuient' in brief and 'On vous guide' in brief
