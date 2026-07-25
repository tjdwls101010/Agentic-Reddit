# Configuration

Agentic Reddit uses an isolated Chromium installation and persistent browser profiles. It is browser-only: all Reddit reads are same-origin fetches from an already-warmed Reddit page.

## Storage locations

By default, paths are below `platformdirs.user_data_dir("agentic-reddit")`:

| Path | Contents |
|---|---|
| `profiles/<name>/browser/` | Persistent Chromium context, including anti-bot-clearance cookies. Profile directories are mode `0700`. |
| `browsers/` | The package's isolated Chromium installation. It is not shared with other tools. |
| `output/` | Default destination for JSON and NDJSON result files. It is not the current directory or repository. |

The default profile name is `default`. Profile names are safe ASCII basenames of 1–64 characters: letters, digits, `.`, `_`, and `-`.

## Profile selection

Use either command-line override on setup, diagnostics, or reads:

```text
--profile NAME
--profile-dir PATH
```

Or set the environment variable:

```text
AGENTIC_REDDIT_PROFILE_DIR=/path/to/profile-root
```

`--profile-dir` is the per-command override and `AGENTIC_REDDIT_PROFILE_DIR` changes the profile root. A selected profile is stored as `<profile-root>/<name>/browser/`; it is not a credential directory.

Example:

```bash
AGENTIC_REDDIT_PROFILE_DIR="$HOME/.local/share/agentic-reddit-profiles" \
  agentic-reddit setup --profile research
agentic-reddit subreddit python --profile research
```

## Browser setup

Run setup before the first read:

```bash
agentic-reddit setup
```

Setup downloads the isolated browser and loads Reddit once to warm the chosen persistent profile. It takes no username, password, OAuth client, cookie import, or other credential. Useful setup flags are `--force` to download/warm again, `--headed` to show the browser, and `--timeout-seconds N` (default 120). Use `status` for a cheap readiness check and `doctor` for browser, challenge, listing, and rate-header diagnostics.

## Request pacing

The client has one non-bypassable pacing governor. It enforces at least one second between requests and can only slow further as Reddit's reported budget depletes. The per-run default request budget is 100. `--wait-on-limit` may wait for a reset only up to `--max-wait`; it does not remove the pacing floor or retry HTTP 429 in a loop.

## Output configuration

Use `--output PATH` to select an explicit file and `--format {json,ndjson}` to choose encoding. Without `--output`, generated names are saved under `output/` using a safe identifier and UTC timestamp. See [Output Schema](Output-Schema.md) for file and summary behavior.
