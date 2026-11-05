"""Family Ops API: private, single-household request/approval service."""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

VERSION = '0.2.0'
ROLES = {'parent', 'teen', 'child'}
KINDS = {'app', 'bonus-time', 'buy', 'fix', 'idea', 'media', 'permission', 'picture', 'ride', 'surprise'}
OPEN = {'new', 'seen', 'needs_info'}
ALL_STATES = OPEN | {'approved', 'declined', 'done', 'expired', 'cancelled'}
ID = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32))


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def connect(path):
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    return db


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY, role TEXT NOT NULL, password TEXT NOT NULL, enabled INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, member TEXT REFERENCES members(id), expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS attempts(ip TEXT NOT NULL, at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS attempts_time ON attempts(at);
    CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, body TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, body TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, operation TEXT NOT NULL, target TEXT, hidden TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
    CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
    ''')
    db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('routing', json.dumps({'rules': [], 'default': {'deciders': [], 'policy': 'either'}, 'revision': 1})))
    db.close()
    os.chmod(path, 0o600)


def audit(db, actor, operation, target=None, hidden=None):
    db.execute('INSERT INTO audit(at,actor,operation,target,hidden) VALUES (?,?,?,?,?)', (now(), actor, operation, target, json.dumps(hidden or [])))


def set_member(path, member, role, password, enabled=False):
    if not ID.fullmatch(member) or role not in ROLES or not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('Valid member ID, supported person role and 12-256 character password required')
    initialize(path)
    db = connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO members VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET role=excluded.role,password=excluded.password,enabled=excluded.enabled', (member, role, generate_password_hash(password), int(enabled)))
        db.execute('DELETE FROM sessions WHERE member=?', (member,))
        audit(db, 'operator', 'setMember', member)
        db.commit()
    finally:
        db.close()


class APIError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def fail(status, code):
    raise APIError(status, code)


def fields(body, allowed, required=()):
    if not isinstance(body, dict) or set(body) - set(allowed) or set(required) - set(body):
        fail(400, 'invalid-fields')


def text(value, maximum, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        fail(400, 'invalid-text')
    return value


def timestamp(value):
    if not isinstance(value, str):
        fail(400, 'invalid-date')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.timestamp()
    except ValueError:
        fail(400, 'invalid-date')


def create_app(path=None):
    app = Flask(__name__)
    app.config.update(DB=path or os.environ.get('FAMILYOPS_DB', 'data/familyops.sqlite'), MAX_CONTENT_LENGTH=16384)
    initialize(app.config['DB'])

    @app.before_request
    def begin():
        g.db = connect(app.config['DB'])
        g.db.execute('BEGIN IMMEDIATE')
        if request.path == '/healthz' or (request.path == '/v1/auth/login' and request.method == 'POST'):
            return
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer ') or not 20 <= len(header[7:]) <= 256:
            fail(401, 'unauthorized')
        row = g.db.execute('SELECT members.id, role FROM sessions JOIN members ON member=members.id WHERE hash=? AND expires>? AND enabled=1', (digest(header[7:]), time.time())).fetchone()
        if row is None or row['role'] not in ROLES:
            fail(401, 'unauthorized')
        g.actor = dict(row)
        # Deadline is enforced before any read or decision, in this transaction.
        for row in g.db.execute('SELECT body FROM requests').fetchall():
            r = json.loads(row['body'])
            if r['status'] in OPEN and r.get('neededBy') and timestamp(r['neededBy']) <= time.time():
                r['status'] = 'expired'
                r['revision'] += 1
                save(r, 'expireRequest', 'system')

    @app.after_request
    def finish(response):
        if hasattr(g, 'db'):
            if response.status_code < 400 or getattr(g, 'commit_error', False):
                g.db.commit()
            else:
                g.db.rollback()
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
        return response

    @app.teardown_request
    def close(_):
        if hasattr(g, 'db'):
            g.db.close()

    def problem(status, code):
        response = jsonify(type='about:blank', title=code, status=status)
        response.status_code = status
        response.content_type = 'application/problem+json'
        return response

    @app.errorhandler(APIError)
    def expected(e):
        return problem(e.status, e.code)

    @app.errorhandler(HTTPException)
    def http_error(e):
        return problem(e.code, e.name.lower().replace(' ', '-'))

    @app.errorhandler(Exception)
    def unexpected(e):
        # No exception payloads: SQL, passwords or request bodies must not reach logs.
        app.logger.error('Request failed: %s', type(e).__name__)
        return problem(500, 'internal-error')

    def body():
        if not request.is_json:
            fail(415, 'json-required')
        return request.get_json()

    def parent():
        if g.actor['role'] != 'parent':
            fail(403, 'parent-required')

    def visible(r):
        actor = g.actor['id']
        return actor not in r.get('hiddenFrom', []) and (actor == r['requester'] or (g.actor['role'] == 'parent' and actor in r['deciders']))

    def load(rid):
        row = g.db.execute('SELECT body FROM requests WHERE id=?', (rid,)).fetchone()
        if not row:
            fail(404, 'not-found')
        r = json.loads(row['body'])
        if not visible(r):
            fail(404, 'not-found')
        return r

    def save(r, operation, actor=None):
        g.db.execute('INSERT INTO requests VALUES (?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', (r['id'], json.dumps(r)))
        audit(g.db, actor or g.actor['id'], operation, r['id'], r.get('hiddenFrom'))

    def revision(b, r):
        if type(b.get('revision')) is not int or b['revision'] < 1:
            fail(400, 'revision-required')
        if b['revision'] != r['revision']:
            fail(409, 'revision-conflict')

    @app.get('/healthz')
    def health():
        g.db.execute('SELECT 1').fetchone()
        return jsonify(status='ok', version=VERSION)

    @app.post('/v1/auth/login')
    def login():
        b = body()
        fields(b, {'username', 'password'}, {'username', 'password'})
        text(b['username'], 64, True)
        text(b['password'], 256, True)
        ip = request.remote_addr or 'unknown'
        t = time.time()
        g.db.execute('DELETE FROM attempts WHERE at<?', (t - 60,))
        if g.db.execute('SELECT count(*) FROM attempts WHERE ip=?', (ip,)).fetchone()[0] >= 10:
            g.commit_error = True
            fail(429, 'login-rate-limited')
        g.db.execute('INSERT INTO attempts VALUES (?,?)', (ip, t))
        m = g.db.execute('SELECT * FROM members WHERE id=?', (b['username'],)).fetchone()
        valid = check_password_hash(m['password'] if m else DUMMY_HASH, b['password'])
        if not valid or not m or not m['enabled'] or m['role'] not in ROLES:
            g.commit_error = True
            fail(401, 'unauthorized')
        token = secrets.token_urlsafe(32)
        g.db.execute('DELETE FROM sessions WHERE expires<=?', (t,))
        g.db.execute('INSERT INTO sessions VALUES (?,?,?)', (digest(token), m['id'], t + 3600))
        audit(g.db, m['id'], 'login')
        return jsonify(accessToken=token, tokenType='Bearer', expiresIn=3600)

    @app.post('/v1/auth/logout')
    def logout():
        g.db.execute('DELETE FROM sessions WHERE hash=?', (digest(request.headers['Authorization'][7:]),))
        audit(g.db, g.actor['id'], 'logout')
        return '', 204

    @app.get('/v1/me')
    def me():
        return jsonify(g.actor)

    @app.get('/v1/requests/routing-rules')
    def routing_get():
        parent()
        return jsonify(json.loads(g.db.execute("SELECT body FROM settings WHERE key='routing'").fetchone()[0]))

    @app.put('/v1/requests/routing-rules')
    def routing_set():
        parent()
        b = body()
        fields(b, {'rules', 'default', 'revision'}, {'rules', 'default', 'revision'})
        old = json.loads(g.db.execute("SELECT body FROM settings WHERE key='routing'").fetchone()[0])
        revision(b, old)
        if not isinstance(b['rules'], list) or len(b['rules']) > 100:
            fail(400, 'invalid-rules')
        for idx, rule in enumerate([b['default']] + b['rules']):
            allowed = {'deciders', 'policy'} | ({'fromRole', 'fromMember', 'kind'} if idx else set())
            fields(rule, allowed, {'deciders', 'policy'})
            ds = rule['deciders']
            if not isinstance(ds, list) or not ds or len(ds) > 10 or any(not isinstance(d, str) for d in ds) or len(set(ds)) != len(ds) or rule['policy'] not in ('either', 'both'):
                fail(400, 'invalid-routing')
            for d in ds:
                if not g.db.execute("SELECT 1 FROM members WHERE id=? AND role='parent' AND enabled=1", (d,)).fetchone():
                    fail(400, 'invalid-decider')
            if 'kind' in rule and (not isinstance(rule['kind'], str) or rule['kind'] not in KINDS):
                fail(400, 'invalid-kind')
            if 'fromRole' in rule and (not isinstance(rule['fromRole'], str) or rule['fromRole'] not in ROLES):
                fail(400, 'invalid-role')
            if 'fromMember' in rule and (not isinstance(rule['fromMember'], str) or not g.db.execute('SELECT 1 FROM members WHERE id=?', (rule['fromMember'],)).fetchone()):
                fail(400, 'invalid-member')
        b['revision'] += 1
        g.db.execute("UPDATE settings SET body=? WHERE key='routing'", (json.dumps(b),))
        audit(g.db, g.actor['id'], 'setRoutingRules')
        return jsonify(b)

    @app.post('/v1/requests')
    def create():
        b = body()
        fields(b, {'kind', 'title', 'details', 'neededBy', 'hiddenFrom'}, {'kind', 'title'})
        if not isinstance(b['kind'], str) or b['kind'] not in KINDS:
            fail(400, 'invalid-kind')
        text(b['title'], 200, True)
        if 'details' in b:
            text(b['details'], 2000)
        if 'neededBy' in b and timestamp(b['neededBy']) <= time.time():
            fail(400, 'deadline-in-past')
        hidden = b.get('hiddenFrom', [])
        if not isinstance(hidden, list) or len(hidden) > 100 or any(not isinstance(x, str) for x in hidden):
            fail(400, 'invalid-hidden-members')
        if hidden:
            parent()
            if b['kind'] != 'surprise' or g.actor['id'] in hidden:
                fail(400, 'invalid-hidden-members')
            for x in hidden:
                if not g.db.execute('SELECT 1 FROM members WHERE id=?', (x,)).fetchone():
                    fail(400, 'invalid-hidden-members')
        routing = json.loads(g.db.execute("SELECT body FROM settings WHERE key='routing'").fetchone()[0])
        chosen = routing['default']
        for rule in routing['rules']:
            if all(rule.get(k, v) == v for k, v in [('fromRole', g.actor['role']), ('fromMember', g.actor['id']), ('kind', b['kind'])]):
                chosen = rule
                break
        deciders = [d for d in chosen['deciders'] if d != g.actor['id'] and d not in hidden]
        if not deciders or any(not g.db.execute("SELECT 1 FROM members WHERE id=? AND role='parent' AND enabled=1", (d,)).fetchone() for d in deciders):
            fail(409, 'no-eligible-decider')
        r = dict(b, id=secrets.token_hex(16), requester=g.actor['id'], deciders=deciders, policy=chosen['policy'], status='new', decisions=[], createdAt=now(), revision=1)
        save(r, 'createRequest')
        return jsonify(r), 201

    @app.get('/v1/requests')
    def listing():
        unknown = set(request.args) - {'status', 'decider', 'cursor', 'limit'}
        if unknown or ('status' in request.args and request.args['status'] not in ALL_STATES):
            fail(400, 'invalid-query')
        try:
            limit = int(request.args.get('limit', 100))
            cursor = int(request.args.get('cursor', 0))
            if not 1 <= limit <= 200 or cursor < 0:
                raise ValueError()
        except ValueError:
            fail(400, 'invalid-pagination')
        records = [json.loads(x[0]) for x in g.db.execute('SELECT body FROM requests ORDER BY rowid')]
        records = [r for r in records if visible(r) and ('status' not in request.args or r['status'] == request.args['status']) and ('decider' not in request.args or request.args['decider'] in r['deciders'])]
        return jsonify(requests=records[cursor:cursor + limit], nextCursor=str(cursor + limit) if len(records) > cursor + limit else None)

    @app.get('/v1/requests/<rid>')
    def get_request(rid):
        r = load(rid)
        if g.actor['id'] in r['deciders'] and r['status'] == 'new':
            r['status'] = 'seen'
            r['revision'] += 1
            save(r, 'getRequest')
        return jsonify(r)

    @app.post('/v1/requests/<rid>/decisions')
    def decide(rid):
        parent()
        r = load(rid)
        b = body()
        fields(b, {'verdict', 'revision', 'note'}, {'verdict', 'revision'})
        if b['verdict'] not in ('approve', 'decline', 'needs_info'):
            fail(400, 'invalid-verdict')
        if 'note' in b:
            text(b['note'], 500)
        if g.actor['id'] not in r['deciders'] or g.actor['id'] == r['requester']:
            fail(403, 'not-a-decider')
        revision(b, r)
        if r['status'] not in ('new', 'seen') or any(d['decider'] == g.actor['id'] and d['verdict'] != 'needs_info' for d in r['decisions']):
            fail(409, 'illegal-transition')
        r['decisions'].append(dict(decider=g.actor['id'], verdict=b['verdict'], at=now(), via='session', note=b.get('note', '')))
        approved = {d['decider'] for d in r['decisions'] if d['verdict'] == 'approve'}
        r['status'] = {'decline': 'declined', 'needs_info': 'needs_info'}.get(b['verdict'], 'approved' if r['policy'] == 'either' or set(r['deciders']) <= approved else 'seen')
        r['revision'] += 1
        save(r, 'decideRequest')
        return jsonify(r)

    @app.post('/v1/requests/<rid>/<action>')
    def transition(rid, action):
        if action not in ('answer', 'cancel', 'complete'):
            fail(404, 'not-found')
        r = load(rid)
        b = body()
        fields(b, {'revision', 'details'} if action == 'answer' else {'revision'}, {'revision'})
        revision(b, r)
        if action == 'complete':
            if g.actor['id'] != r['requester'] and g.actor['id'] not in r['deciders']:
                fail(403, 'forbidden')
            if r['status'] != 'approved':
                fail(409, 'illegal-transition')
            r['status'] = 'done'
        else:
            if g.actor['id'] != r['requester']:
                fail(403, 'forbidden')
            if action == 'answer':
                if r['status'] != 'needs_info':
                    fail(409, 'illegal-transition')
                if 'details' in b:
                    r['details'] = text(b['details'], 2000)
                r['status'] = 'seen'
            else:
                if r['status'] not in OPEN:
                    fail(409, 'illegal-transition')
                r['status'] = 'cancelled'
        r['revision'] += 1
        save(r, action + 'Request')
        return jsonify(r)

    @app.get('/v1/audit')
    def audit_get():
        parent()
        if set(request.args) - {'cursor'}:
            fail(400, 'invalid-query')
        try:
            cursor = int(request.args.get('cursor', 0))
            if cursor < 0:
                raise ValueError()
        except ValueError:
            fail(400, 'invalid-cursor')
        rows = g.db.execute('SELECT * FROM audit WHERE id>? ORDER BY id LIMIT 101', (cursor,)).fetchall()
        entries = []
        for row in rows[:100]:
            if g.actor['id'] in json.loads(row['hidden']):
                entries.append({'id': row['id'], 'redacted': True})
            else:
                entries.append(dict(id=row['id'], at=row['at'], actor=row['actor'], actorKind='person' if row['actor'] != 'system' else 'service', operationId=row['operation'], targetId=row['target'], outcome='ok'))
        return jsonify(entries=entries, nextCursor=str(rows[99]['id']) if len(rows) > 100 else None)

    return app
