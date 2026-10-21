"""Prospect remains unavailable in production even if its dev flag leaks."""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_prospect_routes_are_not_registered_in_production():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update({
        'FLASK_SECRET_KEY': 'test-production-prospect-disabled-long-enough',
        'AUTH_ENABLED': 'true',
        'RATE_LIMIT_ENABLED': 'true',
        'GABRIEL_ENV': 'production',
        'GABRIEL_PROSPECT_ENABLED': 'true',
        'NLP_PRELOAD': 'false',
        'RAG_PRELOAD': 'false',
        'MISTRAL_API_KEY': 'test-key',
        'OPENAI_API_KEY': '',
        'SUPABASE_URL': '',
        'SUPABASE_KEY': '',
        'SUPABASE_SERVICE_ROLE_KEY': '',
    })
    code = (
        "import json, app; "
        "rules=[r.rule for r in app.app.url_map.iter_rules() if 'prospect' in r.rule]; "
        "print(json.dumps({'enabled': app._PROSPECT_ENABLED, 'routes': rules}))"
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {'enabled': False, 'routes': []}
