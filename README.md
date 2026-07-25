# Agentic Reddit

Agentic Reddit is a read-only CLI for anonymous Reddit retrieval. It uses a browser session to read structured Reddit JSON and writes results to files.

## Important limits

- No Reddit account, API key, login, or credentials are used or accepted.
- Run one-time setup before reading. It downloads an isolated browser and warms a persistent browser profile; the browser download uses hundreds of MB of disk space.
- Anonymous Reddit access has a practical budget of about **100 requests per 10 minutes**. The CLI observes Reddit's rate-limit headers and paces requests; large comment trees and broad searches can stop at the budget.
- Results can include NSFW content. Content is not filtered; posts and subreddits expose `over_18` when Reddit provides it.
- Commands are read-only. They cannot post, comment, vote, subscribe, save, send messages, or access a personalized account feed.
- Output can contain third-party personal data. See [DISCLAIMER.md](DISCLAIMER.md) and [SECURITY.md](SECURITY.md).

## Installation

Python 3.11 or later is required.

```bash
pip install agentic-reddit
agentic-reddit setup
```

`setup` takes no credentials. Use `agentic-reddit setup --headed` when a visible browser is needed for setup, or `agentic-reddit setup --force` to download or warm again.

## Quick usage

Read commands write JSON (or NDJSON) to an output file and print a short summary to stderr. Without `--output`, files are written under the platform data directory, not the current directory.

```bash
# Read a subreddit listing
agentic-reddit subreddit python --sort hot --limit 20 --output python.json

# Read a post and its comment tree
agentic-reddit post https://www.reddit.com/r/python/comments/abc123/title/ \
  --depth 3 --comment-limit 500 --output post.json

# Search posts in one subreddit
agentic-reddit search "type hints" --subreddit python --type link --limit 20 \
  --output search.json

# Inspect readiness and available rate budget
agentic-reddit status --json
agentic-reddit doctor
```

Replace the synthetic `abc123` id with a real post id or pass a real Reddit permalink.

The available read primitives are:

- `subreddit <name>` — listing; combine up to 10 names with `+`.
- `post <url|id>` / `comment <permalink>` — a post tree or one comment subtree.
- `user <name>` — public activity; use `--type overview|submitted|comments|top`.
- `search <query>` — use `--type link|sr|user` and optionally `--subreddit`.
- `subreddits <query>` — find subreddits.
- `subreddit-info <name>` / `user-info <name>` — community or profile metadata.
- `related <url|id>` — other communities discussing the same link.

Use `agentic-reddit catalog --json` for the parser-derived command catalog and `agentic-reddit schema --json` for the output JSON Schema. Both are offline commands and do not start a browser.

## Output and rate limits

Every read primitive supports `--format json|ndjson`, `--output PATH`, `--wait-on-limit` with optional `--max-wait SECONDS`, `--profile`, `--profile-dir`, `--raw`/`--no-redact`, and `-v/--verbose`. `subreddit`, `user`, and `search --type link` additionally support `--limit N` and `--since`/`--until` date windows; a date window forces `new` ordering. Non-link search types reject date windows. `subreddits` and `related` support `--limit` without date windows; `post` and `comment` bound comment trees separately; singular metadata lookups support neither group.

Comment-tree retrieval is adaptive and bounded by `--depth` and `--comment-limit`. A result can report that expansion stopped because of a depth, comment, request, or rate limit; that does not mean the tree is complete. On a rate limit, exit 3 can follow a saved partial result; when `--since` was requested but its lower boundary was not confirmed, exit 7 takes precedence. The tool does not provide crawl, batch, daemon, write, login, or OAuth features.

## License

[MIT](LICENSE)
