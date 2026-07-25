# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-25

Minor rather than patch: the exit-code table is part of the published contract (`agentic-reddit catalog` emits it), and this release changes which code one input class produces. Nothing documented is removed or redefined — exit 5 still means "target does not exist or is unavailable" and exit 4 still means response drift — so callers written against the documented contract need no change, but anything branching on the observed 0.1.0 behavior will see different control flow.

### Fixed

- `subreddit-info` on a subreddit that does not exist now exits **5** (target does not exist) instead of **4** (response drift), whose remedy is a pointless `doctor` / `setup --force` cycle. Reddit answers an about request for a missing subreddit with HTTP 200 and an empty `Listing` rather than a 404; that one measured shape is now read as a missing target, while every other non-`t5` body still reports drift. Listing commands are deliberately unchanged — `subreddit <name>` still reports `no_matches` at exit 0, because there an empty `Listing` cannot distinguish a missing community from a merely quiet one.
- Argparse usage errors are no longer replaced wholesale with `[REDACTED diagnostic text: N chars]` once they exceed 80 characters, which permanently hid every `invalid choice` message — the signal that says an install is out of date — because that message enumerates all eleven subcommands. Usage errors are still scrubbed for credentials and local paths. The length bound is unchanged for runtime diagnostics, which can carry scraped content; a usage error carries argv.

### Added

- A `reddit` retrieval skill for Claude Code (`.claude/skills/reddit/`) that wraps the published CLI, teaching budget-first chaining, output-completeness semantics, and the failure playbook. Ships no Python artifact and does not affect the installed package.

## [0.1.0] - 2026-07-25

### Added

- Anonymous, browser-carried, read-only retrieval for subreddit listings, posts and comment trees, user activity, search, subreddit discovery, and subreddit metadata.
- Browser setup, readiness status, diagnostics, parser-derived CLI catalog, and output JSON Schema commands.
- File-based JSON and NDJSON output, rate-budget-aware pacing, structured exit codes, and diagnostic redaction.
- Privacy, security, contribution, and usage documentation for the initial release.

### Security

- Documented that output may contain third-party personal data and must not be committed or retained unnecessarily.
- Documented that NSFW content may be returned unfiltered with `over_18` metadata.
