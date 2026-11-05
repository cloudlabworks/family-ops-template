# Gaming and screen time: what each platform lets you enforce

Read from vendor and Home Assistant documentation on 2026-11-04. These products change often, so check the
current docs before you rely on a row.

| Platform | Public API that sets limits? | What automation can reach | Where it is documented |
|---|---|---|---|
| Nintendo Switch and Switch 2 | Nintendo publishes none. Home Assistant ships a `nintendo_parental_controls` integration, built on a community library that reverse-engineers the parent app | Today's minutes used and remaining; the daily limit, bedtime and weekly schedule; suspending software; extra minutes | home-assistant.io integration page for Nintendo parental controls |
| Xbox (Microsoft Family Safety) | We found none | The Home Assistant `xbox` integration reports what is playing and offers a remote; it needs an adult account. Time limits live in the Family Safety app, the Xbox Family Settings app or the family website | Microsoft support article on Family Safety time limits; home-assistant.io `xbox` |
| PlayStation | We found none | The Home Assistant `playstation_network` integration only reads online status. Time limits live in the PlayStation Family app or on the console | playstation.com, play time controls; home-assistant.io `playstation_network` |
| Steam Families | No API writes limits | The Steam Web API can list recently played games when the profile is visible. Limits are configured inside Steam | Valve's Steam Families FAQ; Steamworks `IPlayerService` docs |
| Apple Screen Time | No web API | Apple's Family Controls frameworks run on the device only, inside an app holding an entitlement Apple grants on request; tvOS is not covered | developer.apple.com, Family Controls |

## How the blueprint uses this

- `GET /gaming/platforms` reports `enforcement: api` only where an integration can change limits (today,
  Switch through the hub). Everything else reports `manual`.
- `PUT /gaming/{member}/windows` saves the play windows. On `api` platforms the connector applies them. On
  `manual` platforms the parent receives a checklist for that platform's own app. The API does not pretend
  to enforce what it cannot reach.
- Backstop on the network: a per-device DNS-filter schedule (`PUT /devices/{id}/schedule`) can cut chosen
  services outside allowed hours, on devices that use the household's DNS.
- Video: the media server enforces its own per-user rating ceiling, library list and viewing hours
  (Jellyfin documents all three; Plex offers preset restriction profiles for managed users).
