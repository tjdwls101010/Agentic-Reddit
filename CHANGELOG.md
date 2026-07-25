# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-07-26

Minor: three new read commands, one combined-listing form, and two behaviour corrections. Nothing documented is removed. Every 0.2.0 invocation still works except one that was answering the wrong question — see the `post` entry under Changed.

The theme is navigation coverage. The package could already read a subreddit, a post, a redditor's activity, and search; it could not open the comment someone actually linked to, look up a redditor's profile, or find the other communities discussing the same link. Those are three of the most ordinary things a logged-out person does on Reddit, and all three endpoints were verified anonymously before being wired up.

### Added

- `comment <permalink>` reads one comment and the replies beneath it, through the comment's own permalink rather than its post. On a large thread this is the cheap read: it fetches that branch instead of the whole tree. `--context N` includes up to N ancestors, because a reply read alone is frequently unintelligible without what it was answering. Output is one `Post` followed by the anchored `Comment`, the same shape `post` writes.
- `user-info <name>` reads one redditor's profile — karma split, account age, moderator/employee/verified flags — and emits a single `User`. It exits 5 for an account that does not exist, which makes it the person-level existence check that `subreddit-info` already was for communities.
- `related <url|id>` reads Reddit's own "other discussions": the same link as submitted to other communities, with `--sort {num_comments,new}` and `--crossposts-only`. It writes only the other discussions, since the caller already holds the original. Measured note: Reddit repeats children in this listing, so the existing fullname deduplication is load-bearing here rather than incidental.
- `subreddit` accepts a combined name — `subreddit python+django+learnpython` — reading up to ten communities as one listing at one request per page instead of one run per community. `subreddit-info` still takes a single name, because a combined name has no metadata record.

### Changed

- `post` now **rejects** a comment permalink with a usage error naming the `comment` command, instead of quietly discarding the comment id and reading the whole post. The old behaviour returned a plausible result to a different question than the one asked, and on a large thread it spent a large share of the request budget doing so. The check is client-side: no browser starts and no request is spent.
- The stderr summary's comment count for `post` and `comment` counts nested replies recursively. A tree of two top-level comments carrying three hundred replies previously reported `2 comments`, which reads as a total and was not one.

### Fixed

- A comment branch that Reddit declines to expand any further no longer aborts the whole retrieval as response drift. Measured 2026-07-26: some deep branches answer their own permalink with exactly what is already visible, so the `more` pointer never clears. The run now abandons that branch, keeps expanding the others, and reports `depth_capped` — an honest incomplete tree — where it previously exited 4 and sent the caller into a `doctor` / `setup --force` cycle over the shape of one thread. This is the same class of mistake the 0.2.0 `subreddit-info` fix addressed: a target- or content-shaped condition reported as transport drift.
- An anchored comment request whose comment id is not in that post is reported as a missing target (exit 5). Measured 2026-07-26: Reddit answers such a request with the post's ordinary top-level listing rather than a 404, so the envelope alone cannot say whether the anchor was honoured — and neither can its shape, because a post with a single top-level comment returns the same one-comment forest a genuine anchor does. `comment` therefore checks that the requested id is actually present in what came back, including when `--context` re-roots the forest at an ancestor and nests it. Without that, the command would hand back an unrelated comment as the requested one.

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
