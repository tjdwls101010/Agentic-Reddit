# CLI Reference

`agentic-reddit` is a read-only, anonymous, browser-backed Reddit client. Read commands save structured output to a file and print one summary line to stderr; they do not emit useful data on stdout.

## Global command

| Command | Purpose | Browser |
|---|---|---|
| `--version` | Print the package version. | No |
| `--help` | Show parser-generated help. | No |
| `catalog [--json]` | Print the machine-readable CLI catalog. `--json` selects compact JSON; otherwise it is indented. | No |
| `schema [--json]` | Print the generated JSON Schema draft 2020-12 for Post, Comment, Subreddit, User, and Media. `--json` selects compact JSON; otherwise it is indented. | No |

## Session and diagnostics

| Command | Flags | Purpose |
|---|---|---|
| `setup` | `--force`, `--headed`, `--profile NAME`, `--profile-dir PATH`, `--timeout-seconds N` (default `120`) | Install the isolated Chromium browser and warm a persistent profile by loading Reddit. It accepts no credentials. `--force` re-downloads/re-warms; `--headed` uses a visible browser when needed. |
| `status` | `--profile NAME`, `--profile-dir PATH`, `--json` | Make one inexpensive read through the profile and report whether it is ready. |
| `doctor` | `--profile NAME`, `--profile-dir PATH` | Write one compact JSON diagnostic to stderr with `browser_executable`, `profile`, `listing`, and `rate_budget` (`remaining`, `reset`, `used`). |

## Read commands

Read commands write JSON or NDJSON to `--output` or to the default output directory. Their capabilities are grouped below rather than implied to be universal.

| Command | Positional input | Command-specific flags | Output |
|---|---|---|---|
| `subreddit` | `<name>`: `python`, `r/python`, `/r/python`, or a subreddit URL. `all` and `popular` mean the public front page. Combine up to 10 names with `+`, for example `python+django+learnpython`, to read them as one listing at one request per page. | `--sort {hot,new,top,rising,controversial}` (default `hot`); `--time {hour,day,week,month,year,all}` (default `day`, for `top`/`controversial`) | Post |
| `post` | `<url\|id>`: allowed Reddit post URL, `t3_<id36>`, or bare `<id36>`. A comment permalink is rejected with exit 1 and directs the user to `comment`; no browser is started. | `--comment-sort {confidence,top,best,new,controversial,old,qa}` (default `confidence`); `--depth N`; `--comment-limit N` (default `500`) | One Post followed by threaded Comments |
| `comment` | `<permalink>`: Reddit comment permalink URL. | `--comment-sort {confidence,top,best,new,controversial,old,qa}` (default `confidence`); `--depth N`; `--comment-limit N` (default `500`); `--context N` (include up to N ancestors; Reddit clamps large values) | One Post followed by the anchored Comment with nested replies. With `--context`, the written Comment is the ancestor and contains the requested comment. |
| `user` | `<name>`: `spez`, `u/spez`, `/user/spez`, or a profile URL. | `--type {overview,submitted,comments,top}` (default `overview`); `--sort {new,hot,top,controversial}`; `--time {hour,day,week,month,year,all}` | Post and/or Comment |
| `search` | `<query>` | `--subreddit NAME` (restricts to that subreddit); `--type {link,sr,user}` (default `link`); `--sort {relevance,hot,top,new,comments}`; `--time {hour,day,week,month,year,all}` | Post (`link`), Subreddit (`sr`), or User (`user`) |
| `subreddits` | `<query>` | `--limit N` | Subreddit |
| `subreddit-info` | `<name>` in the single-name forms accepted by `subreddit` | None; singular lookup | One Subreddit |
| `user-info` | `<name>` in the same forms as `user` | None; singular lookup. Exits 5 when the account does not exist or is unavailable. | One User |
| `related` | `<url\|id>`: allowed Reddit post URL, `t3_<id36>`, or bare `<id36>`. | `--sort {num_comments,new}`; `--crossposts-only`; `--limit N` | Post; only other discussions, without repeating the original. Exits 5 when a post ID does not exist. |

### Base flags: every read command

| Flag | Meaning |
|---|---|
| `--format {json,ndjson}` | File encoding; default `json`. |
| `--output PATH` | Destination file. Without it, output is saved under the platform data directory. |
| `--wait-on-limit` | Wait for a rate-limit reset only within `--max-wait`; it does not bypass pacing. |
| `--max-wait SECONDS` | Maximum wait permitted with `--wait-on-limit`; invalid without it. |
| `--profile NAME` | Persistent browser profile name. |
| `--profile-dir PATH` | Override the profile root. |
| `--raw` | Attach raw Reddit `thing.data` to each object for debugging. Every nested `raw` attachment is redacted recursively unless `--no-redact` is used. |
| `--no-redact` | Disable raw-data redaction and emit a warning; requires `--raw`. Normalized fields are not redacted. |
| `-v`, `--verbose` | Include a scrubbed failure diagnostic. |

### Bounded-listing flags

`subreddit`, `user`, and `search --type link` accept the following flags. `--since` and `--until` force chronological `new` ordering, overriding `--sort`.

| Flag | Meaning |
|---|---|
| `--limit N` | Maximum objects to materialize. The request budget remains an upper bound. |
| `--since YYYY-MM-DD` / `--until YYYY-MM-DD` | Inclusive UTC date window. |
`search --type sr` and `search --type user` reject date windows. `subreddits` and `related` accept `--limit` without date windows. `post` and `comment` use comment-tree limits instead of `--limit` or date-window flags; `subreddit-info` and `user-info` have none of those flags.

## File summary and stop reasons

The stderr summary is shaped as:

```text
{counts}, range {oldest}..{newest}, stop reason: {reason}, budget {remaining}/{used}. Saved to {path}
```

`{counts}` is a single noun for homogeneous output or comma-separated nonzero counts for mixed post/comment output, such as `1 post, 2 comments`. For `post` and `comment`, the comment count includes nested replies recursively. `{remaining}/{used}` comes from `x-ratelimit-remaining` and `x-ratelimit-used` only when the complete valid header set also includes `x-ratelimit-reset`; otherwise it is `unknown/unknown`.

| Stop reason | Meaning |
|---|---|
| `limit_reached` | `--limit` stopped a non-empty remaining listing. |
| `listing_exhausted` | The listing reached its end. |
| `no_matches` | The search or listing had no results. |
| `since_crossed` | The `--since` boundary was reached. |
| `tree_complete` | A post's comment tree has no unexpanded `more` nodes. |
| `depth_capped` / `comment_limit` | Comment expansion stopped at the requested cap, or `depth_capped` marks a branch Reddit will not expand further; the tree is incomplete. |
| `rate_limited` | Reddit's reported budget reached zero or returned HTTP 429. |
| `max_requests` | The per-run request budget stopped the command. |

## Exit codes

| Code | Meaning | Recommended action |
|---|---|---|
| 0 | Success, including a met limit, date boundary, or exhausted listing/tree. | Use the saved file and summary. |
| 1 | Usage error, invalid identifier, or unexpected/setup failure. | Correct input or inspect diagnostics. |
| 2 | Browser missing, profile not warmed, or session not ready. | Run `agentic-reddit setup`. |
| 3 | Rate limited after writing already retrieved records, so the saved file can be partial. | Stop, or use the bounded `--wait-on-limit` behavior. |
| 4 | Response/schema drift or a challenge page where JSON was expected. | Run `agentic-reddit doctor`, re-run `setup`, or upgrade. |
| 5 | Target is unavailable: missing, private, banned, quarantined, suspended, or deleted. | Choose an available public target. |
| 7 | `--since` was requested but the lower boundary was not confirmed before stopping; this takes precedence over partial rate-limit exit 3. | Narrow the request or resume after budget is available. |
