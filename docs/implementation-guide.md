# Setup and implementation guide

> **Status: blueprint.** This repository contains a specification, models, examples and checks. It does
> **not** contain a server, and nothing here is deployed anywhere. Treat it as a design to implement in
> your own private environment.

## 0. Validate the blueprint

```sh
npm ci --ignore-scripts
npm run check        # OpenAPI lint, model checks, request scenarios, privacy scan
```

## 1. Decide the household model first

1. List members with a role (`parent`, `teen`, `child`, `young-child`, `visitor`) and an age band. Use ids,
   not names, in anything you might share.
2. Keep every profile `disabled` until the adults responsible for that person agree it should be on.
3. Write routing rules: who decides which kinds of requests, and whether one parent or both.
4. Ask each person what they want from self-service (see [self-service.md](self-service.md)).

## 2. Identity

1. Put an identity layer in front of a private hostname: one login per person, short sessions.
2. Map each verified subject to a member id in the API, server-side.
3. Issue service tokens for the assistant and the connector, stored only on the machines that use them.
4. Enrol kiosks with one-time codes (`POST /devices/{id}/enrolment`). Never authorize by network address.

## 3. API and database

1. Implement handlers from `openapi/openapi.yaml`. Generate types or stubs from the spec if your stack
   supports it.
2. In every handler: load the object, apply the per-object rule from the operation description, check
   `revision`, write, append to audit. Return 404 for objects hidden from the caller.
3. Implement the request state machine exactly as `scripts/request-reducer.mjs` does, and port
   `examples/request-scenarios.json` into your own tests.
4. Record parent verdicts only from the parent's own session. If you add quick reply, receive the
   platform's signed callbacks directly, verify the signature and sender, and mint one single-use value per
   request, parent and verdict; store only its hash and mark it used before acting.

## 4. Home side

1. Run the home-automation hub on an always-on machine at home. Define scenes in the hub (for example
   `movie-night`, `bedtime`, `away`, `morning`). Scenes never unlock doors.
2. Run the connector on a home machine: claim commands from `/connector/commands`, translate typed
   intents into hub, media-server and DNS-filter calls, report results, push snapshots. Outbound only.
3. Give adults admin access over a private mesh VPN. Do not open ports or public tunnels to home services.
4. Keep camera media inside the home.

## 5. Media and gaming

1. Create a media-server user per member with a maximum rating, allowed libraries and an access schedule.
2. Fill in `GET /gaming/platforms` from [gaming-platforms.md](gaming-platforms.md) for the platforms you
   own. Re-check the vendor docs first.

## 6. Notifications

Send decision cards whose buttons are links into the parent's own signed-in inbox. Quick reply stays off
unless you build the signed-callback path above.

## 7. Before you publish anything derived from your own setup

1. Run `npm run check`.
2. Run your private deny list (real names, places, schools, accounts, hostnames) over every file and the
   full git history. Keep that list outside the repository.
3. Run `gitleaks git .` over the history.

## Phasing that works

| Phase | Build |
|---|---|
| 1 | Requests inbox, calendar, chores and allowance, lists, each person's app list |
| 2 | Home hub with scenes and the connector; media server profiles |
| 3 | Gaming windows where platforms allow, device schedules, energy views |
