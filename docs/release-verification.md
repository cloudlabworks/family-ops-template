# v0.2.0 verification

Verified 2026-11-04 with synthetic household records and randomly generated, temporary test credentials. No production family records were used.

| Instrument | Result |
|---|---|
| Python 3.12 unittest, `tests/test_api.py` | 17 tests passed |
| Ajv against `openapi/runtime.yaml`, `scripts/check-runtime-responses.mjs` | 98 captured HTTP-handler responses validated; covers tested routes/statuses, not exhaustive schema coverage |
| Real Gunicorn HTTP, `tests/http_smoke.py` | Two-parent approval, completion, process restart persistence, operator backup and restored-database reads passed |
| Docker Linux ARM64 | Image built; HTTP workflow/restart/restore passed on ARM64 host |
| Docker Linux AMD64 | Image built; HTTP workflow/restart/restore passed under emulation on ARM64 host, not native AMD64 hardware |
| `pip-audit -r server/requirements.txt` | No known vulnerabilities reported for the eight pinned Python dependencies on the verification date |
| Docker Compose | Loopback health endpoint returned healthy; persistent volume retained |
| `npm run check` | Blueprint lint, model checks, privacy scan, runtime generation check and runtime lint passed; one localhost-server warning retained intentionally |

The authorization tests cover cross-person isolation, hidden requests and audit redaction, no self-approval, frozen routing, both-parent policy, stale revisions, concurrent decisions, cancellation, deadlines, password reset/session revocation, disabled users, login rate limits and unknown routes. SQLite audit triggers reject updates/deletions through ordinary SQL.

## Reproduce

Run from the repository root after installing Python 3.12+, Node 22+ and Docker:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r server/requirements.txt
npm ci --ignore-scripts
FAMILYOPS_CONTRACT_CAPTURE=/tmp/familyops-contract.json .venv/bin/python -m unittest discover -s tests -v
node scripts/check-runtime-responses.mjs /tmp/familyops-contract.json
PYTHONPATH=. .venv/bin/python tests/http_smoke.py
npm run check
docker build -t family-ops-api:0.2.0 .
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:rw,nosuid,nodev,size=128m -v "$PWD/tests:/tests:ro" -e PYTHONPATH=/app family-ops-api:0.2.0 python /tests/http_smoke.py
```

For cross-architecture validation, build with `docker buildx build --platform linux/amd64 --load` and pass the matching `--platform` to `docker run`. Emulation must be available on a non-AMD64 host.

## Boundaries

This is functional and authorization testing, not an independent security audit, load test or proof of every possible policy interaction. No public deployment, family production migration, browser UI, hosted billing, channel callback or device integration is implied. Expiry is evaluated on authenticated access. Root access to SQLite can bypass its audit triggers. Keep deployment private as documented in [self-hosting](self-hosting.md).
