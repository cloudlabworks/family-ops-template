# v0.2.0: self-hosted requests and approvals

First runnable Family Ops release. MIT licensed, synthetic examples only.

## Included

- Flask/Gunicorn API with persistent SQLite storage and a Docker Compose deployment.
- Individual parent/teen/child logins, hidden password prompts, one-hour bearer sessions, logout and local account disable/password rotation.
- Requests, either/both parent decisions, needs-info answers, cancellation, completion, deadline enforcement and optimistic concurrency.
- Frozen server-side routing; hidden-request filtering across list, detail and audit.
- Transactional append-only audit and consistent backup command.
- Runnable subset contract in openapi/runtime.yaml; original blueprint retained separately.

## Not included

No web UI, public hosted service, billing, Agensi skill, calendar/chores implementation, real household data, service impersonation, messaging callbacks, kiosks, or Nintendo/iOS/device enforcement. Private deployment only. This release does not implement all 74 blueprint operations.

## Verification

See docs/release-verification.md for commands, measured outcomes, architecture coverage and known limitations. Release code is not a claim of a production security audit.
