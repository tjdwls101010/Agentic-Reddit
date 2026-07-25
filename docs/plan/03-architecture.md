# Architecture

## Naming triple + layout

- PyPI distribution: **`agentic-reddit`**
- Import package: **`agentic_reddit`** (`src/`-layout)
- Console script: **`agentic-reddit`** → `agentic_reddit.cli:main`
- Build backend: `hatchling`. Python `>=3.11`. License MIT. `Development Status :: 3 - Alpha`.
- `__version__` in `src/agentic_reddit/__init__.py`, gated three-ways (tag == pyproject == source) at release.

## The one-paragraph mental model

A `BrowserSession` starts the isolated Chrome-for-Testing executable as a minimal subprocess with a persistent profile and loopback CDP port, waits for the browser endpoint, and attaches Scrapling over CDP. Chrome loads `https://www.reddit.com/` once so the JS anti-bot challenge clears; every read is then a **same-origin `fetch()` executed inside that page**, returning parsed JSON. Scrapling's Playwright-managed launch path is deliberately not used because fresh managed profiles remained challenged in Phase 0, while the minimal direct subprocess cleared the challenge headless. Everything above the session — pagination, models, schema, CLI — never learns that a browser exists; it just calls `get_json(path) -> dict`. That single seam keeps the transport swappable.

## Module structure (`src/agentic_reddit/`)

Ported from `agentic-threads` (shape) with the transport layer replaced. **No credentials, no cookies, no `login`, no `httpx`, no `docids.py`, no `transaction.py`, no `gql.py`, no `tokens.py`.**

| Module | Responsibility | Primary source to adapt |
|---|---|---|
| `__init__.py` | `__version__`, package docstring. Public surface is the CLI only. | agentic-threads |
| `__main__.py` | `python -m agentic_reddit` → `cli.main`. | agentic-threads |
| `config.py` | `APP_NAME="agentic-reddit"`; paths (`platformdirs.user_data_dir`); `MIN_REQUEST_PAUSE_SECONDS = 1.0` + `clamp_request_pause`; `DEFAULT_MAX_REQUESTS`; `REDDIT_BASE="https://www.reddit.com"`; env prefix `AGENTIC_REDDIT_*`; profile-name validation. | agentic-threads `config.py` |
| `errors.py` | Typed hierarchy under `AgenticRedditError`, each carrying an `exit_code` class attr. See `04`. | agentic-threads `errors.py` |
| `identity.py` | **Identifier normalize-then-validate** (no auth here — the siblings' `auth.py` minus everything credential-shaped): subreddit name (`python`, `r/python`, `/r/python`, URL), username (`spez`, `u/spez`, `/user/spez`, URL), post (`t3_<id36>`, `<id36>`, permalink URL), comment permalink → `(kind, value)`. Host allowlist (`reddit.com`, `www.`, `old.`, `np.`, `sh.reddit.com`). | agentic-threads `auth.py` (identifier half only) |
| `session.py` | `BrowserSession`: lazy Scrapling import; locate the isolated Chrome-for-Testing binary; start a minimal subprocess with persistent profile + loopback CDP port; attach `DynamicSession` over the discovered WebSocket endpoint; `warm()` loads reddit.com and polls until the challenge clears; `get_json(path)` uses in-page `fetch`; `close()` terminates Scrapling and the owned subprocess. Also `run_setup()`, `run_status()`, `run_doctor()`. **No stealth/fingerprint patching (D15).** | agentic-facebook provisioning + Phase 0 CDP evidence |
| `pacing.py` | The **budget governor** (D8): consumes `x-ratelimit-remaining` / `-reset` / `-used` from each response, enforces the 1.0s floor, stretches toward `reset / remaining` as budget depletes, raises `RateLimitedError` at exhaustion. Single non-bypassable choke point. | new (small; this is the project's distinctive piece) |
| `endpoints.py` | Pure URL+param builders per command: `subreddit_path`, `post_path`, `comment_subtree_path`, `user_path`, `search_path`, `subreddits_search_path`, `about_path`. No I/O. | new (small) |
| `parse.py` | Pure walkers: `Listing` → `(list[thing_data], after)`; `parse_post_response` (2-element array → post + comment forest); recursive `replies` walk; `more`-node collection; subtree splice. Per-kind dispatch (`t1/t2/t3/t5/more`). `EnvelopeParseError` on structural drift or on a challenge-HTML body where JSON was expected (→ exit 4). | agentic-threads `parse.py` (retargeted) |
| `model.py` | `Post`/`Comment`/`Subreddit`/`User`/`Media` dataclasses + `to_dict()`; `*_FIELD_DESCRIPTIONS`; `schema_fields()` anchored on `to_dict()`; `json_schema()` (draft 2020-12). `build_*` normalizers. | agentic-threads `model.py` |
| `retrieve.py` | Orchestrators: `fetch_subreddit`, `fetch_post` (adaptive comment-tree expansion), `fetch_user`, `search`, `find_subreddits`, `fetch_subreddit_info`. `after`-cursor loop, `--limit`/`--since`/`--until` composition, `stop_reason` vocabulary, request budget, `RetrieveResult`. Transport-agnostic. | agentic-threads `retrieve.py` |
| `redact.py` | Scrub sensitive keys in diagnostics (cookie/token/authorization headers, profile paths) + truncate free-text keys (`selftext`, `body`). Normalized output fields remain unredacted; optional `raw` attachments pass through this same redaction choke point unless `--no-redact` is explicit. | agentic-threads `redact.py` |
| `cli.py` | argparse parser, subcommand handlers, `_HANDLERS` dispatch, exit-code contract, `catalog` (from parser) + `schema` (from model), `--output` writing + stderr summary. | agentic-threads `cli.py` |

## The transport seam

```python
class BrowserSession:
    def warm(self) -> None: ...  # start minimal Chrome, attach Scrapling over CDP, clear challenge
    def get_json(self, path: str) -> dict | list: ...  # same-origin fetch inside the page
    def close(self) -> None: ...
```

`get_json` runs, inside the page:

```js
const r = await fetch(path, {headers: {'Accept': 'application/json'}});
// return BOTH the parsed body and the x-ratelimit-* headers — pacing.py needs them
```

It must return the rate-limit headers alongside the body; `pacing.py` is fed on every call. A non-JSON content-type (i.e. the challenge HTML) is a **hard signal**, not a parse hiccup: raise `ChallengeError` (exit 4) with guidance to re-run `setup`.

**Lifetime:** one browser per CLI invocation — `warm()` once, then N `get_json` calls, then `close()`. Launch cost (~1–3 s) amortises across a paginated run. Do **not** launch a browser per request.

**Why in-page `fetch` and not navigating to the `.json` URL:** navigation would re-enter the challenge per request and force reading JSON out of a rendered document; a `fetch` from an already-cleared page is one clean XHR with the profile's cookies attached automatically.

## Rate governance (`pacing.py`) — the distinctive piece

Measured: **~100 requests per ~600 s window**, with `x-ratelimit-remaining` / `-reset` exposed on every response (`02` §4).

```
before each request:  sleep(max(MIN_REQUEST_PAUSE_SECONDS, adaptive_delay))
adaptive_delay     :  0                      if remaining is unknown or comfortable
                      reset / max(remaining, 1)   as remaining depletes
at remaining == 0  :  RateLimitedError(reset_at)  → stop_reason=rate_limited
                      (or sleep until reset if --wait-on-limit, bounded by --max-wait)
```

The 1.0 s floor is clamped in code and cannot be lowered by flag, env, or library entry point (sibling invariant). The governor only ever makes things *slower*. Never retry-loop on 429.

## Storage (`platformdirs.user_data_dir("agentic-reddit")`)

- `profiles/<name>/browser/` — the persistent Chromium context (holds anti-bot clearance cookies so later runs skip the challenge). Dir mode `0700`.
- `browsers/` — isolated Playwright/Chromium install (`PLAYWRIGHT_BROWSERS_PATH`), never shared with other tools.
- `output/` — default output dir (never cwd/repo).
- Env override: `AGENTIC_REDDIT_PROFILE_DIR` (or `--profile-dir`).

**There is no `credential.json`, no `session.json`, no cookie import.** The only persisted state is a browser profile. This is the largest simplification versus all three siblings.

## Data model (output schema)

Five types. Fields drawn from the real captures in `02` §10 — the useful subset, not all ~100 raw keys. All datetimes → ISO-8601 UTC `Z`. `id` = id36; `fullname` = `t3_…`/`t1_…`. **Dedup on `fullname`.**

**`Post`** (`t3`): `id`, `fullname`, `url` (reddit permalink), `link_url` (outbound url for link posts, else null), `subreddit`, `subreddit_prefixed`, `author`, `author_fullname`, `title`, `text` (selftext), `created_at`, `edited_at` (or null), `score`, `upvote_ratio`, `num_comments`, `num_crossposts`, `over_18`, `spoiler`, `is_self`, `is_video`, `is_original_content`, `stickied`, `pinned`, `locked`, `distinguished`, `flair` (link_flair_text), `domain`, `thumbnail`, `media[]` (`Media`), `total_awards`, `removed` (removed_by_category or null), `captured_at`, `raw?`.

**`Comment`** (`t1`): `id`, `fullname`, `permalink` (full url), `post_id` (link_id), `subreddit`, `parent_id`, `author`, `author_fullname`, `text` (body), `created_at`, `edited_at`, `score`, `depth`, `is_submitter`, `stickied`, `distinguished`, `controversiality`, `collapsed`, `score_hidden`, `total_awards`, `replies[]` (nested `Comment`, recursive), `more_count` (unexpanded remainder under this node, if truncated), `captured_at`, `raw?`.

**`Subreddit`** (`t5`): `id`, `fullname`, `name` (display_name), `prefixed`, `title`, `public_description`, `description`, `subscribers`, `created_at`, `over_18` (**from `over18` — note the spelling split, `02` §9**), `subreddit_type`, `url`, `lang`, `icon_url` (community_icon or icon_img), `quarantine`, `captured_at`, `raw?`.

**`User`** (`t2`): `id`, `fullname`, `name`, `created_at`, `link_karma`, `comment_karma`, `total_karma`, `is_gold`, `is_mod`, `is_employee`, `verified`, `has_verified_email`, `icon_url`, `accept_followers`, `captured_at`, `raw?`.

**`Media`** (element of `Post.media`): `kind` (`image`/`video`/`gallery`/`embed`/`unknown`), `url`, `width`, `height`. Reddit galleries → multiple `Media`; `secure_media`/`media_embed` for video/external.

Schema is **generated from the code** (`schema_fields()` anchored on `to_dict()`, `json_schema()` draft 2020-12), never hand-written — so `agentic-reddit schema --json` can't drift. `test_model.py` validates fixtures against it with `jsonschema`.

## Command → output-object map (`_COMMAND_OUTPUT`, asserted by `test_cli.py`)

| Command | Output object(s) |
|---|---|
| `subreddit` | `Post` |
| `post` | `Post` (index 0) + `Comment[]` (threaded) |
| `user` | `Post` and/or `Comment` (per `--type`) |
| `search` | `Post` (`link`), `Subreddit` (`sr`), or `User` (`user`) |
| `subreddits` | `Subreddit` |
| `subreddit-info` | `Subreddit` (single) |

## The three invariants to preserve

1. **Everything derived, never transcribed** — `catalog` from the live argparse parser, schema from `to_dict()`-anchored descriptions, exit codes from one `errors` table. Tests assert non-drift.
2. **One choke point for pacing, one for redaction** — every request passes `pacing.py` regardless of entry point; every diagnostic surface and optional `raw` attachment routes through `redact`, while normalized output fields deliberately bypass it.
3. **The transport seam stays narrow** — nothing above `session.get_json()` may know about browsers, pages, or cookies. This is what lets OAuth return later if Reddit ever approves it.
