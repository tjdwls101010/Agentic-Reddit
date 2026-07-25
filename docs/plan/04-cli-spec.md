# CLI Specification

`prog = agentic-reddit`. stdlib `argparse`. `main(argv)` → `build_parser().parse_args()` → dispatch via `_HANDLERS`. Subparsers `required=True`. Global `--version`. Custom `_ArgumentParser.error()` exits **1** (not argparse's 2 — exit 2 is reserved for "browser/session not ready").

## Commands

### Session / meta

- **`setup`** — provision the isolated browser (download Chromium into the app-owned `browsers/` dir) and warm the persistent profile by loading `reddit.com` until the anti-bot challenge clears. Takes **no credentials of any kind**. Flags: `--force` (re-download / re-warm), `--headed` (if Q-2 shows headless is challenged), `--profile`, `--profile-dir`, `--timeout-seconds` (default 120). Exit 0 / 1 / 2.
- **`status`** — one cheap read (`/r/announcements/about.json`) through the warmed profile → classify. Flags: `--profile`, `--profile-dir`, `--json`. Exit: 0 ready, 2 browser missing / profile not warmed / challenge unresolved, 3 rate-limited.
- **`doctor`** — deeper diagnostic: browser present? profile warm? challenge clears? a real `Listing` comes back? current `x-ratelimit-remaining`/`-reset`? Flags: `--profile`, `--profile-dir`. Exit 0 / 1 / 2.
- **`catalog`** — machine-readable description of the whole CLI, generated from the parser. Flag: `--json` (no-op; always JSON). Offline, no browser.
- **`schema`** — the `Post`/`Comment`/`Subreddit`/`User`/`Media` output schema. Flag: `--json` (JSON Schema draft 2020-12). Offline, no browser.

### Read primitives (write JSON to a file; one-line stderr summary)

- **`subreddit <name>`** — a subreddit's listing. `<name>` accepts `python`, `r/python`, `/r/python`, or a subreddit URL. **`all` / `popular` = the public front page.** Flags: `--sort {hot,new,top,rising,controversial}` (default `hot`), `--time {hour,day,week,month,year,all}` (default `day`; applies to `top`/`controversial` only). → `Post`.
- **`post <url|id>`** — one post **plus its comment tree** (adaptive `more` expansion via permalink-subtree GETs, D7). `<url|id>` = a post URL (any allowed reddit host), `t3_<id36>`, or bare `<id36>`. Flags: `--comment-sort {confidence,top,best,new,controversial,old,qa}` (default `confidence`), `--depth N` (tree depth cap), `--comment-limit N` (max comments to materialise; default a sane cap, e.g. 500). → `Post` (index 0) then threaded `Comment`s.
- **`user <name>`** — a redditor's activity. `<name>` accepts `spez`, `u/spez`, `/user/spez`, or a profile URL. Flags: `--type {overview,submitted,comments,top}` (default `overview`), `--sort {new,hot,top,controversial}`, `--time {…}`. → `Post` and/or `Comment`.
- **`search <query>`** — search Reddit. Flags: `--subreddit <name>` (restrict to one sub, sets `restrict_sr=1`), `--type {link,sr,user}` (default `link`), `--sort {relevance,hot,top,new,comments}`, `--time {…}`. `link` → `Post`; `sr` → `Subreddit`; `user` → `User`.
- **`subreddits <query>`** — find subreddits by name/topic. → `Subreddit`.
- **`subreddit-info <name>`** — subreddit metadata (subscribers, description, type, `over_18`, quarantine). → single `Subreddit`.

### Common read flags (shared group)

`--format {json,ndjson}` (default json), `--output PATH` (default: timestamped file under the platform data dir), `--limit N` (default unbounded, capped by the request budget), `--since YYYY-MM-DD`, `--until YYYY-MM-DD` (client-side over `--sort new`), `--wait-on-limit`, `--max-wait SECONDS`, `--profile`, `--profile-dir`, `--raw`, `--no-redact`, `-v/--verbose`.

`--output` default naming: `<safe_identifier>-<UTC timestampZ>.<json|ndjson>` under `output/`. `subreddit`'s identifier is the sub name; `post`'s is the post id36.

## Output contract

- Read commands write to a **file**; only a one-line summary hits **stderr**; nothing useful goes to stdout.
- Summary format: `"{N} posts, range {oldest}..{newest}, stop reason: {reason}, budget {remaining}/{used}. Saved to {path}"` (`{N} comments …` / `{N} subreddits …` / `{N} users …` per output object). **Surfacing the remaining rate budget in the summary is deliberate** — it is the scarce resource (D8) and the skill needs to see it to plan a chain.
- `--raw` attaches the raw `thing.data` per object (redacted unless `--no-redact`, which prints a warning). Debug-only.

## `stop_reason` vocabulary (in the stderr summary)

- `limit_reached` — `--limit` stopped it; there is more.
- `listing_exhausted` / `no_after` — genuinely the end (`after` is null).
- `no_matches` — a search/listing with no hits (real; report as such).
- `since_crossed` — `--since` date boundary reached.
- `tree_complete` *(post)* — the comment tree was fully expanded; no unexpanded `more` remains.
- `depth_capped` / `comment_limit` *(post)* — expansion stopped by `--depth`/`--comment-limit`; unexpanded `more_count` remains. **"Gave up", not "finished".**
- `rate_limited` — budget exhausted (`x-ratelimit-remaining == 0` or a 429). See `--wait-on-limit`.
- `max_requests` — stopped by the per-run request budget.

## Exit-code contract (single source in `errors.py`; asserted by `test_cli.py`)

Follows the **X/Threads convention** (3 = rate-limited, 4 = drift), NOT Facebook's.

| Code | Meaning |
|---|---|
| 0 | success (limit met / date window reached / listing or tree exhausted) |
| 1 | usage error, invalid identifier, or unexpected failure |
| 2 | browser/session not ready — not installed, profile not warmed, challenge unresolved. Fix: `agentic-reddit setup` |
| 3 | rate-limited (budget exhausted or 429). See `--wait-on-limit` |
| 4 | Reddit's response no longer matches expectations — envelope parse failure, or an anti-bot challenge page where JSON was expected. Fix: `agentic-reddit doctor`, re-run `setup`, or upgrade |
| 5 | target subreddit/user/post does not exist or is unavailable (private, banned, quarantined, suspended, deleted) |
| 7 | `--since` requested but the run stopped before confirming it was reached |

## Typed errors (`errors.py`, base `AgenticRedditError`, each with `exit_code`)

`BrowserNotReadyError` / `SetupRequiredError` (→2, browser missing or profile unwarmed), `ChallengeError` (→4, a challenge/HTML body where JSON was expected — **never auto-retry-loop**; tell the user to re-run `setup`), `RateLimitedError(reset_at)` (→3), `EnvelopeParseError` (→4, structural drift), `NotFoundError` / `TargetUnavailableError` (→5, 404 / private / banned / quarantined / suspended / deleted — shapes to be captured in Phase 0 Q-6), `InvalidIdentifierError` (→1), `BrowserSetupError` (→1, install-time failure).

(No login/cookie/credential/`doc_id`/transaction errors — there are none in this design.)

## `catalog` (mirror agentic-threads verbatim)

`build_catalog()` reflects over `build_parser()._actions` → `{catalog_version, package, command, version, commands[], exit_codes{}, output_schema}`. Each command carries `name`, `help`, `output` (`Post`/`Comment`/`Subreddit`/`User`/None from `_COMMAND_OUTPUT`), `arguments[]` (flags/types/defaults/choices). `test_cli.py` asserts every `_HANDLERS` command is in the catalog and every read command declares its output object — the anti-drift gate.
