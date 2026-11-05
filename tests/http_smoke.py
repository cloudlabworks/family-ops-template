"""Real HTTP + process restart + backup/restore check; no token/password output."""
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from server.app import set_member


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / 'familyops.sqlite')
        passwords = {u: secrets.token_urlsafe(24) for u in ('parent-a', 'parent-b', 'child-a')}
        for u, password in passwords.items():
            set_member(db, u, 'child' if u == 'child-a' else 'parent', password, True)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        base = 'http://localhost:' + str(port)
        http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def call(method, path, data=None, token=None):
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
            with http.open(req, timeout=5) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        def start(path):
            proc = subprocess.Popen([sys.executable, '-m', 'gunicorn', '--bind', '127.0.0.1:' + str(port), '--workers', '1', '--threads', '4', 'server.app:create_app()'], env=dict(os.environ, FAMILYOPS_DB=path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(80):
                if proc.poll() is not None:
                    raise RuntimeError('Server exited during startup')
                try:
                    if call('GET', '/healthz')['status'] == 'ok':
                        return proc
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(.1)
            proc.terminate()
            proc.wait(10)
            raise RuntimeError('Server readiness timeout')
        p = start(db)
        try:
            tokens = {u: call('POST', '/v1/auth/login', {'username': u, 'password': pw})['accessToken'] for u, pw in passwords.items()}
            call('PUT', '/v1/requests/routing-rules', {'rules': [], 'default': {'deciders': ['parent-a', 'parent-b'], 'policy': 'both'}, 'revision': 1}, tokens['parent-a'])
            r = call('POST', '/v1/requests', {'kind': 'ride', 'title': 'Synthetic library ride'}, tokens['child-a'])
            for u in ('parent-a', 'parent-b'):
                r = call('POST', '/v1/requests/' + r['id'] + '/decisions', {'verdict': 'approve', 'revision': r['revision']}, tokens[u])
            assert r['status'] == 'approved'
            r = call('POST', '/v1/requests/' + r['id'] + '/complete', {'revision': r['revision']}, tokens['child-a'])
            assert r['status'] == 'done'
            p.terminate()
            p.wait(10)
            p = start(db)
            assert call('GET', '/v1/requests/' + r['id'], token=tokens['child-a'])['status'] == 'done'
            backup = str(Path(tmp) / 'restore.sqlite')
            subprocess.run([sys.executable, '-m', 'server.manage', '--db', db, 'backup', backup], check=True, stdout=subprocess.DEVNULL)
            p.terminate()
            p.wait(10)
            p = start(backup)
            assert call('GET', '/v1/requests/' + r['id'], token=tokens['child-a'])['status'] == 'done'
            assert any(e.get('operationId') == 'completeRequest' for e in call('GET', '/v1/audit', token=tokens['parent-a'])['entries'])
            print(json.dumps({'http_workflow': 'pass', 'two_parent_policy': 'pass', 'process_restart_persistence': 'pass', 'operator_backup_restore': 'pass', 'audit': 'pass'}))
        finally:
            if p.poll() is None:
                p.terminate()
                p.wait(10)


if __name__ == '__main__':
    run()
