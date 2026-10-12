"""Non-regression tests for credit-store failures (CR-02 / CR-03 only).

All persistence and provider interactions are local fakes. The database tests
run with the Python standard library; Flask integration tests are skipped when
the application's declared dependencies are not installed locally.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-credit-fail-closed')
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['AUTH_ENABLED'] = 'true'
os.environ['RATE_LIMIT_ENABLED'] = 'false'
os.environ['NLP_PRELOAD'] = 'false'
os.environ['RAG_PRELOAD'] = 'false'

import api.db as _db
import api.auth as _auth

try:
    import app as _app
    _APP_IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # local environment may lack app dependencies
    _app = None
    _APP_IMPORT_ERROR = exc


class _Result:
    def __init__(self, data):
        self.data = data


class _CreditTable:
    def __init__(self, *, selected=None, updated=None, select_error=None,
                 update_error=None):
        self.selected = selected
        self.updated = updated
        self.select_error = select_error
        self.update_error = update_error
        self.mode = None

    def select(self, *_args, **_kwargs):
        self.mode = 'select'
        return self

    def update(self, *_args, **_kwargs):
        self.mode = 'update'
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self.mode == 'select':
            if self.select_error:
                raise self.select_error
            return _Result(self.selected)
        if self.update_error:
            raise self.update_error
        return _Result(self.updated)


class _CreditSupabase:
    def __init__(self, table):
        self.credit_table = table

    def table(self, _name):
        return self.credit_table


class CreditStoreUnitTests(unittest.TestCase):
    def test_supabase_read_failure_is_not_replaced_by_free_credits(self):
        fake = _CreditSupabase(_CreditTable(select_error=RuntimeError('offline')))
        with patch.object(_db, '_supabase', fake):
            with self.assertRaises(_db.CreditStoreUnavailable):
                _db.get_user_credits('existing-user')

    def test_nonexistent_user_is_distinct_from_unavailable_store(self):
        fake = _CreditSupabase(_CreditTable(selected=[]))
        with patch.object(_db, '_supabase', fake):
            with self.assertRaises(_db.CreditAccountNotFound):
                _db.get_user_credits('unknown-user')

    def test_missing_balance_is_distinct_from_nonexistent_user(self):
        fake = _CreditSupabase(_CreditTable(selected=[{'credits': None}]))
        with patch.object(_db, '_supabase', fake):
            with self.assertRaises(_db.CreditBalanceMissing):
                _db.get_user_credits('user-without-balance')

    def test_persisted_new_account_keeps_its_signup_credits(self):
        with tempfile.TemporaryDirectory() as directory:
            uid = 'new-local-user'
            users_file = Path(directory) / 'users.json'
            users_file.write_text(json.dumps({
                uid: {'user_id': uid, 'credits': _db.DEFAULT_FREE_CREDITS},
            }), encoding='utf-8')
            with patch.object(_db, '_supabase', None), \
                    patch.object(_db, '_DATA_DIR', directory):
                self.assertEqual(
                    _db.get_user_credits(uid),
                    _db.DEFAULT_FREE_CREDITS,
                )

    def test_historical_google_key_is_resolved_by_persisted_user_id(self):
        with tempfile.TemporaryDirectory() as directory:
            uid = 'google-user-uuid'
            users_file = Path(directory) / 'users.json'
            users_file.write_text(json.dumps({
                'google-sub': {'user_id': uid, 'credits': 300},
            }), encoding='utf-8')
            with patch.object(_db, '_supabase', None), \
                    patch.object(_db, '_DATA_DIR', directory):
                self.assertEqual(_db.deduct_credits(uid, 80, 'test'), 220)
                persisted = json.loads(users_file.read_text(encoding='utf-8'))
                self.assertEqual(persisted['google-sub']['credits'], 220)

    def test_supabase_write_failure_is_never_reported_as_a_new_balance(self):
        fake = _CreditSupabase(_CreditTable(
            selected=[{'credits': 300}],
            update_error=RuntimeError('write refused'),
        ))
        with patch.object(_db, '_supabase', fake):
            with self.assertRaises(_db.CreditDeductionFailed):
                _db.deduct_credits('existing-user', 80, reason='psychologue')

    def test_supabase_update_of_zero_rows_is_a_failed_deduction(self):
        fake = _CreditSupabase(_CreditTable(
            selected=[{'credits': 300}],
            updated=[],
        ))
        with patch.object(_db, '_supabase', fake):
            with self.assertRaises(_db.CreditDeductionFailed):
                _db.deduct_credits('deleted-user', 80, reason='psychologue')

    def test_supabase_confirmed_update_returns_persisted_balance(self):
        fake = _CreditSupabase(_CreditTable(
            selected=[{'credits': 300}],
            updated=[{'credits': 220}],
        ))
        with patch.object(_db, '_supabase', fake):
            self.assertEqual(
                _db.deduct_credits('existing-user', 80, reason='psychologue'),
                220,
            )

    def test_local_dev_account_is_provisioned_once_without_resetting_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            users_file = Path(directory) / 'users.json'
            dev_environment = {
                'AUTH_ENABLED': 'false',
                'GABRIEL_ENV': 'development',
                'RENDER': '',
                'RENDER_EXTERNAL_URL': '',
            }
            with patch.dict(os.environ, dev_environment), \
                    patch.object(_auth, '_supabase', None), \
                    patch.object(_auth, '_USERS_FILE', str(users_file)), \
                    patch.object(_auth, '_dev_user_provisioned', False), \
                    patch.object(_db, '_supabase', None), \
                    patch.object(_db, '_DATA_DIR', directory):
                _auth._ensure_dev_user_row()
                self.assertEqual(
                    _db.get_user_credits(_auth._DEV_USER['user_id']),
                    _db.DEFAULT_FREE_CREDITS,
                )

                self.assertEqual(
                    _db.deduct_credits(
                        _auth._DEV_USER['user_id'],
                        _db.CREDIT_COSTS['psychologue'],
                        reason='test',
                    ),
                    220,
                )

                # Simulate another process start: provisioning must detect the
                # existing account and must never restore its credits to 300.
                _auth._dev_user_provisioned = False
                _auth._ensure_dev_user_row()
                self.assertEqual(
                    _db.get_user_credits(_auth._DEV_USER['user_id']),
                    220,
                )

    def test_dev_account_is_never_provisioned_in_production(self):
        with tempfile.TemporaryDirectory() as directory:
            users_file = Path(directory) / 'users.json'
            class _ForbiddenSupabase:
                called = False

                def table(self, _name):
                    self.called = True
                    raise AssertionError('production must not provision the dev account')

            fake_supabase = _ForbiddenSupabase()
            production_environment = {
                'AUTH_ENABLED': 'false',
                'GABRIEL_ENV': 'production',
                'RENDER': 'true',
                'RENDER_EXTERNAL_URL': 'https://example.invalid',
            }
            with patch.dict(os.environ, production_environment), \
                    patch.object(_auth, '_supabase', fake_supabase), \
                    patch.object(_auth, '_USERS_FILE', str(users_file)), \
                    patch.object(_auth, '_dev_user_provisioned', False):
                _auth._ensure_dev_user_row()
                self.assertFalse(fake_supabase.called)
                self.assertFalse(users_file.exists())


@unittest.skipIf(_app is None, f'application dependencies unavailable: {_APP_IMPORT_ERROR}')
class CreditRouteIntegrationTests(unittest.TestCase):
    def _client(self, uid='credit-fail-closed-user'):
        client = _app.app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = uid
            session['user_email'] = f'{uid}@example.com'
        return client

    def test_paid_route_refuses_to_start_when_credit_store_is_unavailable(self):
        def unavailable(*_args, **_kwargs):
            raise _db.CreditStoreUnavailable('offline')

        with patch.object(_db, 'check_usage_limit', return_value={'allowed': True}), \
                patch.object(_db, 'has_enough_credits', side_effect=unavailable):
            response = self._client().post('/analyze', json={
                'source': 'text',
                'content': 'Commentaire un\nCommentaire deux\nCommentaire trois',
            })

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['error_code'], 'credits_unavailable')

    def test_paid_route_reports_an_unprovisioned_account_as_a_conflict(self):
        def account_not_found(*_args, **_kwargs):
            raise _db.CreditAccountNotFound('missing')

        with patch.object(_db, 'check_usage_limit', return_value={'allowed': True}), \
                patch.object(_db, 'has_enough_credits', side_effect=account_not_found):
            response = self._client().post('/analyze', json={
                'source': 'text',
                'content': 'Commentaire un\nCommentaire deux\nCommentaire trois',
            })

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()['error_code'],
            'credit_account_not_provisioned',
        )

    def test_creator_job_is_failed_when_deduction_was_not_persisted(self):
        persisted_states = []

        def update_job(_job_id, **fields):
            persisted_states.append(fields.get('status'))
            return True

        def deduction_failed(*_args, **_kwargs):
            raise _db.CreditDeductionFailed('write refused')

        import agents.creation as creation
        patches = (
            patch.object(_db, 'has_enough_credits', return_value=True),
            patch.object(_db, 'create_job', return_value=True),
            patch.object(_db, 'update_job', side_effect=update_job),
            patch.object(_db, 'deduct_credits', side_effect=deduction_failed),
            patch.object(_app, '_resolve_psycho', return_value={}),
            patch.object(_app, '_resolve_strategy', return_value={}),
            patch.object(_app, '_resolve_business_context', return_value={}),
            patch.object(
                creation,
                'generate_result',
                return_value={'success': True, 'full_text': 'generated'},
            ),
        )
        with patches[0], patches[1], patches[2], patches[3], \
                patches[4], patches[5], patches[6], patches[7]:
            response = self._client().post('/creator/generate', json={
                'content_type': 'youtube',
                'user_request': 'Un script de test',
            })
            job_id = response.get_json()['job_id']
            for _ in range(100):
                state = (_app._jobs.get(job_id) or {}).get('status')
                if state in {'done', 'error'}:
                    break
                time.sleep(0.01)

        self.assertEqual((_app._jobs.get(job_id) or {}).get('status'), 'error')
        self.assertNotIn('completed', persisted_states)
        self.assertIn('failed', persisted_states)
        _app._jobs.pop(job_id, None)


if __name__ == '__main__':
    unittest.main()
