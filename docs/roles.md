# Roles and permissions

Source of truth: [`model/roles.json`](../model/roles.json). `npm run check` fails if any operation in
`openapi/openapi.yaml` allows a role where this table says `none`, or if this table drifts from the JSON.

Levels, lowest to highest: **none**, **read**, **own** (your own records plus records shared with you),
**write**, **relay** (acts for a verified person with that person's rights; never decides), **full**.

| Domain | parent | teen | child | young-child | visitor | guest | kiosk | svc-agent | svc-connector | channel-webhook |
|---|---|---|---|---|---|---|---|---|---|---|
| calendar | full | own | read | none | read | none | read | relay | read | none |
| chores | full | own | own | none | none | none | own | read | read | none |
| meals | full | write | write | none | write | none | write | write | read | none |
| activities | full | own | read | none | none | none | none | read | none | none |
| house | full | own | none | none | none | none | none | read | none | none |
| media | full | own | read | none | none | none | read | none | none | none |
| gaming | full | own | own | none | none | none | none | none | none | none |
| requests | full | own | own | none | own | none | own | relay | none | relay |
| apps | full | own | own | none | none | none | none | none | none | none |
| devices | full | own | read | none | none | none | none | none | none | none |
| audit | read | none | none | none | none | none | none | none | none | none |
| household | full | read | read | none | none | none | none | read | read | none |
| connector | read | none | none | none | none | none | none | none | full | none |

## The roles

| Role | Login | Notes |
|---|---|---|
| parent | yes | Decides requests. Unlocking a door needs a fresh login (step-up). |
| teen | yes | 13 to 17. Their own room's lights and temperature, scenes marked for teens, their own media profile. |
| child | yes | About 8 to 12. Simple views. Parents turn apps on for them. |
| young-child | no | Under about 8. Uses a kiosk that serves them, or parents act for them. |
| visitor | yes | Stays on a schedule. Sees shared records only during the visit. Profile off until a parent turns it on. |
| guest | no | Sees nothing. Guest network only. |
| kiosk | device | An enrolled display serving one member. A network address never counts as authorization. |
| svc-agent | service | Chat or voice assistant. Creates and reads for a verified sender. Cannot decide. |
| svc-connector | service | Home connector. Claims commands, writes snapshots. Cannot decide. |
| channel-webhook | channel | A messaging platform's signed button callback, checked by the API. Only for opt-in quick replies. |

## Rules the table cannot show

- **Profiles start switched off.** A parent turns each member on. A member who is off shows up in no view
  and gets no messages.
- **Joint ownership.** A member's profile can name more than one parent in `coOwners`. Each of them can
  switch it off, fix entries or erase them.
- **Hidden records.** If `hiddenFrom` names the caller, the record does not exist for them, audit detail
  included. Use it for surprises.
- **Step-up for doors.** Unlocking needs a step-up token issued to the same parent in the last 5 minutes.
  No service, kiosk or scene can unlock.
- **Services never exceed the person they act for.** An assistant filing for a teen can do what that teen
  can do and nothing more.
