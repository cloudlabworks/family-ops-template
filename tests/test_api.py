import concurrent.futures
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.app import connect, create_app, digest, set_member


CAPTURE = []

class API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.TemporaryDirectory()
        cls.base = str(Path(cls.root.name) / 'base.sqlite')
        cls.passwords = {u: secrets.token_urlsafe(24) for u in ['parent-a', 'parent-b', 'parent-c', 'teen-a', 'child-a', 'disabled']}
        for u, pw in cls.passwords.items():
            role = 'parent' if u.startswith('parent') else ('teen' if u == 'teen-a' else 'child')
            set_member(cls.base, u, role, pw, enabled=u != 'disabled')

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()
        if os.environ.get("FAMILYOPS_CONTRACT_CAPTURE"):
            Path(os.environ["FAMILYOPS_CONTRACT_CAPTURE"]).write_text(json.dumps(CAPTURE))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'test.sqlite')
        shutil.copyfile(self.base, self.path)
        self.app = create_app(self.path)
        self.client = self.app.test_client()
        self.tokens = {}
        for u in ('parent-a', 'parent-b', 'parent-c', 'teen-a', 'child-a'):
            result = self.client.post('/v1/auth/login', json={'username': u, 'password': self.passwords[u]})
            self.assertEqual(result.status_code, 200)
            self.tokens[u] = result.json['accessToken']
        self.configure()

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, path, user='teen-a', body=None, status=200):
        result = self.client.open('/v1' + path, method=method, json=body, headers={'Authorization': 'Bearer ' + self.tokens[user]})
        self.assertEqual(result.status_code, status, result.json)
        CAPTURE.append({'method': method.lower(), 'path': path.split('?')[0], 'status': result.status_code, 'body': result.json})
        return result.json

    def configure(self, policy='either'):
        current = self.call('GET', '/requests/routing-rules', 'parent-a')
        return self.call('PUT', '/requests/routing-rules', 'parent-a', {'rules': [], 'default': {'deciders': ['parent-a', 'parent-b', 'parent-c'], 'policy': policy}, 'revision': current['revision']})

    def create(self, user='teen-a', **extra):
        return self.call('POST', '/requests', user, dict(kind='ride', title='Ride to the library', **extra), 201)

    def decision(self, r, user='parent-a', verdict='approve', status=200):
        return self.call('POST', '/requests/' + r['id'] + '/decisions', user, {'verdict': verdict, 'revision': r['revision']}, status)

    def test_complete_workflow_and_restart(self):
        r = self.create()
        r = self.decision(r)
        self.assertEqual(r['status'], 'approved')
        r = self.call('POST', '/requests/' + r['id'] + '/complete', body={'revision': r['revision']})
        self.assertEqual(r['status'], 'done')
        self.client = create_app(self.path).test_client()
        self.assertEqual(self.call('GET', '/requests/' + r['id'])['status'], 'done')
        entries = self.call('GET', '/audit', 'parent-a')['entries']
        self.assertTrue(any(e.get('operationId') == 'completeRequest' for e in entries))

    def test_both_policy_and_duplicate_decision(self):
        self.configure('both')
        r = self.create()
        r = self.decision(r)
        self.assertEqual(r['status'], 'seen')
        self.decision(r, status=409)
        r = self.decision(r, 'parent-b')
        self.assertEqual(r['status'], 'seen')
        r = self.decision(r, 'parent-c')
        self.assertEqual(r['status'], 'approved')

    def test_decline_final(self):
        self.configure('both')
        r = self.decision(self.create())
        r = self.decision(r, 'parent-b', 'decline')
        self.assertEqual(r['status'], 'declined')
        self.decision(r, 'parent-c', status=409)

    def test_needs_info_answer(self):
        r = self.decision(self.create(), verdict='needs_info')
        self.call('POST', '/requests/' + r['id'] + '/answer', 'parent-a', {'revision': r['revision']}, 403)
        r = self.call('POST', '/requests/' + r['id'] + '/answer', body={'revision': r['revision'], 'details': 'At noon'})
        self.assertEqual(self.decision(r)['status'], 'approved')

    def test_child_cannot_decide_or_spoof_parent(self):
        r = self.create('child-a')
        self.decision(r, 'child-a', status=403)
        result = self.client.post('/v1/requests/' + r['id'] + '/decisions', json={'verdict': 'approve', 'revision': 1}, headers={'X-Role': 'parent', 'X-User': 'parent-a'})
        self.assertEqual(result.status_code, 401)
        self.call('POST', '/requests', body={'kind': 'ride', 'title': 'Spoof', 'requester': 'parent-a'}, status=400)
        self.call('POST', '/requests', body={'kind': 'ride', 'title': 'Spoof', 'onBehalfOf': 'parent-a'}, status=400)

    def test_hidden_request_and_audit(self):
        r = self.call('POST', '/requests', 'parent-a', {'kind': 'surprise', 'title': 'A surprise', 'hiddenFrom': ['parent-b']}, 201)
        self.assertEqual(r['deciders'], ['parent-c'])
        self.call('GET', '/requests/' + r['id'], 'parent-b', status=404)
        self.assertEqual(self.call('GET', '/requests', 'parent-b')['requests'], [])
        entries = self.call('GET', '/audit', 'parent-b')['entries']
        self.assertNotIn(r['id'], json.dumps(entries))
        self.assertTrue(any(e.get('redacted') for e in entries))

    def test_cross_member_visibility(self):
        r = self.create()
        self.call('GET', '/requests/' + r['id'], 'child-a', status=404)
        self.assertEqual(self.call('GET', '/requests', 'child-a')['requests'], [])
        self.call('GET', '/audit', 'teen-a', status=403)

    def test_self_approval_and_frozen_routing(self):
        r = self.create('parent-a')
        self.assertNotIn('parent-a', r['deciders'])
        self.decision(r, status=403)
        r = self.create()
        old_deciders = r['deciders']
        self.configure('both')
        reread = self.call('GET', '/requests/' + r['id'])
        self.assertEqual(reread['policy'], 'either')
        self.assertEqual(reread['deciders'], old_deciders)

    def test_stale_revision(self):
        r = self.create()
        seen = self.call('GET', '/requests/' + r['id'], 'parent-a')
        self.assertGreater(seen['revision'], r['revision'])
        self.decision(r, status=409)
        self.assertEqual(self.decision(seen)['status'], 'approved')

    def test_concurrent_decisions_only_one_wins(self):
        r = self.create()
        def act(user):
            with self.app.test_client() as c:
                return c.post('/v1/requests/' + r['id'] + '/decisions', json={'revision': r['revision'], 'verdict': 'approve'}, headers={'Authorization': 'Bearer ' + self.tokens[user]}).status_code
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            codes = list(pool.map(act, ['parent-a', 'parent-b']))
        self.assertEqual(sorted(codes), [200, 409])

    def test_cancel_and_deadline(self):
        r = self.create()
        r = self.call('POST', '/requests/' + r['id'] + '/cancel', body={'revision': r['revision']})
        self.assertEqual(r['status'], 'cancelled')
        self.decision(r, status=409)
        r = self.create(neededBy=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
        db = connect(self.path)
        r['neededBy'] = '2000-01-01T00:00:00Z'
        db.execute('UPDATE requests SET body=? WHERE id=?', (json.dumps(r), r['id']))
        db.close()
        self.assertEqual(self.call('GET', '/requests/' + r['id'])['status'], 'expired')

    def test_disabled_expired_and_logout(self):
        result = self.client.post('/v1/auth/login', json={'username': 'disabled', 'password': self.passwords['disabled']})
        self.assertEqual(result.status_code, 401)
        self.call('POST', '/auth/logout', status=204)
        self.call('GET', '/me', status=401)
        db = connect(self.path)
        db.execute('UPDATE sessions SET expires=0 WHERE hash=?', (digest(self.tokens['child-a']),))
        db.close()
        self.call('GET', '/me', 'child-a', status=401)

    def test_password_reset_revokes_sessions(self):
        set_member(self.path, 'teen-a', 'teen', secrets.token_urlsafe(24), True)
        self.call('GET', '/me', status=401)

    def test_login_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.client.post('/v1/auth/login', json={'username': 'absent', 'password': 'invalid-test-input'}).status_code, 401)
        self.assertEqual(self.client.post('/v1/auth/login', json={'username': 'absent', 'password': 'invalid-test-input'}).status_code, 429)

    def test_validation_and_unknown_routes(self):
        for b in [{'kind': [], 'title': 'x'}, {'kind': {}, 'title': 'x'}, {'kind': 'unknown', 'title': 'x'}, {'kind': 'ride', 'title': ''}, {'kind': 'ride', 'title': 'x', 'neededBy': 'tomorrow'}, {'kind': 'ride', 'title': 'x', 'hiddenFrom': ['parent-a']}]:
            expected = 403 if b.get('hiddenFrom') else 400
            self.call('POST', '/requests', body=b, status=expected)
        self.call('POST', '/requests', body=['x'], status=400)
        self.call('GET', '/requests?cursor=-1', status=400)
        self.call('GET', '/house/scenes', status=404)
        self.call('POST', '/requests/x/channel-decisions', body={}, status=404)
        huge = self.client.post('/v1/requests', data='x' * 20000, content_type='application/json', headers={'Authorization': 'Bearer ' + self.tokens['teen-a']})
        self.assertEqual(huge.status_code, 413)

    def test_sqlite_backup_and_append_only_audit(self):
        r = self.create()
        db = connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('DELETE FROM audit')
        dstpath = str(Path(self.tmp.name) / 'restore.sqlite')
        dst = sqlite3.connect(dstpath)
        db.backup(dst)
        dst.close()
        db.close()
        self.client = create_app(dstpath).test_client()
        self.assertEqual(self.call('GET', '/requests/' + r['id'])['id'], r['id'])

    def test_tokens_not_stored_plaintext(self):
        db = connect(self.path)
        stored = '\n'.join(x[0] for x in db.execute('SELECT hash FROM sessions'))
        self.assertNotIn(self.tokens['teen-a'], stored)
        db.close()
        self.assertEqual(self.client.get('/healthz').status_code, 200)


if __name__ == '__main__':
    unittest.main()
