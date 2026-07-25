# Security and Privacy

## Scope and access model

Agentic Reddit is read-only, anonymous, browser-only software for publicly accessible Reddit content. It does not post, vote, message, moderate, alter accounts, or use Reddit's OAuth/API credentials. It has no login command, cookie import, credential file, `credential.json`, or `session.json`.

Reddit has not approved this package. Use remains subject to Reddit's Terms of Service, applicable law, and the policies of each community. Do not use the tool to evade access controls, pacing, challenges, account restrictions, or community rules.

## Browser profile

Setup creates an app-owned persistent Chromium profile. The profile retains browser state needed for a cleared public-site challenge, including clearance cookies, so future runs can reuse that state. It is stored under `profiles/<name>/browser/` with the profile directory restricted to mode `0700`.

Treat the profile as sensitive local browser state:

- Do not share, publish, or commit profile directories.
- Do not point the package at a personal daily-use browser profile.
- Remove an app profile through your normal local-data controls when it is no longer needed.

The browser installation is also isolated under the app data directory; it is not a shared browser profile.

## Output privacy

Normalized result fields are intentionally unredacted third-party personal
data. Reddit content and metadata may include usernames, links, contact
details, sensitive claims, or other identifying material. Saved files can also
contain NSFW, disturbing, sexual, violent, hateful, or otherwise unsuitable
content because public Reddit content can contain it.

Protect output files as collected third-party data. Limit access, retain only
what is needed, avoid publishing results, review material before sharing it,
and apply your own lawful handling, minimization, and retention requirements.

`--raw` is a debugging option that adds raw Reddit `thing.data` attachments to
output objects. Only those optional `raw` attachments are recursively redacted
by default; normalized ordinary result fields remain unredacted by design.
`--raw --no-redact` disables that raw-only protection and prints a warning.
Diagnostic surfaces separately redact sensitive keys such as cookies, tokens,
authorization headers, and profile paths, and truncate free-text diagnostic
values.

## Rate limits and challenges

The client enforces a minimum one-second request pause and adapts to Reddit's reported rate-limit headers. This control cannot be lowered by flags, environment variables, or library entry points. A challenge response where JSON is expected is a hard error, not a signal to retry automatically. Use `doctor` and `setup` to diagnose a legitimate readiness problem; do not automate challenge evasion.

## Reporting security issues

Do not include browser profile data, cookies, third-party personal information, or raw NSFW content in an issue report. Provide a minimal redacted reproduction and the package version; use the repository's security reporting channel for sensitive vulnerabilities.
