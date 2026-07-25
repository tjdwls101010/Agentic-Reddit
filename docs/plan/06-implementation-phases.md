# Implementation Phases (with verify gates)

Ordered; loop each phase until its verify gate passes. Prefer many small green steps over one big one.

**Budget discipline while developing:** the anonymous ceiling is ~100 requests per ~600 s (`02` §4). Live probing burns the same budget your tests do. Cache real responses into gitignored `scratch/` and re-run parsers against files, not the network.

---

## Phase 0 — Cold-start verification under scrapling (do NOT skip)

Unusually for this family, the *data* layer was fully verified during planning (see `00` "Recon status") — every endpoint, the comment-tree mechanism, pagination, search types, the rate model, and NSFW reach were all confirmed **logged out**. What planning could **not** test is scrapling's cold start, because all recon ran in a Chrome profile that already held anti-bot clearance.

Resolve the open questions from `01-decisions.md`:

- **Q-1 (GATE — the only remaining single point of failure)** — a **genuinely fresh** scrapling persistent profile: launch → load `https://www.reddit.com/` → poll until a real Reddit document renders → same-origin `fetch('/r/python/hot.json')` → expect **200 + `Listing`**. **If this fails, halt and consult the user.** Do not reach for fingerprint-spoofing (D15).
- **Q-2** — headless vs headed: does headless clear the challenge? How long does clearance persist in the profile (does `setup` need periodic re-running)? If only headed works, raise it with the user before defaulting to a window-per-command UX.
- **Q-3** — top-level `more` (`parent_id` = `t3_…`): choose between raising the initial `limit`, per-child permalink GETs under budget, or reporting the remainder unexpanded.
- **Q-4** — confirm the ~600 s window length, whether the budget is per-IP or per-profile, and the exact shape at `remaining == 0` (429 body, `retry-after` presence).
- **Q-5** — `over_18` (`t3`) vs `over18` (`t5`) both map correctly through the model.
- **Q-6** — capture anonymous response shapes for private / banned / quarantined subreddits, suspended / deleted users, and deleted posts, so exit 5 maps correctly instead of surfacing as a parse error.

**Verify:** a scratch script cold-starts a fresh profile and pulls one page from each of the six read endpoints, saving raw bodies to `scratch/` as future fixture sources. Update `02-recon-findings.md` if reality differs.

## Phase 1 — Scaffold + packaging + offline commands

`src/agentic_reddit/` skeleton, `pyproject.toml` (deps = `scrapling[fetchers]` + `platformdirs`, **no httpx, no `[browser]` extra**), `config.py` (paths + floor + constants), `errors.py` (typed + exit codes), `__init__.py` (`__version__`). Implement `catalog` + `schema` end-to-end against a stubbed `model.py`. Set up CI (`ci.yml`), harden `publish.yml` (keep filename + `pypi` environment; add the three-way version gate; pin the publish action SHA), pre-commit, scripts, `.gitignore`, root doc stubs.

**Verify:** `agentic-reddit --version/--help/catalog/schema/schema --json` all work **with no browser launched and `scrapling` absent from `sys.modules`**; `ruff` clean; `test_offline_commands.py` green; the `--no-deps` smoke job green.

## Phase 2 — Browser session + pacing + setup/status/doctor

`session.py` (`BrowserSession`: lazy scrapling import, persistent context under `profiles/<name>/browser/`, isolated `PLAYWRIGHT_BROWSERS_PATH`, `warm()` poll loop, `get_json()` via in-page `fetch` returning body **and** `x-ratelimit-*` headers, `close()`), `pacing.py` (floor + budget governor), `identity.py`, and the `setup`/`status`/`doctor` commands.

**Verify:** `agentic-reddit setup` provisions the browser and warms a fresh profile (Q-1/Q-2 satisfied); `status` exits 0 and reports remaining budget; a second invocation reuses the warm profile without re-solving the challenge; `get_json` on a challenge/HTML body raises `ChallengeError` (exit 4); the 1.0 s floor is observed and cannot be bypassed. `test_session.py`/`test_pacing.py`/`test_identity.py` green (all with fakes, no Chromium).

## Phase 3 — Read vertical slice: `subreddit`

`endpoints.py` (`subreddit_path`), `parse.py` (`Listing` walk + `after`), `model.py` (`Post`/`Media` + `to_dict` + schema), `retrieve.py` (`fetch_subreddit` with `after` pagination + limit/since/until), and the `subreddit` subcommand end-to-end (file output + stderr summary incl. remaining budget).

**Verify:** `agentic-reddit subreddit python --sort new --limit 20 --output /tmp/p.json` writes schema-valid `Post` JSON from a live anonymous session; `--limit`, `after` EOF, and `--since` behave; `jsonschema` validates the output; pacing is observed and the summary reports budget. Unit slices of `test_parse.py`/`test_model.py`/`test_retrieve.py` green.

## Phase 4 — Remaining read primitives

Add:
- **`post`** — 2-element array split; comment forest with recursive `replies`; **adaptive expansion via permalink-subtree GETs** (`02` §6.2) with splice-in-place; `Comment` model; `tree_complete`/`depth_capped`/`comment_limit` stop reasons; the Q-3 decision for top-level `more`. **Do not use `/api/morechildren`** (`02` §6.1).
- **`user`** — `--type overview|submitted|comments|top`, emitting mixed `Post`+`Comment`.
- **`search`** — `--type link|sr|user` (three output types) and `--subreddit` (`restrict_sr=1`).
- **`subreddits`** — `Subreddit` output.
- **`subreddit-info`** — single `Subreddit` (mind the `over18` spelling, Q-5).

Extend `endpoints.py`, `parse.py`, `model.py`, `retrieve.py` per command.

**Verify:** each command returns schema-valid output from a live anonymous session with the correct `stop_reason`; `post` fully expands a small thread (`tree_complete`) and honestly reports truncation on a large one; `search --type sr|user` emit `Subreddit`/`User`; date filters and limits behave. Fixture unit tests for every op green; `test_cli.py` catalog/exit-code coverage green.

## Phase 5 — Hardening + docs + release prep

`redact.py` wired to all diagnostic surfaces; challenge detection everywhere JSON is expected; Q-6 unavailability shapes mapped to exit 5; `--wait-on-limit`/`--max-wait` verified against a real budget exhaustion. Write `README.md`, `CHANGELOG.md`, `DISCLAIMER.md` (D14 — all four points, unsoftened), `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CLAUDE.md`, `LICENSE`, and `docs/wiki/`. Bump to the release version.

**Verify:** full offline suite green on both CI legs; `--no-deps` smoke green; a **live e2e pass** exercising every command against an anonymous session (documented, outputs deleted, no PII committed) — budget the run, it cannot be done in one 10-minute window; `git tag` == `pyproject` == `__init__.__version__`.

## Phase 6 — Publish

Open PR → merge to `main` → create a GitHub **Release** (triggers `publish.yml` → PyPI Trusted Publishing). Confirm `pip install agentic-reddit` installs the `agentic-reddit` command and `--version` matches.

**Verify:** installable from PyPI; on a clean machine, `uv tool install agentic-reddit` → `agentic-reddit setup` → `agentic-reddit subreddit python` works end-to-end **with no Reddit account and no API key**.

## Phase 7 — The Claude skill (SEPARATE later session)

Not part of the package build. See `07-skill-plan.md`.

---

## Hard constraints (do not violate — from CLAUDE.md + the siblings + this project)

- **Minimum code, surgical changes, no speculative abstractions or unrequested features.** Scope-outs (writes, login/accounts/credentials, personalized data, OAuth, `duplicates`/wiki/trophies/multireddits/live, `crawl`/batch/daemon) — don't build them.
- **Transport: browser only.** No `httpx`, no cookie/credential store, no `login` command. Keep everything above `session.get_json()` transport-agnostic (D1).
- **No TLS-fingerprint spoofing** (`curl_cffi`, `tls-client`) and no aggressive evasion layer beyond scrapling's minimal default. If Phase 0 seems to require more, **ask the user first** (D15).
- **`/api/morechildren` is forbidden** — it returns HTML-render shapes, not `t1` (`02` §6.1).
- **Pacing is non-bypassable**: the 1.0 s floor plus the header-driven budget governor apply on every request from every entry point. Never retry-loop on 429.
- **Lazy scrapling import**: offline commands (`--version`/`--help`/`catalog`/`schema`) must never import scrapling or launch a browser.
- **PII**: `scratch/`, `*.raw.json`, `output/`, `profiles/`, `browsers/` gitignored; fixtures synthetic + PII-scanned; never commit real captures.
- **DISCLAIMER tone is not to be weakened** (D14). NSFW is reachable and must be documented, not hidden (D6).
- If a scope change beyond this plan seems needed, **ask first**.
