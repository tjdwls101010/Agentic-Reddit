# Security Policy

## Reporting a vulnerability

Report security vulnerabilities privately through the repository's security reporting channel when available. If private reporting is unavailable, open a GitHub issue with enough detail to reproduce the problem and avoid publishing sensitive data.

Do not include real Reddit output, usernames, browser-profile contents, tokens, cookies, or credentials in a report.

## In scope

The following are security issues for this project:

- A bypass of diagnostic redaction that exposes sensitive fields outside the requested output file.
- Injection or unsafe behavior caused by malicious or malformed Reddit API responses.
- Unsafe browser-profile creation, storage, permissions, or cleanup.
- Supply-chain weaknesses in the release or trusted-publishing pipeline.

## Out of scope

The following are not security vulnerabilities for this project:

- That use may violate Reddit's terms or policies. This is a documented, intentional property; see [DISCLAIMER.md](DISCLAIMER.md).
- That normalized result fields are unredacted. They are intentionally returned as third-party personal data; only optional `raw` attachments are recursively redacted by default. `--raw --no-redact` disables that raw-only protection and warns.

## Handling guidance

Keep browser profiles and output files private. Do not commit output files or real captures. Use synthetic, PII-free fixtures for tests. Keep diagnostic data redacted unless an explicit local debugging workflow requires otherwise.
