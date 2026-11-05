# Contributing

Issues and pull requests are welcome.

- Run `npm run check` before opening a pull request. For runtime changes, also run the Python tests and HTTP smoke check in [release verification](docs/release-verification.md).
- Keep every example synthetic. Use role ids (`parent-a`, `teen-a`), never real names, places, schools,
  accounts or hostnames.
- A change to who can do what goes in `model/roles.json` first; the checks keep the spec and
  `docs/roles.md` in line with it.
- A change to the request lifecycle goes in `model/request-states.json` and
  `scripts/request-reducer.mjs`, with a scenario in `examples/request-scenarios.json`.
- Sign off your commits (`git commit -s`, Developer Certificate of Origin).

By contributing, you agree that your contribution is licensed under the MIT License in [LICENSE](LICENSE).
