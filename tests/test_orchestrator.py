# ─── Gabriel — Tests Orchestrateur (routage d'intention + page) ───────────────
#
# Couvre le module agents/orchestrator (heuristique de routage, niveaux de
# réponse, handoff) et le rendu de la page /orchestrateur.
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_orchestrator.py -v

import os
import sys

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-orch'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.orchestrator import (
    classify_intent, build_recommendation, build_handoff, response_max_tokens, AGENTS,
)
import app as _app


def _client(uid='uid-orch'):
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = uid
        s['user_email'] = f'{uid}@example.com'
        s['user_name'] = 'Orch Tester'
    return c


# ══════════════════════════════════════════════════════════════════════════════
# 1. Routage d'intention — chaque bureau capté par ses mots-clés
# ══════════════════════════════════════════════════════════════════════════════
def test_intent_audience_routes_to_psychologue():
    it = classify_intent("Je veux comprendre ce que ressent mon audience")
    assert it['agent'] == 'psychologue'


def test_intent_decision_routes_to_stratege():
    it = classify_intent("Quelle est la bonne stratégie de positionnement ?", has_psycho=True)
    assert it['agent'] == 'stratege'


def test_intent_content_with_full_context_routes_to_createur():
    it = classify_intent("Crée-moi un post LinkedIn", has_psycho=True, has_strategy=True)
    assert it['agent'] == 'createur'


# ══════════════════════════════════════════════════════════════════════════════
# 2. Logique de parcours — ne pas sauter les étapes amont
# ══════════════════════════════════════════════════════════════════════════════
def test_content_without_upstream_reroutes_to_psychologue():
    """Créer du contenu sans audience ni stratégie → on renvoie au Psychologue d'abord."""
    it = classify_intent("Rédige une publicité", has_psycho=False, has_strategy=False)
    assert it['agent'] == 'psychologue'
    assert 'audience' in it['reason'].lower()


def test_content_with_psycho_only_reroutes_to_stratege():
    it = classify_intent("Rédige une publicité", has_psycho=True, has_strategy=False)
    assert it['agent'] == 'stratege'


# ══════════════════════════════════════════════════════════════════════════════
# 3. Niveaux de réponse
# ══════════════════════════════════════════════════════════════════════════════
def test_level_deep_on_reasoning_question():
    it = classify_intent("Pourquoi cette stratégie est-elle la bonne ?", has_psycho=True, has_strategy=True)
    assert it['level'] == 'deep'
    assert response_max_tokens('deep') > response_max_tokens('quick')


def test_level_quick_on_greeting():
    it = classify_intent("Bonjour")
    assert it['level'] == 'quick'
    assert it['agent'] is None  # un simple bonjour ne pousse pas de carte


# ══════════════════════════════════════════════════════════════════════════════
# 4. Recommandation — pas de carte vers un bureau déjà fait sans raison explicite
# ══════════════════════════════════════════════════════════════════════════════
def test_no_reco_for_greeting():
    it = classify_intent("Salut")
    assert build_recommendation(it) is None


def test_reco_has_expected_shape():
    it = classify_intent("Ma cible convient-elle à mon offre ?")
    reco = build_recommendation(it)
    assert reco is not None
    assert reco['agent'] in AGENTS
    assert reco['href'] == AGENTS[reco['agent']]['href']
    assert reco['cta'] and reco['label'] and reco['reason']


# ══════════════════════════════════════════════════════════════════════════════
# 5. Handoff — paquet compact, sérialisable
# ══════════════════════════════════════════════════════════════════════════════
def test_handoff_is_compact_and_serializable():
    import json
    h = build_handoff('psychologue', "Ma cible est-elle bonne ?",
                      business_context={'activite': 'Coaching', 'cible': 'PME'})
    assert h['target_agent'] == 'psychologue'
    assert h['source_agent'] == 'orchestrateur'
    assert h['known_context']['activite'] == 'Coaching'
    json.dumps(h)  # ne doit pas lever


# ══════════════════════════════════════════════════════════════════════════════
# 6. Page /orchestrateur — rendu, sans dossier requis
# ══════════════════════════════════════════════════════════════════════════════
def test_orchestrateur_page_renders_without_folder():
    c = _client()
    r = c.get('/orchestrateur')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="orch-page"' in html
    assert 'id="op-thread"' in html
    assert 'data-office="orchestrateur"' in html


# ══════════════════════════════════════════════════════════════════════════════
# 7. Route /orchestrator_chat — la réponse expose reply + level + recommendation
# ══════════════════════════════════════════════════════════════════════════════
def test_orchestrator_chat_returns_enriched_payload(monkeypatch):
    import json as _json

    class _FakeMsg:
        content = "Votre cible mérite d'être vérifiée sur des données réelles."
    class _FakeChoice:
        message = _FakeMsg()
    class _FakeResp:
        choices = [_FakeChoice()]
    class _FakeChat:
        def complete(self, **kwargs):
            return _FakeResp()
    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(_app, '_get_mistral_client', lambda timeout_ms=60000: _FakeClient())

    c = _client()
    r = c.post('/orchestrator_chat',
               data=_json.dumps({'message': "Je veux comprendre ce que ressent mon audience"}),
               content_type='application/json')
    assert r.status_code == 200
    d = r.get_json()
    assert d['reply']
    assert d['level'] in ('quick', 'deep')
    # Comprendre l'audience → oriente vers le Psychologue, avec handoff cohérent.
    assert d['recommendation'] is not None
    assert d['recommendation']['agent'] == 'psychologue'
    assert d['handoff']['target_agent'] == 'psychologue'
