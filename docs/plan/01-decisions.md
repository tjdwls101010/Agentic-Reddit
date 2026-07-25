# Decision Log

Decisions agreed with the user during the 2026-07-24 planning interview (Korean), most via explicit AskUserQuestion. Each records the choice **and the reasoning**, so the implementer can re-derive intent for cases the plan didn't enumerate.

> **This log contains a mid-session pivot.** D1/D2/D5/D14 were originally decided in favour of Reddit's official OAuth Data API, then **overturned by evidence** when app registration proved approval-gated. The superseded reasoning is preserved at the bottom — it is not dead weight: it records *why* OAuth is not an option, so a future session doesn't re-litigate it. D6, D7 and D8 were later **revised by live measurement**.

---

### D1 (REVISED) — Transport = a real browser carrying the session; JSON fetched same-origin

**Choice (user):** Drive a real browser (scrapling), load `reddit.com` once so the JS anti-bot challenge clears, then call Reddit's `.json` endpoints with **same-origin `fetch()` from inside the page**.

**Rejected:** (a) OAuth Data API — approval-gated and per-user, so a distributed package can't rely on it (see D1-OLD); (b) pure-`httpx` replay — blocked by the anti-bot from any IP/User-Agent; (c) HTML scraping — unnecessary and lossy.

**Why this is not a downgrade:** the in-page `fetch` returns the **identical clean `Listing`/`thing` JSON** the OAuth API would have returned (proven in recon, logged out). The browser is *only* a transport carrying anti-bot clearance; the parse/model/retrieve/CLI layers are unchanged.

**Factoring rule:** keep the transport behind one narrow interface (`get_json(path) -> dict`) so an OAuth or cookie-replay transport can be swapped in later without touching anything above it.

### D2 (REVISED) — Anonymous only: no login, no account, no credentials

**Choice (user, AskUserQuestion):** v1 is **logged-out only**. No `login` command, no credential store, no session file, no account.

**Why:** the stated goal is *"so other people can use this package too"* — anything requiring each user to have/risk a Reddit account (or obtain an approval) defeats distribution. Anonymous also means **zero account-ban risk** and **no credential PII to protect**.

**Status: VERIFIED.** Every v1 endpoint was re-tested from a logged-out browser on 2026-07-24 and returned clean JSON (`02` §3). This decision no longer rests on an assumption.

### D3 — Command surface = full sibling-parity (not an MVP subset)

**Choice (user):** v1 ships the full Reddit-native set: `subreddit`, `post`, `user`, `search`, `subreddits`, `subreddit-info`, plus `setup`/`status`/`doctor`/`catalog`/`schema`.

**Why:** the goal is Claude navigating Reddit like a person. Missing primitives (find-subreddits, subreddit metadata) break the chaining that justifies the tool — e.g. "find active subreddits about X, then read each" needs `subreddits` *and* `subreddit`; "who is this commenter and what else do they say" needs `user`.

### D4 — Command naming = Reddit-native scheme (confirmed via preview)

**Choice (user, previewed):** Reddit-concept names, not sibling verbs. `subreddit <name>` (listing; `all`/`popular` = front page), `post <url|id>` (post + comment tree), `user <name>` (a redditor's activity via `--type`), `search <query>`, `subreddits <query>`, `subreddit-info <name>`.

**Rejected:** sibling-style `fetch`/`feed` verbs — they blur Reddit's subreddit-vs-user distinction.

**Sub-decisions:** there is **no `login` command** (D2) and **no separate `feed` command** — the public front page is `subreddit popular` / `subreddit all`.

### D5 (REVISED) — `setup` provisions the browser; there are no user credentials

**Choice:** `setup` installs the isolated browser binary (scrapling/Playwright into an app-owned `browsers/` dir) and warms a **persistent browser profile** by loading `reddit.com` until the challenge clears, so later commands skip it. It takes **no credentials of any kind** — no client_id, no password, no cookies.

**Why:** D1+D2 removed every credential from the design. This is the smallest possible first-run story: `pip install` → `agentic-reddit setup` → read.

**Safety rule retained:** never accept, store, or transmit a Reddit account password under any circumstance.

### D6 (REVISED by measurement) — NSFW/over_18: return as-is, mark `over_18`; no filtering

**Choice (user):** Return whatever the endpoints yield; expose `over_18` on the model; build no filtering.

**Correction to the original note:** the first draft claimed anonymous sessions are not age-verified so NSFW would be largely absent. **That was wrong.** Measured 2026-07-24 logged out: `/r/nsfw/about.json` → 200 (`over18: true`, 4.58M subscribers), `/r/gonewild/about.json` → 200 (5.56M), `/r/nsfw/hot.json` → 200 with `over_18: true` items. **NSFW is fully reachable anonymously.**

**Consequence:** because it *is* reachable, `over_18` must be populated faithfully on every `Post`/`Subreddit`, the README must state that NSFW content can be returned, and the skill (`07`) must tell Claude to check `over_18` rather than assume the surface is safe. Still no filtering flag — that is the caller's judgment.

### D7 (REVISED by recon) — Comment tree = adaptive expansion via **permalink-subtree GETs**

**Choice (user):** `post <url|id>` returns the post **plus its comment tree**, expanding collapsed `more` nodes within a `--depth`/`--comment-limit` budget and reporting honestly whether the tree was complete.

**Why:** a Reddit post *is* its discussion; top-level-only (rejected alt) is useless on large threads.

**Mechanism revised after live testing (`02` §5.1–5.2):** `/api/morechildren` **cannot be used** — from the `www` origin it returns Reddit's HTML-render shape (`content`/`contentHTML`/`contentText`) rather than `t1` objects, under every param variant tried (`raw_json=1`, `renderstyle=json`). Expansion instead uses the **permalink-subtree GET** `/r/<sub>/comments/<post_id36>/_/<comment_id36>.json?limit=100&depth=N`, verified (logged out) to return a clean `t1` root with nested `Listing` replies. Splice each returned subtree in place of its `more`; **no `parent_id` re-threading step is needed.**

**Consequences to respect:** one request per expanded `more`, against a hard budget of ~100 requests per 10 minutes (D8) — so large threads are budget-bound *by physics*, not by choice. A 13.5k-comment thread cannot be fully expanded; don't try. **Top-level `more` nodes (`parent_id` = `t3_…`) have no parent comment to root on** — Phase 0 (Q-C) must choose between raising the initial `limit`, per-child GETs under budget, or reporting the remainder unexpanded.

### D8 (REVISED by measurement) — Budget-aware adaptive pacing, not a naive fixed floor

**Measured 2026-07-24, logged out:** Reddit returns `x-ratelimit-used`, `x-ratelimit-remaining`, and `x-ratelimit-reset` on every `.json` response. Observed `used + remaining = 100` and `reset` counting down in real seconds from a ~600s window. **The anonymous budget is ~100 requests per ~10 minutes ≈ one request per 6 seconds sustained.**

**Choice:** a two-part strategy, both non-bypassable:

1. **Floor:** `MIN_REQUEST_PAUSE_SECONDS = 1.0`, clamped in code regardless of flag/env, with a stderr note when a lower value is raised. This permits a short burst for small jobs.
2. **Budget governor (the important half):** parse `x-ratelimit-remaining` / `x-ratelimit-reset` on every response and pace against them — when `remaining` is low relative to `reset`, stretch the delay toward `reset / remaining`; when `remaining` hits zero, stop with `stop_reason=rate_limited` (or wait if `--wait-on-limit`, bounded by `--max-wait`). Never retry-loop on 429.

**Why not simply a 6s floor:** it would make small jobs needlessly slow. Why not just 1.0s: it exhausts the window in 100s and spends the next 500s in 429s. The headers make the correct behaviour observable, so use them — this is strictly better than the siblings' fixed-floor approach and should be treated as a *feature* of this package.

**Implication for the skill (`07`):** request budget is the scarce resource. Bound fan-out before starting; a deep comment expansion and a wide multi-subreddit sweep compete for the same 100 requests.

### D9 — Output model: file + one-line stderr summary; Claude reads the file

**Choice:** Every read command writes results to a `--output` path (default: a timestamped file under the platform data dir, **never cwd/repo**) and prints only a one-line summary to stderr. `--format json` (array) or `ndjson`.

**Why:** proven sibling pattern; hands context control to Claude and keeps third-party PII out of the repo.

### D10 — Third-party data is public **but still personal**; PII discipline unchanged

**Choice:** Treat all scraped output as third-party PII (usernames, post/comment histories): temp paths not the repo, never `git add` captures, fixtures are hand-authored synthetic skeletons, a CI/pre-commit PII scanner, redaction on all diagnostic surfaces (never the output file itself).

**Why:** "public" ≠ "not personal." Same GDPR/privacy posture as the siblings. Reddit sharpens this: pseudonymous accounts are routinely de-anonymised by aggregating their history, which is exactly what `user --type overview` makes easy.

### D11 — Naming triple + clean env prefix

**Choice:** PyPI dist `agentic-reddit`; import package `agentic_reddit`; console command `agentic-reddit`. Env override `AGENTIC_REDDIT_PROFILE_DIR`. `__version__` in `src/agentic_reddit/__init__.py`, gated three-ways (tag == pyproject == source) at release by `scripts/check_tag_version.py`.

### D12 — English artifacts

**Choice:** SKILL.md, code, comments, docstrings, README, wiki, CLI output — all English. The planning interview is Korean. **Why:** matches all three siblings; most stable substrate for skill-triggering and technical vocabulary.

### D13 — The skill is a later, separate session

**Choice:** Build the package first, publish to PyPI, THEN build `.claude/skills/reddit/SKILL.md` in a fresh session using the `harness-creator` skill. It wraps the *installed* CLI and points at its `catalog`/`schema`. See `07-skill-plan.md`.

### D14 (REVISED) — ToS posture: same gray zone as the siblings; say so plainly

**Choice:** Because the OAuth path is closed (D1), this tool reads Reddit **without the approval Reddit's policy requires**. That places it in the **same ToS-gray position as `Agentic Facebook` / `Agentic X` / `Agentic Threads`** — the posture the user has knowingly adopted three times.

`DISCLAIMER.md` must state this **plainly and without softening**: Reddit's *Responsible Builder Policy* requires explicit approval for programmatic data access; this tool does not have it; users accept the consequences (IP blocks, ToS termination) and must not use it commercially or to build bulk/ML-training datasets. Keep the third-party-PII section (D10). **Do not** weaken this to "it's just public data."

### D15 (NEW) — Line drawn: a real browser, yes; forging fingerprints to defeat bot detection, no

**Choice (assistant, accepted by user):** The transport may be a **real browser** with a real profile. It must **not** be a TLS-fingerprint impersonation library (`curl_cffi`, `tls-client`, etc.) whose purpose is to defeat Reddit's bot detection, and the implementation should avoid piling on evasion patches beyond scrapling's default. Prefer the **most minimal** stealth configuration that works; do not port an aggressive `_stealth_init.js` evasion layer unless Phase 0 proves it necessary — and if it does, surface that to the user rather than quietly adding it.

**Why:** driving a real browser is ordinary automation; forging a client's identity specifically to evade bot detection is not something this project will ship.

### D16 (NEW) — Browser stack = scrapling (sibling consistency)

**Choice (user, AskUserQuestion):** Use `scrapling[fetchers]` rather than raw Playwright.

**Why:** all three siblings use it, its browser-install/session/persistent-context handling is already solved and understood, and local docs are cached at `../.tmp/docs_scrapling/` (incl. a Korean README).

**Consequence:** scrapling is a **base dependency**, not a `[browser]` extra — the browser is in the read hot-path, so a browser-less install would be non-functional. There is **no `httpx` dependency at all** (every request goes through the page).

---

## Superseded decisions (kept for the record — do not re-litigate)

**D1-OLD — OAuth Data API transport.** Originally chosen because `oauth.reddit.com` bypasses the anti-bot with a Bearer token, returns the same clean schema, needs no browser, and app registration *appeared* self-service (the `prefs/apps` form renders with web/installed/script radios and a create button).

**Why it was overturned:** the form's backend rejects creation. Reddit's *Responsible Builder Policy* states *"Approval is required: You must request access and get explicit approval before accessing any Reddit data through our API"*, steers non-commercial developers to the Developer Platform (Devvit), and reserves new Data API apps for *"a valid moderation use case."* **Empirically confirmed: two separate Reddit accounts were both refused app creation** (a 1-day-old account and an established one), so this is a policy gate, not an account-quality heuristic. The policy also forbids *"registering multiple accounts … for the same use case"*, foreclosing account-shopping. Decisively, approval is **per-user**, so even a successful approval would not make the package usable by anyone else — the user's stated goal.

**Residual value:** if Reddit ever grants approval, D1's interface rule means an OAuth transport can be added behind `get_json(path)` with no changes above it. The recon-verified endpoint/param/schema tables in `02` apply to `oauth.reddit.com` verbatim (drop `.json`).

**D2-OLD — userless (app-only) token, public data only.** Made moot by D1-OLD's removal; its *scope* conclusion survives unchanged as D2 (public data only, no personalized surfaces).

**D5-OLD — `client_id` + optional `client_secret` credential input.** Fully removed; there are no credentials now (D5).

**D14-OLD — "sanctioned tool, honor the Data API Terms."** Overturned: without approval this is not a sanctioned integration, so the DISCLAIMER reverts to the siblings' gray-zone framing (D14).

---

## Open questions remaining for Phase 0

The data-layer unknowns were all closed during planning (see `00` "Recon status"). What remains is **cold-start behaviour under scrapling**, which could not be tested from Claude-in-Chrome:

- **Q-1 (GATE) — Does a genuinely fresh scrapling profile pass the JS challenge?** All recon ran in a Chrome profile that had already visited Reddit and held clearance cookies. A brand-new profile must execute the challenge from scratch. Verify: fresh profile dir → load `reddit.com` → poll until a real Reddit document renders → `fetch('/r/python/hot.json')` → 200. **If this fails, halt and consult the user** — it is the only remaining single point of failure.
- **Q-2 — Headless or headed?** Headless is far better UX for a distributed CLI (no window per command). Determine whether headless passes the challenge. If only headed works, decide with the user between a headed default and a `--headed` fallback. Related: how long does clearance persist in the profile (does `setup` need re-running)?
- **Q-3 — Top-level `more` handling.** Choose between raising the initial `limit`, per-child permalink GETs under budget, or reporting the remainder unexpanded (D7).
- **Q-4 — Rate-window confirmation.** Confirm the ~600s window length and whether it is per-IP or per-profile, and confirm the governor's behaviour at `remaining == 0` (429 shape, `retry-after` presence).
- **Q-5 — `over_18` fidelity.** Confirm `t3.over_18` and `t5.over18` map correctly through the model (note the different spellings), and that the `about` vs listing spellings are both handled.
- **Q-6 — Anonymous edge cases.** Private/banned/quarantined subreddits, suspended/deleted users, deleted posts: capture the exact anonymous response shapes so `NotFoundError`/`TargetUnavailableError` (exit 5) map correctly rather than surfacing as parse errors.
