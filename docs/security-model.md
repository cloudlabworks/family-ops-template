# Security and privacy model

**Blueprint. Not deployed, not audited.** These are the rules an implementation should enforce.

## Two separate questions

| Layer | Question | Mechanism |
|---|---|---|
| Identity layer | Who is calling? | A signed assertion per person (identity-aware proxy or OIDC), a credential per kiosk, a token per service, a platform signature for opt-in quick replies |
| API, by route | Can this kind of caller use this route at all? | `x-allowed-roles` on each operation, checked against `model/roles.json` |
| API, by record | Can this caller see or change this particular record? | Ownership, `who`, `hiddenFrom`, the member a kiosk serves, the deciders copied onto a request, the allowed state transitions, `revision` |

Getting through the identity layer grants nothing on its own. Each handler loads the record and applies the
per-record rule from its operation description before it reads or writes.

## Services cannot decide

- An assistant or connector works for a verified person and is limited to that person's rights.
- No route that records a parent's verdict accepts a service token. `npm run check` fails if one ever does.
- Parents decide in their own signed-in session. Cards on their phones link there.
- The only other path is opt-in quick reply: the messaging platform posts the press straight to the API,
  signed with a key no household service holds. The API verifies the signature and the sender, and needs a
  single-use value tied to the request, the parent and the verdict pressed. What remains: control of the
  parent's messaging account is enough to press a button, so keep quick reply off for high-stakes asks.

## Kiosks

- A parent enrols a display with a single-use code. The display receives its own credential that only
  opens the kiosk routes of the one member it serves. A parent can revoke it at any time.
- An IP or MAC address never authorizes anything. Another option is to render the kiosk view locally on
  the display, from data the connector delivers, with no network listener at all.

## The home side

- The home opens no ports. The connector makes outbound calls only.
- Adults administer home services over a private mesh VPN. No public tunnel reaches the hub.
- Pictures and video from cameras stay at home. The API carries camera state only and refuses snapshots
  that include image or video data.
- The hub's own credential lives only on the machine that runs the connector.

## Doors

Only parents can unlock, and only with a step-up token: a fresh login, valid 5 minutes, usable once. Every
try is written to the audit log, refusals too. Configure the hub to relock on its own, with no dependency
on the API.

## Keep less

- Store schedules, never records: no grades, school reports, health data or location history.
- Information about children stays out of public files, out of logs shipped to outside services, and off
  shared screens unless a parent marked it shareable.
- Events marked `private` never reach a shared display or any service.
- Every profile starts switched off.

## Audit

Append-only: who, what kind of caller, which operation, which record, the result, and the path (`session`,
`channel`, `device`, `service`). There is no route to edit or delete entries. Copy the log to home storage
on a schedule.

## A lost device

`POST /devices/{id}/lost` revokes all sessions and kiosk credentials tied to the device and removes any chat
account enrolled from it. Then lock or wipe it with the vendor's tools. Devices hold no secrets, so nothing
needs rotating. Read the owner's audit entries for the past week.

## Repository hygiene

- CI runs gitleaks across the whole history, OSV-Scanner on dependencies, CodeQL, and
  `scripts/privacy-scan.mjs`.
- If you adapt this for your own home, keep a private deny list (your names, places, accounts, hostnames)
  outside the repository and run it before every push.
