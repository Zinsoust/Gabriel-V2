"""Landing du repositionnement : le Psychologue en héros, une promesse
défendable (signaux observables), des limites visibles, un parcours qui
mène à l'espace Psychologue."""
import os

os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-landing')
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')

import app as _app


def _page():
    r = _app.app.test_client().get('/')
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_landing_presents_gabriel_as_human_behaviour_analysis():
    html = _page()
    assert "analyse du comportement humain" in html.lower()
    assert "Psychologie avancée" in html
    assert "Découvrez le marché caché, les peurs et les aspirations" in html
    assert '<meta name="description"' in html


def test_landing_keeps_the_promise_defensible():
    html = _page()
    assert "Aucune pensée devinée" in html
    assert "Aucun diagnostic" in html
    for promesse_intenable in ("lit dans les pensées", "connaît le cœur", "diagnostic psychologique précis"):
        assert promesse_intenable not in html


def test_landing_names_gabriel_ai_as_a_multi_agent_system_led_by_the_psychologue():
    html = _page()
    assert "Gabriel<span>.ai</span>" in html
    assert "Système multi-agents" in html
    assert "Agent principal" in html
    assert "Gabriel <span>· Psychologue</span>" not in html


def test_landing_leads_to_the_psychologue_and_keeps_the_other_agents():
    html = _page()
    assert 'href="/login"' in html
    assert "Ariane, la stratège" in html and "Le Créateur" in html


def test_previous_landing_stays_reachable():
    r = _app.app.test_client().get('/landing-classique')
    assert r.status_code == 200
    assert "Prenez la bonne décision" in r.get_data(as_text=True)
