# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-25

### Added

- Anonymous, browser-carried, read-only retrieval for subreddit listings, posts and comment trees, user activity, search, subreddit discovery, and subreddit metadata.
- Browser setup, readiness status, diagnostics, parser-derived CLI catalog, and output JSON Schema commands.
- File-based JSON and NDJSON output, rate-budget-aware pacing, structured exit codes, and diagnostic redaction.
- Privacy, security, contribution, and usage documentation for the initial release.

### Security

- Documented that output may contain third-party personal data and must not be committed or retained unnecessarily.
- Documented that NSFW content may be returned unfiltered with `over_18` metadata.
