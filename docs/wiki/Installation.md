# Installation

## Requirements

- Python 3.11 or newer
- A supported operating system capable of running the app-owned Chrome browser
- Network access to Reddit from that browser

Agentic Reddit is an anonymous, browser-only, read-only client. It does not
require an account or credentials.

## Install from PyPI

```bash
python -m pip install agentic-reddit
```

Confirm the command is available without starting a browser:

```bash
agentic-reddit --version
agentic-reddit catalog
```

## Provision the isolated browser

Before a read command, provision and warm the app-owned browser and persistent
profile:

```bash
agentic-reddit setup
agentic-reddit status
```

`setup` downloads Chrome for Testing into Agentic Reddit's application-data
directory and uses a persistent browser profile there. It does not use your
everyday Chrome profile or collect credentials. The browser download is large
(hundreds of MB). Use `--headed` when a visible browser is needed to complete
the initial warm-up.

Use a named isolated profile when separate local contexts are useful:

```bash
agentic-reddit setup --profile research
agentic-reddit status --profile research
```

`--profile-dir PATH` selects an explicit profile root. Keep any custom profile
path private and out of source control.

## Verify readiness

```bash
agentic-reddit doctor
```

`doctor` checks the installed browser, profile warm-up, anonymous browser
session, and current rate-limit information. If it reports that the browser or
profile is not ready, rerun `agentic-reddit setup`; do not attempt to bypass a
challenge.

## Storage and privacy

By default, browser files, profiles, and output files are stored in the
platform application-data directory rather than the current repository. Read
commands write structured JSON or NDJSON to a file; pass `--output PATH` to
choose a location.

Output contains intentionally unredacted third-party personal data, including
usernames, posts, and histories. In particular, `user --type overview` can make
aggregation-based de-anonymisation easy. Write output to a temporary or
access-controlled location, never commit it, and delete it when no longer
needed. Only optional `raw` attachments are recursively redacted by default.
`--raw --no-redact` disables that raw-only protection and prints a warning.

## Usage and content limits

The tool is read-only: it cannot post, comment, vote, subscribe, save, or send
messages. It uses a real isolated Chrome subprocess with Scrapling CDP as the
transport; it does not use stealth or evasion techniques.

Reddit's observed anonymous budget is approximately 100 requests per 10-minute
window. Agentic Reddit enforces at least a one-second delay between requests and
uses the browser response's rate-limit headers. Keep runs small, inspect the
reported remaining budget, and use `--wait-on-limit` only with an appropriate
`--max-wait`.

NSFW content is reachable anonymously and may be returned unfiltered. Inspect
output before sharing it; the structured `over_18` fields are available to
callers that need to handle such content.

## Legal notice

Reddit's Responsible Builder Policy requires explicit approval for programmatic
data access. This tool does not have that approval. Using it may violate
Reddit's terms; users accept possible consequences, including IP blocks or
termination. Use is limited to non-commercial personal or research purposes;
do not repurpose output as bulk or ML-training data.
