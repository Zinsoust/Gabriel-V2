"""Ariane ne doit plus reposer indéfiniment la même question.

Observé le 13/09/2026 : réponses précises (« Offre : formation présentielle
2 jours… Cible : dirigeant de PME… »), mais l'extraction échouait (modèle
refusé en 403, erreur avalée) — Ariane reformulait « Quelle est la
proposition concrète ? » à chaque tour. Deux garde-fous :
  - une panne technique est dite comme telle, sans compter le tour ;
  - au 3e tour sur une même dimension, la réponse est retenue telle quelle
    et l'entretien avance.
"""
from agents.context_builder import orchestrator as orch


class FauxStockage:
    def __init__(self):
        self.messages, self.fields, self.session = [], {}, {'session_id': 's1', 'current_dimension': 'identity'}

    def installer(self, monkeypatch):
        db = orch.db
        monkeypatch.setattr(db, 'get_active_context_session', lambda uid: dict(self.session))
        monkeypatch.setattr(db, 'get_context_fields', lambda uid: dict(self.fields))
        monkeypatch.setattr(db, 'create_context_session', lambda *a, **k: None)
        monkeypatch.setattr(db, 'get_context_messages', lambda sid, uid: list(self.messages))
        monkeypatch.setattr(db, 'save_context_message',
                            lambda sid, uid, role, content, dimension_key='': self.messages.append(
                                {'role': role, 'content': content, 'dimension_key': dimension_key}))
        monkeypatch.setattr(db, 'upsert_context_field', lambda uid, k, v, source_session_id=None: self.fields.__setitem__(k, v))

        def maj(sid, uid, **k):
            self.session.update({kk: vv for kk, vv in k.items() if kk == 'current_dimension'})
        monkeypatch.setattr(db, 'update_context_session', maj)
        tr = orch.tr
        monkeypatch.setattr(tr, 'render_followup', lambda ext, labels, missing: {'display_text': 'RELANCE ' + ', '.join(missing)})
        monkeypatch.setattr(tr, 'render_transition', lambda ext, labels, q: {'display_text': 'SUITE ' + q[:20]})
        monkeypatch.setattr(tr, 'render_clarification', lambda rej, q: {'display_text': 'PRÉCISEZ'})
        monkeypatch.setattr(tr, 'render_completion', lambda f: {'display_text': 'FINI'})


REPONSE = "Offre : formation présentielle 2 jours + suivi email 30 jours. Cible : dirigeants de PME."


def test_une_dimension_n_est_jamais_demandee_plus_de_trois_fois(monkeypatch):
    stock = FauxStockage(); stock.installer(monkeypatch)
    rien = {'extracted': {}, 'rejected_vague': [], 'failed': False}
    monkeypatch.setattr(orch.ae, 'extract_answer_freeform', lambda msg, known: rien)
    monkeypatch.setattr(orch.ae, 'extract_answer', lambda dim, msg, known: rien)

    reponses = [orch.handle_message('u1', REPONSE)['reply']['display_text'] for _ in range(3)]

    assert reponses[0].startswith('RELANCE') and reponses[1].startswith('RELANCE')
    assert reponses[2].startswith('SUITE'), "au 3e tour, l'entretien doit passer à la dimension suivante"
    assert stock.session['current_dimension'] == 'vision'
    for cle in ('offer', 'target', 'format'):
        assert stock.fields[cle] == REPONSE, "la réponse de l'utilisateur est retenue telle quelle, rien d'inventé"


def test_une_esquive_repetee_est_notee_comme_non_precisee(monkeypatch):
    stock = FauxStockage(); stock.installer(monkeypatch)
    stock.messages = [{'role': 'user', 'content': 'bonjour', 'dimension_key': 'identity'}] * 2
    monkeypatch.setattr(orch.ae, 'extract_answer', lambda dim, msg, known: {'extracted': {}, 'rejected_vague': ["Identité"], 'failed': False})

    orch.handle_message('u1', 'je sais pas')

    assert stock.fields['offer'].startswith('Non précisé par le dirigeant')
    assert stock.session['current_dimension'] == 'vision'


def test_une_panne_du_modele_est_dite_et_ne_compte_pas_comme_un_tour(monkeypatch):
    stock = FauxStockage(); stock.installer(monkeypatch)
    stock.messages = [{'role': 'user', 'content': 'x', 'dimension_key': 'identity'}]
    monkeypatch.setattr(orch.ae, 'extract_answer', lambda dim, msg, known: {'extracted': {}, 'rejected_vague': [], 'failed': True})

    payload = orch.handle_message('u1', REPONSE)

    assert payload['extraction_failed'] is True
    assert 'technique' in payload['reply']['display_text']
    assert stock.fields == {}
    assert stock.session['current_dimension'] == 'identity'
    assert stock.messages[-2] == {'role': 'user', 'content': REPONSE, 'dimension_key': ''}


def test_l_extracteur_distingue_une_panne_d_un_json_vide(monkeypatch):
    from agents.context_builder import answer_extractor as ae

    def refus(*a, **k):
        raise RuntimeError('403 tier_not_allowed')
    monkeypatch.setattr(ae, '_call_llm', refus)
    assert ae.extract_answer('identity', REPONSE, {})['failed'] is True
    assert ae.extract_answer_freeform(REPONSE, {})['failed'] is True

    monkeypatch.setattr(ae, '_call_llm', lambda *a, **k: '{}')
    assert ae.extract_answer('identity', REPONSE, {})['failed'] is False
