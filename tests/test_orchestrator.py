# ─── Gabriel — Tests Orchestrateur (routage d'intention + page) ───────────────
#
# Couvre le module agents/orchestrator (heuristique de routage, niveaux de
# réponse, handoff) et le rendu de la page /orchestrateur.
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_orchestrator.py -v

import os
import sys
from pathlib import Path
import pytest

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-orch'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.orchestrator import (
    classify_intent, build_recommendation, build_handoff, response_max_tokens, AGENTS,
    build_mental_model, decide_help, build_response_directive, validate_response,
    build_mission, update_conversation_memory, format_conversation_memory,
    plan_context_access,
)
import app as _app


@pytest.fixture(autouse=True)
def _no_real_orchestrator_session_writes(monkeypatch):
    """Les tests de route ne doivent pas écrire dans les conversations utilisateur."""
    store = []
    monkeypatch.setattr(_app, '_get_user_conversations', lambda user_id: store)
    monkeypatch.setattr(
        _app, '_save_user_conversations',
        lambda user_id, conversations: store.__setitem__(slice(None), conversations),
    )


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
    assert it['agent'] is None  # une critique transversale reste chez l'Orchestrateur
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
# 4b. Contrat de mission — Gabriel sélectionne l'agent, le front l'exécute
# ══════════════════════════════════════════════════════════════════════════════
def test_youtube_audience_mission_is_ready_and_uses_existing_pipeline():
    intent = classify_intent('Analyse cette audience : https://youtu.be/abc123')
    mission = build_mission(intent, 'Analyse cette audience : https://youtu.be/abc123', 'm-1')
    assert mission['status'] == 'ready'
    assert mission['selected_agents'][0]['id'] == 'psychologue'
    assert mission['execution']['endpoint'] == '/api/v2/agents/psychologue/analyze'
    assert mission['execution']['payload']['source'] == 'youtube'


def test_audience_mission_without_data_waits_without_fake_execution():
    intent = classify_intent("Je veux comprendre mon audience")
    mission = build_mission(intent, "Je veux comprendre mon audience", 'm-2')
    assert mission['status'] == 'awaiting_input'
    assert 'execution' not in mission


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
    assert 'id="gabriel-v2-root"' in html
    assert 'gabriel-v2/app.css' in html
    assert 'gabriel-v2/app.js' in html
    assert 'window.__GABRIEL_V2__' in html


def test_v2_bootstrap_exposes_a_stable_workspace_contract():
    c = _client()
    r = c.get('/api/v2/bootstrap')
    assert r.status_code == 200
    payload = r.get_json()
    assert payload['success'] is True
    assert payload['api_version'] == 'v2'
    assert isinstance(payload['workspaces'], list)
    assert set(payload['user']) == {'name', 'email'}


def test_v2_bootstrap_keeps_the_hall_neutral_until_a_workspace_is_explicit():
    """Un ancien dossier ne doit pas s'ouvrir à la place du Hall."""
    folder = {
        'folder_id': 'existing-workspace', 'title': 'Ancien dossier',
        'folder_type': 'workspace', 'status': 'active', 'step': 'conversation',
    }
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_app._db, 'get_folders', lambda user_id: [folder])
        response = _client().get('/api/v2/bootstrap')

    assert response.status_code == 200
    assert response.get_json()['workspace'] is None


def test_v2_first_message_creates_and_returns_its_workspace(monkeypatch):
    """Le premier message du Hall crée le conteneur avant les agents."""
    created = {}

    def _create_folder(folder_id, user_id, title, objective='', folder_type='audience'):
        created['folder'] = {
            'folder_id': folder_id,
            'user_id': user_id,
            'title': title,
            'objective': objective,
            'folder_type': folder_type,
            'status': 'active',
            'step': 'conversation',
        }
        return created['folder']

    monkeypatch.setattr(_app._db, 'create_folder', _create_folder)
    monkeypatch.setattr(
        _app._db, 'get_folder_by_id',
        lambda folder_id, user_id: created.get('folder') if folder_id == created.get('folder', {}).get('folder_id') else None,
    )
    monkeypatch.setattr(_app, '_call_openai_orchestrator', lambda **kwargs: 'Réponse dans le nouveau workspace.')

    response = _client().post('/api/v2/conversations/messages', json={
        'message': 'Faut-il revoir le prix de mon offre ?',
    })

    assert response.status_code == 200
    payload = response.get_json()
    assert created['folder']['title'] == 'Nouvelle conversation'
    assert payload['workspace_created'] is True
    assert payload['workspace']['folder_id'] == created['folder']['folder_id']
    assert payload['workspace']['agents']['psychologue']['status'] == 'ready'


def test_v2_greeting_uses_the_workspace_created_in_the_same_request(monkeypatch):
    """Le raccourci de salutation garde le même contrat que le flux complet."""
    created = {}

    def _create_folder(folder_id, user_id, title, objective='', folder_type='audience'):
        created['folder'] = {
            'folder_id': folder_id, 'user_id': user_id, 'title': title,
            'folder_type': folder_type, 'status': 'active', 'step': 'conversation',
        }
        return created['folder']

    monkeypatch.setattr(_app._db, 'create_folder', _create_folder)
    # Simule une lecture différée de la base juste après l'insertion.
    monkeypatch.setattr(_app._db, 'get_folder_by_id', lambda folder_id, user_id: None)
    response = _client().post('/api/v2/conversations/messages', json={'message': 'Bonjour'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['reply'].startswith('Bonjour.')
    assert payload['workspace_created'] is True
    assert payload['workspace']['folder_id'] == created['folder']['folder_id']


def test_v2_uploaded_comments_prepare_an_executable_psychologue_mission(monkeypatch):
    """Le fichier déjà normalisé rejoint le pipeline Psychologue sans UI factice."""
    created = {}

    def _create_folder(folder_id, user_id, title, objective='', folder_type='audience'):
        created['folder'] = {
            'folder_id': folder_id, 'user_id': user_id, 'title': title,
            'folder_type': folder_type, 'status': 'active', 'step': 'conversation',
        }
        return created['folder']

    monkeypatch.setattr(_app._db, 'create_folder', _create_folder)
    monkeypatch.setattr(
        _app._db, 'get_folder_by_id',
        lambda folder_id, user_id: created.get('folder') if folder_id == created.get('folder', {}).get('folder_id') else None,
    )
    monkeypatch.setattr(_app, '_call_openai_orchestrator', lambda **kwargs: 'Je prépare cette analyse d’audience.')

    response = _client().post('/api/v2/conversations/messages', json={
        'message': 'Analyse ce fichier de commentaires.',
        'uploaded_source': {
            'filename': 'retours-clients.csv',
            'comments': [
                {'text': 'Je ne sais pas quelle offre choisir.'},
                {'text': 'Le prix reste difficile à comprendre.'},
                {'text': 'J’aimerais un accompagnement plus concret.'},
            ],
        },
    })

    assert response.status_code == 200
    mission = response.get_json()['mission']
    assert mission['status'] == 'ready'
    assert mission['selected_agents'][0]['id'] == 'psychologue'
    assert mission['execution']['payload']['source'] == 'file'
    assert len(mission['execution']['payload']['comments']) == 3


def test_vite_proxy_covers_integrated_agent_requests():
    """En développement, aucun appel iframe ne doit tomber sur le fallback HTML."""
    config = (Path(__file__).resolve().parents[1] / 'frontend-react' / 'vite.gabriel-v2.config.js').read_text()
    for route in ('/upload-comments-file', '/history', '/strategies', '/business-context', '/voice', '/feedback'):
        assert f"'{route}'" in config


# ══════════════════════════════════════════════════════════════════════════════
# 7. Route /orchestrator_chat — la réponse expose reply + level + recommendation
# ══════════════════════════════════════════════════════════════════════════════
def test_orchestrator_chat_returns_enriched_payload(monkeypatch):
    import json as _json
    monkeypatch.setattr(
        _app, '_call_openai_orchestrator',
        lambda **kwargs: "Votre cible mérite d'être vérifiée sur des données réelles.",
    )

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


def test_v2_conversation_route_keeps_the_orchestrator_contract(monkeypatch):
    monkeypatch.setattr(_app, '_call_openai_orchestrator', lambda **kwargs: 'Réponse V2.')
    response = _client().post('/api/v2/conversations/messages', json={
        'message': 'Faut-il augmenter mes prix pour améliorer la rentabilité de mon offre ?',
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['reply'] == 'Réponse V2.'
    assert payload['conversation_id']


def test_v2_first_message_accepts_an_empty_persisted_session(monkeypatch):
    """Une conversation inexistante ne doit jamais provoquer un HTTP 500."""
    workspace = {
        'folder_id': 'workspace-first-message',
        'title': 'Nouvelle conversation',
        'folder_type': 'workspace',
        'status': 'active',
        'step': 'conversation',
    }
    monkeypatch.setattr(_app._db, 'create_folder', lambda *args, **kwargs: workspace)
    monkeypatch.setattr(_app._db, 'get_folder_by_id', lambda *args, **kwargs: workspace)
    monkeypatch.setattr(_app._db, 'get_orchestrator_session_state', lambda *args, **kwargs: {})
    monkeypatch.setattr(_app._db, 'save_orchestrator_session', lambda *args, **kwargs: True)

    response = _client().post('/api/v2/conversations/messages', json={'message': 'hello'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['reply'].startswith('Bonjour.')
    assert payload['workspace']['id'] == workspace['folder_id']


def test_orchestrator_persists_mission_contract_for_the_conversation(monkeypatch):
    monkeypatch.setattr(_app, '_call_openai_orchestrator', lambda **kwargs: 'Je lance la bonne lecture de cette audience.')
    c = _client('uid-mission')
    response = c.post('/orchestrator_chat', json={
        'message': 'Analyse cette audience : https://youtu.be/abc123',
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['mission']['status'] == 'ready'
    assert payload['mission']['execution']['endpoint'] == '/api/v2/agents/psychologue/analyze'

    restored = c.get(
        f"/api/orchestrator/missions/{payload['mission']['id']}?conversation_id={payload['conversation_id']}"
    )
    assert restored.status_code == 200
    assert restored.get_json()['mission']['id'] == payload['mission']['id']


def test_local_server_without_openai_key_keeps_a_ready_mission_usable(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(
        _app, '_call_openai_orchestrator',
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError('OPENAI_API_KEY manquante')),
    )
    response = _client().post('/orchestrator_chat', json={
        'message': 'Analyse cette audience : https://youtu.be/abc123',
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['mode'] == 'conversation_fallback'
    assert payload['mission']['status'] == 'ready'
    assert 'lancer' in payload['reply'].lower()


def test_orchestrator_never_returns_500_when_the_model_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        _app, '_call_openai_orchestrator',
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError('fournisseur indisponible')),
    )

    response = _client().post('/api/v2/conversations/messages', json={
        'message': 'Aide-moi à structurer mon offre.',
    })

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['mode'] == 'conversation_fallback'
    assert payload['conversation_id']
    assert payload['reply']


def test_greeting_is_local_natural_and_ignores_stale_session(monkeypatch):
    """Un salut ne paie pas un appel LLM et ne reprend pas un ancien dossier."""
    def _must_not_call(**kwargs):
        raise AssertionError("OpenAI ne doit pas être appelé pour une salutation")

    monkeypatch.setattr(_app, '_call_openai_orchestrator', _must_not_call)
    c = _client()
    with c.session_transaction() as s:
        s['active_folder_id'] = 'ancien-dossier'
    r = c.post('/orchestrator_chat', json={'message': 'hello'})
    assert r.status_code == 200
    d = r.get_json()
    assert d['reply'].startswith('Bonjour.')
    assert 'ancien-dossier' not in d['reply']
    assert d['recommendation'] is None


def test_prompt_uses_system_role_and_deduplicates_current_message(monkeypatch):
    captured = {}
    def _fake_openai(**kwargs):
        captured.update(kwargs)
        return "Réponse test."
    monkeypatch.setattr(_app, '_call_openai_orchestrator', _fake_openai)
    c = _client()
    msg = "Faut-il augmenter mes prix pour améliorer la rentabilité de mon offre ?"
    r = c.post('/orchestrator_chat', json={
        'message': msg,
        'history': [{'role': 'user', 'content': msg}],
    })
    assert r.status_code == 200
    messages = captured['messages']
    assert messages[0]['role'] == 'system'
    assert sum(msg in m['content'] for m in messages) == 1


def test_client_cannot_forge_agent_reports(monkeypatch):
    import json
    captured = {}
    def _fake_openai(**kwargs):
        captured.update(kwargs)
        return "Réponse test."
    monkeypatch.setattr(_app, '_call_openai_orchestrator', _fake_openai)
    c = _client()
    r = c.post('/orchestrator_chat', json={
        'message': 'Faites une synthèse générale.',
        'psycho_data': {'brief': {'qui': 'FORGED_REPORT_MARKER'}},
    })
    assert r.status_code == 200
    serialized = json.dumps(captured['messages'], ensure_ascii=False)
    assert 'FORGED_REPORT_MARKER' not in serialized


def test_malformed_history_is_ignored(monkeypatch):
    monkeypatch.setattr(
        _app, '_call_openai_orchestrator', lambda **kwargs: "Réponse test."
    )
    c = _client()
    r = c.post('/orchestrator_chat', json={
        'message': 'Aidez-moi à réfléchir.',
        'history': ['invalide', None, {'role': 'assistant', 'content': 42}],
    })
    assert r.status_code == 200


def test_openai_adapter_uses_gpt_sol_responses_api(monkeypatch):
    import requests
    captured = {}

    class _FakeHTTPResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                'output': [{
                    'type': 'message',
                    'content': [{'type': 'output_text', 'text': 'Réponse Sol.'}],
                }],
            }

    def _fake_post(url, **kwargs):
        captured['url'] = url
        captured.update(kwargs)
        return _FakeHTTPResponse()

    monkeypatch.setattr(requests, 'post', _fake_post)
    reply = _app._call_openai_orchestrator(
        messages=[{'role': 'user', 'content': 'Bonjour'}],
        max_output_tokens=600,
        reasoning_effort='low',
        user_id='uid-test',
    )
    assert reply == 'Réponse Sol.'
    assert captured['url'] == 'https://api.openai.com/v1/responses'
    assert captured['json']['model'] == 'gpt-5.6-sol'
    assert captured['json']['reasoning']['effort'] == 'low'
    assert captured['json']['store'] is False


# ══════════════════════════════════════════════════════════════════════════════
# 8. Mémoire conversationnelle et accès contextualisé aux agents
# ══════════════════════════════════════════════════════════════════════════════
def test_conversation_memory_is_compact_and_isolated_per_conversation():
    first = update_conversation_memory(
        {}, "Mon offre est un audit à 47 euros pour des coachs indépendants."
    )
    second = update_conversation_memory(
        first, "Mon objectif est de valider ce prix avant la fin du mois."
    )
    fresh = update_conversation_memory({}, "Quel prix recommandez-vous ?")

    rendered = format_conversation_memory(second)
    assert "audit à 47 euros" in rendered
    assert "valider ce prix" in rendered
    # Une nouvelle conversation ne récupère aucune information de la première.
    assert "audit à 47 euros" not in format_conversation_memory(fresh)


def test_context_access_opens_only_the_requested_agent_reports():
    availability = {'psychologue': True, 'stratege': True, 'createur': True}
    direct = plan_context_access(
        "Aidez-moi à clarifier mon offre.",
        {'kind': 'specialist_request', 'agent': 'stratege'}, availability, {},
    )
    synthese = plan_context_access(
        "Faites une synthèse de l'analyse, de la stratégie et du contenu.",
        {'kind': 'transversal', 'agent': None}, availability, {},
    )
    targeted = plan_context_access(
        "Quel risque voyez-vous dans cette décision ?",
        {'kind': 'conversation', 'agent': None}, availability, {},
    )

    assert direct['agents'] == []
    assert synthese['agents'] == ['psychologue', 'stratege', 'createur']
    assert targeted['agents'] == ['stratege']


def test_orchestrator_restores_prior_offer_memory_without_repeating_current_message(monkeypatch):
    calls = []

    def _fake_openai(**kwargs):
        calls.append(kwargs)
        return "Je vous recommande de tester ce prix avec une cohorte pilote."

    monkeypatch.setattr(_app, '_call_openai_orchestrator', _fake_openai)
    client = _client('uid-memory')
    first = client.post('/orchestrator_chat', json={
        'message': 'Mon offre est un audit à 47 euros pour des coachs indépendants.',
    }).get_json()
    second = client.post('/orchestrator_chat', json={
        'message': 'Quel prix recommandez-vous pour cette offre ?',
        'conversation_id': first['conversation_id'],
    })

    assert second.status_code == 200
    serialized = str(calls[-1]['messages'])
    assert 'Mon offre est un audit à 47 euros' in serialized
    assert sum('Quel prix recommandez-vous pour cette offre ?' in str(item) for item in calls[-1]['messages']) == 1


def test_orchestrator_loads_specialist_reports_only_for_a_requested_synthesis(monkeypatch):
    calls = []
    workspace = {
        'folder_id': 'workspace-shared-context', 'title': 'Offre audit',
        'objective': 'Valider une offre', 'analysis_id': 'psy-1',
        'strategy_id': 'str-1', 'creator_output_id': 'cre-1', 'step': 'createur',
    }
    monkeypatch.setattr(_app._db, 'get_folder_by_id', lambda *args: workspace)
    monkeypatch.setattr(
        _app._db, 'get_analysis_by_id',
        lambda *args: calls.append('psychologue') or {
            'folder_id': 'workspace-shared-context',
            'full_result': {'brief': {'qui': 'Coachs', 'insight': 'Ils cherchent de la clarté'}},
        },
    )
    monkeypatch.setattr(
        _app._db, 'get_strategy_by_id',
        lambda *args: calls.append('stratege') or {
            'folder_id': 'workspace-shared-context',
            'strategy_result': {'decision_centrale': 'Vendre un audit court'},
        },
    )
    monkeypatch.setattr(
        _app._db, 'get_job',
        lambda *args, **kwargs: calls.append('createur') or {
            'folder_id': 'workspace-shared-context',
            'result_data': {'writing_brief': {'format': 'Post LinkedIn'}, 'full_text': 'Texte prêt.'},
        },
    )
    captured = {}
    monkeypatch.setattr(
        _app, '_call_openai_orchestrator',
        lambda **kwargs: captured.update(kwargs) or 'Les trois productions convergent sur un audit court.',
    )

    response = _client('uid-context').post('/orchestrator_chat', json={
        'message': "Faites une synthèse de l'analyse, de la stratégie et du contenu.",
        'folder_id': 'workspace-shared-context', 'conversation_id': 'context-1',
    })

    assert response.status_code == 200
    assert calls == ['psychologue', 'stratege', 'createur']
    reference = str(captured['messages'])
    assert 'ANALYSE DU PSYCHOLOGUE' in reference
    assert 'STRATÉGIE DU STRATÈGE' in reference
    assert 'PRODUCTION DU CRÉATEUR' in reference


def test_orchestrator_does_not_eagerly_load_reports_for_a_normal_question(monkeypatch):
    workspace = {
        'folder_id': 'workspace-direct-question', 'title': 'Offre audit',
        'analysis_id': 'psy-1', 'strategy_id': 'str-1', 'creator_output_id': 'cre-1',
    }
    monkeypatch.setattr(_app._db, 'get_folder_by_id', lambda *args: workspace)

    def _must_not_read_report(*args, **kwargs):
        raise AssertionError('Un rapport ne doit pas être relu sans demande explicite.')

    monkeypatch.setattr(_app._db, 'get_analysis_by_id', _must_not_read_report)
    monkeypatch.setattr(_app._db, 'get_strategy_by_id', _must_not_read_report)
    monkeypatch.setattr(_app._db, 'get_job', _must_not_read_report)
    monkeypatch.setattr(
        _app, '_call_openai_orchestrator',
        lambda **kwargs: 'Je commencerais par tester une promesse plus précise.',
    )

    response = _client('uid-direct').post('/orchestrator_chat', json={
        'message': "Aidez-moi à clarifier mon offre.",
        'folder_id': 'workspace-direct-question', 'conversation_id': 'direct-1',
    })

    assert response.status_code == 200
    assert response.get_json()['reply']


def test_orchestrator_keeps_foreign_workspace_output_out_of_context(monkeypatch):
    workspace = {'folder_id': 'workspace-a', 'analysis_id': 'psy-foreign'}
    monkeypatch.setattr(_app._db, 'get_folder_by_id', lambda *args: workspace)
    monkeypatch.setattr(
        _app._db, 'get_analysis_by_id',
        lambda *args: {'folder_id': 'workspace-b', 'full_result': {'brief': {'qui': 'Interdit'}}},
    )

    state = _app._orchestrator_load_context(
        'workspace-a', 'uid-security', include_agents=['psychologue']
    )

    assert state['psycho_data'] == {}
    assert state['loaded_agents'] == []


# ══════════════════════════════════════════════════════════════════════════════
# 9. Pipeline V1 — Mental Model, décision, personnalité et validation
# ══════════════════════════════════════════════════════════════════════════════
def test_mental_model_asks_one_targeted_question_when_request_is_ambiguous():
    intent = classify_intent("Je veux avancer")
    model = build_mental_model(
        "Je veux avancer", {}, None,
        {'psychologue': False, 'stratege': False, 'createur': False}, intent,
    ).to_dict()
    assert model['niveau_confiance'] <= 0.35
    assert model['question_validation']
    assert model['question_validation'].count('?') == 1
    assert model['donnees_manquantes']
    decision = decide_help("Je veux avancer", intent, model).to_dict()
    assert decision['action'] == 'clarify'
    assert decision['use_web'] is False


def test_mental_model_does_not_interrogate_a_specific_request():
    message = "Quelle stratégie de prix recommandez-vous pour cette offre ?"
    intent = classify_intent(message, has_psycho=True)
    model = build_mental_model(
        message, {'activite': 'SaaS'}, {'objective': 'Rentabilité'},
        {'psychologue': True, 'stratege': False, 'createur': False}, intent,
    ).to_dict()
    assert model['question_validation'] is None
    assert model['objectif'] == 'Rentabilité'
    assert 'psychologue' in model['analyses_existantes']


def test_mental_model_accepts_a_short_answer_to_its_previous_question():
    message = "Augmenter mes ventes"
    intent = classify_intent(message)
    history = [
        {'role': 'user', 'content': 'Je veux avancer'},
        {'role': 'assistant', 'content': 'Quel résultat business cherchez-vous à obtenir ?'},
    ]
    model = build_mental_model(
        message, {}, None, {}, intent, session_history=history
    ).to_dict()
    assert model['question_validation'] is None


def test_decision_enables_web_only_for_current_information():
    message = "Quelles sont les tendances actuelles de ce marché ?"
    intent = classify_intent(message)
    model = build_mental_model(message, {}, None, {}, intent).to_dict()
    decision = decide_help(message, intent, model).to_dict()
    assert decision['action'] == 'research_then_answer'
    assert decision['use_web'] is True


def test_decision_enables_web_for_an_explicit_business_web_request():
    message = "Cherche sur Internet les concurrents directs de cette offre."
    intent = classify_intent(message)
    model = build_mental_model(message, {}, None, {}, intent).to_dict()
    decision = decide_help(message, intent, model).to_dict()
    assert decision['use_web'] is True


def test_response_planner_preserves_gabriel_personality():
    directive = build_response_directive(
        {'action': 'answer_directly', 'specialist': None},
        {'niveau_confiance': 0.8},
    )
    assert 'consultant senior' in directive
    assert 'calme' in directive
    assert 'flatterie' in directive


def test_validator_removes_document_heading_and_tone_cliche():
    result = validate_response("# Analyse\nSuper ! Voici mon avis.")
    assert result['valid'] is True
    assert not result['reply'].startswith('#')
    assert 'Super !' not in result['reply']


def test_route_returns_clarification_without_llm(monkeypatch):
    monkeypatch.setattr(
        _app, '_call_openai_orchestrator',
        lambda **kwargs: (_ for _ in ()).throw(AssertionError('appel LLM interdit')),
    )
    r = _client().post('/orchestrator_chat', json={'message': 'Je veux avancer'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['reply'].endswith('?')
    assert data['recommendation'] is None
    assert data['conversation_id']


def test_route_reuses_persisted_session_history(monkeypatch):
    calls = []
    def _fake_openai(**kwargs):
        calls.append(kwargs)
        return "Je vous recommande de tester cette décision."
    monkeypatch.setattr(_app, '_call_openai_orchestrator', _fake_openai)
    client = _client('uid-session')
    first = client.post('/orchestrator_chat', json={
        'message': 'Faut-il augmenter le prix de mon offre ?',
    }).get_json()
    second = client.post('/orchestrator_chat', json={
        'message': 'Et quel est le risque principal ?',
        'conversation_id': first['conversation_id'],
    })
    assert second.status_code == 200
    serialized = str(calls[-1]['messages'])
    assert 'augmenter le prix de mon offre' in serialized


def test_openai_adapter_adds_web_tool_only_when_requested(monkeypatch):
    import requests
    captured = {}

    class _FakeHTTPResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                'id': 'resp_test',
                'usage': {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15},
                'output': [{'type': 'message', 'content': [
                    {'type': 'output_text', 'text': 'Réponse sourcée.'},
                ]}],
            }

    def _fake_post(url, **kwargs):
        captured.update(kwargs)
        return _FakeHTTPResponse()

    monkeypatch.setattr(requests, 'post', _fake_post)
    result = _app._call_openai_orchestrator(
        messages=[{'role': 'user', 'content': 'Tendances actuelles ?'}],
        max_output_tokens=600, reasoning_effort='low', use_web=True,
        return_metadata=True,
    )
    assert captured['json']['tools'] == [{'type': 'web_search'}]
    assert result['usage']['total_tokens'] == 15


def test_orchestrator_uses_mistral_when_openai_is_not_configured(monkeypatch):
    """Le hall V2 reste conversationnel dans l'environnement local Mistral."""
    from types import SimpleNamespace

    captured = {}

    response = SimpleNamespace(
        id='mistral-test',
        usage={'prompt_tokens': 12, 'completion_tokens': 8, 'total_tokens': 20},
        choices=[SimpleNamespace(message=SimpleNamespace(content='Réponse Mistral de Gabriel.'))],
    )

    class _FakeChat:
        def complete(self, **kwargs):
            captured.update(kwargs)
            return response

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setenv('MISTRAL_API_KEY', 'test-key')
    monkeypatch.setattr(_app, '_get_mistral_client', lambda **kwargs: _FakeClient())

    result = _app._call_openai_orchestrator(
        messages=[{'role': 'system', 'content': 'Vous êtes Gabriel.'}, {'role': 'user', 'content': 'Bonjour'}],
        max_output_tokens=600,
        reasoning_effort='low',
        use_web=True,
        return_metadata=True,
    )

    assert result['reply'] == 'Réponse Mistral de Gabriel.'
    assert result['provider'] == 'mistral_fallback'
    assert result['usage']['total_tokens'] == 20
    from core.llm_client import model_for_tier
    assert captured['model'] == model_for_tier('deep')
    assert captured['retries'] is None
    assert any('recherche web n\'est pas disponible' in item['content'] for item in captured['messages'])


def test_orchestrator_mistral_fallback_uses_persistent_budget(monkeypatch, tmp_path):
    """The direct SDK fallback cannot bypass the campaign ledger."""
    import json
    import sqlite3
    from types import SimpleNamespace

    model = 'mistral-test-202610'
    ledger = tmp_path / 'orchestrator-budget.sqlite3'
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setenv('MISTRAL_API_KEY', 'test-key')
    monkeypatch.setenv('MISTRAL_VALIDATION_BUDGET_ENABLED', 'true')
    monkeypatch.setenv('MISTRAL_VALIDATION_RUN_ID', 'orchestrator-test')
    monkeypatch.setenv('MISTRAL_VALIDATION_BUDGET_USD', '1.00')
    monkeypatch.setenv('MISTRAL_VALIDATION_MAX_ATTEMPTS', '2')
    monkeypatch.setenv('MISTRAL_VALIDATION_LEDGER_PATH', str(ledger.resolve()))
    monkeypatch.setenv('MISTRAL_VALIDATION_PRICING_JSON', json.dumps({model: {
        'input_usd_per_million': '0.10',
        'output_usd_per_million': '1.00',
    }}))
    monkeypatch.setattr(_app, '_llm_model_for_tier', lambda tier: model)

    response = SimpleNamespace(
        id='mistral-budget-test',
        model=model,
        usage={'prompt_tokens': 12, 'completion_tokens': 8, 'total_tokens': 20},
        choices=[SimpleNamespace(message=SimpleNamespace(content='Reponse locale.'))],
    )

    class _FakeChat:
        def complete(self, **kwargs):
            return response

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(_app, '_get_mistral_client', lambda **kwargs: _FakeClient())
    result = _app._call_openai_orchestrator(
        messages=[{'role': 'user', 'content': 'Bonjour'}],
        max_output_tokens=100,
        reasoning_effort='low',
        return_metadata=True,
    )
    assert result['reply'] == 'Reponse locale.'
    with sqlite3.connect(ledger) as conn:
        row = conn.execute(
            'SELECT provider, model, label, status FROM mistral_budget_attempts'
        ).fetchone()
    assert row == ('mistral', model, 'orchestrator_fallback', 'settled')
