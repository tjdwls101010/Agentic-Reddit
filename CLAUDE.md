# Agentic Reddit

## Project constraints

- Keep the package read-only. Do not add posting, commenting, voting,
  subscribing, saving, messaging, or other write operations.
- The supported transport is an anonymous browser session only: an owned,
  isolated Chrome subprocess connected through Scrapling CDP. Do not add
  credential, account, or login flows.
- Do not add stealth, fingerprint spoofing, challenge bypasses, or other
  evasion. On a challenge or unexpected HTML response, fail clearly and direct
  the user to `setup` or `doctor`.
- Keep browser imports lazy. Offline commands (`--version`, `--help`, `catalog`,
  and `schema`) must not launch a browser or import Scrapling.
- All read commands write structured JSON or NDJSON to files. Preserve the
  schema, output-path, redaction, and stderr-summary contracts.
- Preserve the non-bypassable one-second request floor and the approximately
  100-request-per-10-minute rate budget. Respect browser response rate-limit
  headers.
- Treat retrieved data as third-party personal data. Redact diagnostics by
  default; do not add captured responses, profiles, browser files, or output
  data to version control.
- Anonymous reads may return NSFW content. Preserve `over_18` data and do not
  silently filter it.
- Reddit approval has not been obtained. Preserve the explicit legal and
  privacy language in user-facing documentation: non-commercial personal or
  research use only; do not use output as bulk or ML-training data.

## Engineering rules

- Target Python 3.11+ and use the existing standard-library-first patterns.
- Keep changes minimal, explicit, and aligned with nearby code and tests.
- Add focused offline tests for behavior changes. Tests and CI must not make
  network requests or launch a browser.
- Do not add dependencies without a demonstrated need and an update to the
  packaging and lockfile conventions.