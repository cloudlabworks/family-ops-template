# Self-host Family Ops Requests API 0.2.0

A working example: a child asks for a library ride, a parent approves in their own session, and the child marks the ride complete. Each mutation writes an audit entry in the same SQLite transaction.

This release is a **single-household requests/approvals service** for private deployment. It is not the entire 74-operation blueprint and is not an internet-ready hosted SaaS. No service account can impersonate a parent. No device-control integrations or messaging callbacks are enabled.

## Start with Docker Compose

Requires Docker Engine with Compose v2 (Docker Desktop or an equivalent Linux-container runtime), outbound access for the initial image build, and a local port 8080. ARM64 and AMD64 base images are available; see release notes for architectures actually tested.

```sh
git clone https://github.com/cloudlabworks/family-ops-template.git
cd family-ops-template
git checkout v0.2.0
docker compose up --build -d
docker compose exec api python -m server.manage user-set parent-a --role parent --enable
docker compose exec api python -m server.manage user-set parent-b --role parent --enable
docker compose exec api python -m server.manage user-set child-a --role child --enable
```

Each command prompts for a password twice, with hidden input. Choose separate passwords of 12-256 characters. There are no default credentials. Member IDs above are synthetic; choose your own locally. Without `--enable`, the profile remains disabled. Enabling a child's profile is the responsible adult's opt-in decision.

The service binds **only to the Docker host's loopback port 8080**, not the public internet. Check:

```sh
curl --fail http://localhost:8080/healthz
```

## Complete your first request

The interactive client below keeps the password and token out of terminal output, saves neither, and logs out after each command. Its JSON argument is for non-secret request data only.

Set who can decide new requests (the empty default deliberately prevents unrouted requests):

```sh
docker compose exec api python -m server.client --user parent-a --json '{"rules":[],"default":{"deciders":["parent-a","parent-b"],"policy":"either"},"revision":1}' PUT /v1/requests/routing-rules
```

Create a request:

```sh
docker compose exec api python -m server.client --user child-a --json '{"kind":"ride","title":"Ride to the library","details":"Saturday afternoon"}' POST /v1/requests
```

Copy the returned `id` and `revision`. Replace `REQUEST_ID` below with that id. Use the **current** revision, initially 1. Opening a new request as a parent changes it to `seen` and increments revision, so re-read before retrying a conflict.

```sh
docker compose exec api python -m server.client --user parent-a --json '{"verdict":"approve","revision":1}' POST /v1/requests/REQUEST_ID/decisions
```

The response is `approved`, with revision 2 if no intervening read occurred:

```sh
docker compose exec api python -m server.client --user child-a --json '{"revision":2}' POST /v1/requests/REQUEST_ID/complete
docker compose exec api python -m server.client --user parent-a GET /v1/audit
```

`both` policy requires every frozen decider to approve. Any decline ends the request. A `needs_info` verdict lets the requester answer via `/v1/requests/REQUEST_ID/answer`, with current revision and optional `details`.

## API contract and scope

Use [the runnable OpenAPI contract](../openapi/runtime.yaml), not the larger design contract.

| Implemented | Behavior |
|---|---|
| Login, logout, identity | Opaque one-hour bearer sessions; password hashes and session-token hashes only in SQLite; immediate revocation on password reset/disable |
| Requests | Create, visible listing, detail, answer, cancel, complete, deadline expiry on authenticated API access |
| Decisions | Frozen routing; either/both policy; no self-approval; stale revision and duplicate-decision rejection |
| Hidden surprises | Parent-created only; hidden people cannot read request/details or identifying audit entries |
| Routing and audit | Parent-only routing updates; append-only audit API and DB triggers; paginated reads |

Supported runtime roles: parent, teen, child. No visitor schedules, young-child accounts, kiosks, service delegation or signed channel quick replies in this release. Unknown routes return 404, not simulated success. Calendar, chores, allowance, groceries, media, gaming enforcement, home automation and device controls remain blueprint-only. There is no browser UI yet.

## Private remote use

Keep the default loopback binding. For another device, use a private authenticated mesh VPN or an SSH tunnel. Put HTTPS in front of any non-loopback access: bearer tokens and passwords must not cross an unencrypted shared network. Do not publish router ports or treat this small-household service as a public multi-tenant product.

No CORS allowance, cookie authentication or trusted identity headers are enabled. Identity is resolved from server-issued tokens, never user-supplied role or on-behalf-of fields. Login is capped at ten attempts per remote address per minute. Behind a proxy, all clients may share that quota: the service deliberately does not trust forwarded IP headers. Operate privately; review edge rate limits before a wider deployment.

## Backup, recovery and retirement

SQLite runs in a named Docker volume with WAL. Use the online backup command, not a copy of only the live main database file:

```sh
docker compose exec api python -m server.manage backup /data/familyops-backup.sqlite
docker compose cp api:/data/familyops-backup.sqlite ./familyops-backup.sqlite
```

Backups include sensitive household records and password/session hashes. Encrypt them and keep a separate off-host copy. The command refuses to overwrite an existing destination; use a new filename for each backup. Root access to the host/database can bypass the audit triggers, so this is not a cryptographically tamper-proof audit log.

Restore to a **new** volume first, preserving the old volume. Stop the API, place the backup at `/data/familyops.sqlite` in the new volume with ownership UID/GID 10001, change the Compose volume reference, start and verify records before retiring anything. Never place a backup over a running SQLite database or mix it with old WAL files. Prefer `user-set` to rotate passwords and revoke restored sessions before use.

```sh
docker compose exec api python -m server.manage disable child-a
docker compose stop
```

Stopping preserves data. Do not use `docker compose down -v` unless you explicitly intend to destroy the household database.

## Development and checks

Python 3.12 or newer is the supported runtime. Node is needed only for design/spec checks.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r server/requirements.txt
python -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run check
```

One Gunicorn worker with four threads and SQLite write serialization suits a small household, not a shared SaaS. Deadline expiry is lazy on authenticated access, not a background notification guarantee. Request listing currently scans the household's records before filtering/pagination; archive old records through a future supported feature rather than assuming unlimited scale.
