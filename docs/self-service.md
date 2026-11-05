# Self-service apps: per-person catalog and suggestion list

Each person has a home screen of apps they picked, or that a parent picked with them. Example catalog:
[`examples/app-catalog.json`](../examples/app-catalog.json).

## Rules

1. **Opt-in only.** Nothing is enabled for anyone by default. Opt-ins are stored per member
   (`PUT /members/{id}/apps/{appId}`).
2. **Age bands.** Each entry lists the age bands it fits. A member sees only entries for their band.
3. **Who opts in.** Adults and teens opt themselves in, unless the entry says `needsParent`. A parent opts
   in for children and young children. Anyone can opt themselves out at any time.
4. **Interests are chosen, not inferred.** A member (or a parent, for a young child) may add interest tags
   to their own profile. Tags only suggest catalog entries. Never infer interests from activity.
5. **Adopt before build.** Prefer maintained open-source or free apps. Every entry names an exit test:
   how the household leaves without losing data.
6. **Suggestion list.** Anyone can suggest an app (`POST /apps/suggestions`). A suggestion opens a request
   of kind `app` routed to parents. On approval a parent adds it to the catalog; the suggester can then opt
   in.

## Fitting apps to people

Ask each person, do not guess. A short form works:

- What do you want to do more of, or get better at?
- What gets in your way (forgetting, timing, rides, money)?
- What would you never want tracked?

Then pick from the catalog by age band and stated interests, and let the person (or a parent, for young
children) opt in.

## Example (synthetic household)

| Member | Band | Stated interests | Opted in | Suggested by them |
|---|---|---|---|---|
| Teen A | 13-17 | robotics, chess | My day, Club tracker | Chess puzzles |
| Kid A | 8-12 | astronomy, swimming | Sky tonight (opted in by Parent B) | Swim lap log |
| Little A | under-8 | animals | Picture board (opted in by Parent A) | none |
| Parents | adult | none | anything adult-banded | none |

## Build vs adopt in the example catalog

| App | Choice | Exit test |
|---|---|---|
| My day, Family inbox, Allowance, Picture board, Study timer, Club tracker | build (views over this API) | API export |
| Home hub companion app | adopt | Hub config and backups are local |
| Media server client | adopt | Media stays as files |
| Sky tonight, Meal planner | adopt (choose one, check the license) | Link only, or recipe export |
