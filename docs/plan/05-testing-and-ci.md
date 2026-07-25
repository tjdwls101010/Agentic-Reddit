# Testing, Packaging & CI

Mirror `agentic-threads`/`agentic-x` for structure, with one structural difference: **the browser is a base dependency** (D16), so there is no `[browser]` extra and no "base install must not import scrapling" guard. Instead CI must prove the opposite invariant: **the offline commands work without ever launching a browser.**

## pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agentic-reddit"
version = "0.1.0"                      # bump per release; gated vs tag AND __init__.__version__
requires-python = ">=3.11"
license = "MIT"
dependencies = [
    "scrapling[fetchers]>=0.4.10,<0.5",
    "platformdirs>=4.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.8", "pre-commit>=3.8", "build>=1.2", "jsonschema>=4.0"]

[project.scripts]
agentic-reddit = "agentic_reddit.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/agentic_reddit"]

[tool.ruff]
line-length = 100
target-version = "py311"
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[project.urls]
Homepage  = "https://github.com/tjdwls101010/Agentic-Reddit"
Issues    = "https://github.com/tjdwls101010/Agentic-Reddit/issues"
Changelog = "https://github.com/tjdwls101010/Agentic-Reddit/blob/main/CHANGELOG.md"
```

**No `httpx`** — every request goes through the browser page. `jsonschema` is a declared dev dep so the schema-validation test runs in CI (not `importorskip`'d away).

**Lazy-import discipline (inverted from the siblings):** scrapling is a base dep, but it must still be imported **only inside `session.py` functions**, never at module top level, so that `--version`, `--help`, `catalog`, and `schema` stay instant and browser-free. `tests/test_offline_commands.py` enforces this in a subprocess.

## Tests (`tests/`) — offline, fixture-driven; no network and **no browser** in CI

- `conftest.py`: `load_fixture` returns a fixture file's parsed JSON (the `post` fixture is a 2-element array).
- `tests/fixtures/*.json`: **hand-authored synthetic, PII-free** `Listing`/`thing` skeletons (fake usernames like `synthetic_alice`, fake `t3_`/`t1_` ids), one per shape: `subreddit_hot`, `post_with_comment_tree` (including both a `t1`-parented and a `t3`-parented `more` node), `comment_subtree` (the permalink-subtree response), `user_overview` (mixed `t1`+`t3`), `search_link`, `search_sr`, `search_user`, `subreddits_search`, `subreddit_about`, plus edge cases (gallery post, video post, removed/deleted comment, `over_18` post and `over18` subreddit, empty listing, private/banned/suspended shapes from Q-6). Un-ignored in `.gitignore` by **exact name**, never a wildcard. Real captures live in a gitignored `scratch/`.
- Unit test files (all offline, mock JSON — never the network, never a browser):
  - `test_parse.py` — `Listing` walk + `after` EOF; the 2-element `post` array split; recursive `replies` walk (`""` vs nested `Listing`); `more`-node collection; **subtree splice** (permalink-subtree response replaces a `more` in place); per-kind dispatch; `EnvelopeParseError` on structural drift **and on an HTML/challenge body**; decoy protection (never hunt for a convenient key).
  - `test_model.py` — `build_*` normalizers, ISO-Z serialization, `raw` only-when-set, schema/`to_dict` parity, every key has a description, `jsonschema` validation of fixtures, and specifically the **`over_18` vs `over18` spelling split** (`02` §9).
  - `test_pacing.py` — **the distinctive suite.** The 1.0 s floor cannot be bypassed (monkeypatch `time.sleep`, assert captured durations) from any entry point; the governor stretches delay as `remaining` depletes; `remaining == 0` raises `RateLimitedError(reset_at)`; `--wait-on-limit` sleeps to `reset` and is bounded by `--max-wait`; a missing header set degrades to the plain floor rather than crashing.
  - `test_session.py` — with a **fake page object** (no real browser): `get_json` builds the right in-page call, surfaces rate-limit headers to `pacing`, raises `ChallengeError` on a non-JSON content-type, and `warm()` polls-then-times-out correctly. Never launches Chromium.
  - `test_retrieve.py` — a `FakeSession` returning canned pages drives dedup (on fullname), `after` EOF, limit/since/until composition, the full `stop_reason` vocabulary, and comment-tree expansion (`more` → subtree GET → splice; budget caps → `depth_capped`/`comment_limit`/`tree_complete`).
  - `test_identity.py` — identifier normalization for subreddit/user/post/comment across bare names, `r/`/`u/` prefixes, all allowed hosts, and rejection of foreign hosts.
  - `test_endpoints.py` — URL/param builders (sort/time/after/count/restrict_sr/type).
  - `test_redact.py`, `test_cli.py` (exit-code map + catalog coverage + schema output), `test_catalog.py`.
  - `test_offline_commands.py` — subprocess: `agentic-reddit --version/--help/catalog/schema/schema --json` succeed **and `scrapling` never appears in `sys.modules`** (the lazy-import guard).
- `tests/live/` (opt-in, gated behind `AGENTIC_REDDIT_LIVE=1`, **never in CI**): a real browser session; asserts **shapes and invariants, never content** (no PII); hard-bounded to ≤3 requests to respect the ~100/10min budget. Env: `AGENTIC_REDDIT_LIVE_TARGET`.

## CI (`.github/workflows/ci.yml`) — matrix `[macos-latest, ubuntu-latest]`, Python 3.12

- `lint-and-test`: install pinned `requirements-dev.lock` + `pip install -e . --no-deps`; `ruff check .`, `ruff format --check .`, `python scripts/check_fixtures_pii.py`, `pytest`. **`--no-deps` matters**: it keeps scrapling/Chromium out of CI entirely, which is why every test must be browser-free.
- `build-and-smoke`: build the wheel, install into a clean venv **with `--no-deps`**, and smoke-test `agentic-reddit --version/--help/catalog/schema/schema --json`. This proves the offline command path never touches scrapling — the load-bearing regression (an eager top-level `import scrapling` would crash `--version` here).

**No CI leg installs a browser binary.** Live/browser verification is a manual, opt-in step (Phase 5).

## Publishing (`.github/workflows/publish.yml`) — PyPI Trusted Publishing (OIDC)

Already configured and proven (the `0.0.1` placeholder published through it): repo `tjdwls101010/Agentic-Reddit`, workflow **`publish.yml`**, environment **`pypi`**. **Keep the filename and the environment name.** Harden the existing skeleton to the sibling standard:

- Keep `on: release: types: [published]` (a GitHub Release, not a bare tag push).
- Add to `build`: `python3 scripts/check_tag_version.py "${{ github.ref_name }}"` — verifies tag == `pyproject` version == `__init__.__version__` (three-way, Threads style).
- Pin `pypa/gh-action-pypi-publish` to a **commit SHA** (the skeleton currently uses the floating `@release/v1`; the siblings pin `cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0`).
- Keep `permissions: id-token: write`; add a top-level `permissions: contents: read`. No stored API token anywhere.

## pre-commit + scripts

- `.pre-commit-config.yaml`: `astral-sh/ruff-pre-commit` (pinned, as the siblings do) running `ruff --fix` + `ruff-format`, plus a local hook running `scripts/check_fixtures_pii.py` on `tests/fixtures/*.json`.
- `scripts/check_tag_version.py` (three-way gate, `tomllib` + AST-parse `__init__`), `scripts/check_fixtures_pii.py` (stdlib-only structural scan: emails/phones, token-shaped keys, high-entropy strings, non-synthetic usernames — a seatbelt, not a certification), `scripts/record_fixture.py` (dev tool capturing real responses into gitignored `scratch/`).
- `.gitignore`: extend the current skeleton with `scratch/`, `*.raw.json`, `output/`, `profiles/`, `browsers/`, plus the general Python set. Fixtures un-ignored by exact name.
- `requirements-dev.lock`: pinned dev toolchain (ruff/pytest/pre-commit/build/jsonschema/platformdirs), **excluding scrapling** — which is precisely what lets CI run `--no-deps` and prove the offline path.

## Repo-hygiene docs (ship the full sibling set)

`README.md`, `CONTRIBUTING.md`, `DISCLAIMER.md`, `SECURITY.md`, `CHANGELOG.md` (Keep a Changelog + SemVer), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `LICENSE` (MIT), `CLAUDE.md`, and `docs/wiki/` (Installation, Quick-Start, CLI-Reference, Output-Schema, Configuration, Security-and-Privacy, FAQ-and-Troubleshooting).

**`DISCLAIMER.md` must carry (D14) — do not soften:**
1. Reddit's *Responsible Builder Policy* requires **explicit approval** for programmatic data access; **this tool does not have it**. Using it may violate Reddit's terms; consequences (IP blocks, termination) are the user's to accept.
2. Non-commercial personal/research use only; **do not** repurpose the output as bulk or ML-training data.
3. Third-party personal data (D10): output contains other people's usernames and histories; `user --type overview` in particular makes aggregation-based de-anonymisation easy. Write to temp, never commit, delete when done.
4. **NSFW content is reachable anonymously** (`02` §9) and will be returned unfiltered when present; `over_18` is populated for callers who care.

**`README.md` must state plainly**: no account needed; a one-time `agentic-reddit setup` downloads a browser (~hundreds of MB); the practical ceiling is ~100 requests per 10 minutes; NSFW may appear.

**`SECURITY.md`** in-scope: redaction bypasses, injection via malicious API responses, browser-profile handling, and supply-chain issues in the trusted-publishing pipeline. Out-of-scope: "violates platform ToS" (a documented, intentional property) and "output files are unredacted" (by design).
