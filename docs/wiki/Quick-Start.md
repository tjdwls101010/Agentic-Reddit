# Quick Start

Agentic Reddit reads public Reddit data anonymously through an isolated local
browser. It is read-only and writes structured results to files.

## 1. Install and prepare a browser profile

```bash
python -m pip install agentic-reddit
agentic-reddit setup
agentic-reddit status
```

The first setup downloads app-owned Chrome for Testing and warms its persistent
profile. It may take time and requires hundreds of MB of disk space. No account,
credentials, or everyday browser profile are used.

## 2. Read a subreddit

```bash
agentic-reddit subreddit python --limit 10 --output python-hot.json
```

The command writes the results to `python-hot.json` and prints a one-line summary
to stderr, including counts, stop reason, and the observed
`x-ratelimit-remaining`/`x-ratelimit-used` budget when all rate-limit headers are
valid. It does not emit retrieved records to stdout.

## 3. Read a post and comment tree

```bash
agentic-reddit post https://www.reddit.com/r/python/comments/abc123/example/ \
  --depth 3 --comment-limit 100 --output post.json
```

Replace the synthetic `abc123` id and title portion with a real post URL. `post` expands the
comment tree within the requested depth and comment limits. A stop reason of
`depth_capped` or `comment_limit` means that some comments remain unexpanded.

## 4. Search or inspect a user

```bash
agentic-reddit search "python packaging" --type link --limit 20 --output search.json
agentic-reddit user spez --type submitted --limit 10 --output user.json
```

Use `agentic-reddit catalog` for the machine-readable command catalog and
`agentic-reddit schema --json` for the output schema. Both work offline and do
not start a browser.

## Work within the request budget

Anonymous access has an observed budget of about 100 requests per 10-minute
window. Agentic Reddit enforces a minimum one-second delay and adapts to the
rate-limit headers returned in the browser session. Keep queries bounded with
`--limit`, watch the remaining/used header budget in the summary, and avoid
repeated runs. When the budget is exhausted, exit 3 can follow a saved partial
result. `--wait-on-limit` can wait until reset when paired with a suitable
`--max-wait`. For `subreddit`, `user`, and `search --type link`, `--since` and
`--until` force `new` ordering; non-link searches reject date windows. If a
`--since` run stops before confirming its lower boundary, it exits 7 instead.

## Treat output as sensitive

Results can include third-party usernames and histories; `user --type overview`
can enable aggregation-based de-anonymisation. Store output in a temporary or
access-controlled location, do not commit it, and delete it when finished.
Raw source payloads are redacted recursively by default only when `--raw` is
used. `--no-redact` exposes those raw attachments and warns before writing; it
does not change normalized output fields.

NSFW content is accessible anonymously and may appear unfiltered in results.
Check the `over_18` fields and inspect output before sharing it.

## Know the boundaries

The tool does not write to Reddit: it cannot post, comment, vote, subscribe,
save, or send messages. It uses an owned Chrome subprocess connected through
Scrapling CDP, without stealth or evasion.

Reddit's Responsible Builder Policy requires explicit approval for programmatic
data access. This tool does not have that approval. Using it may violate
Reddit's terms, and users accept possible consequences such as IP blocks or
termination. It is for non-commercial personal or research use only; do not use
its output as bulk or ML-training data.
