# Agentic Reddit — Plan Overview

> Planning session: 2026-07-24 (Korean interview, English artifacts). This directory is the full, self-contained plan for a **separate implementation session**. Read it in order: `00` (this) → `01-decisions` → `02-recon-findings` → `03-architecture` → `04-cli-spec` → `05-testing-and-ci` → `06-implementation-phases` → `07-skill-plan` → `IMPLEMENTATION-KICKOFF`.
>
> **This plan was pivoted mid-session.** It originally targeted Reddit's official OAuth Data API; live probing proved that path is approval-gated and unavailable to a distributable package. The transport is now a **browser-carried session**. `01-decisions.md` records both the pivot and the superseded reasoning — read it, don't skip it.

## What this is

A read-only Reddit reader: **no account, no API key, no login** — install it and read a subreddit's listing, a post and its comment tree, a redditor's activity, search (posts / subreddits / people), find subreddits, and subreddit metadata. Output is clean, schema'd JSON written to a file.

It is the fourth sibling of an existing family:

- `Agentic Facebook` (`agentic-facebook`, PyPI `agentic-facebook`)
- `Agentic X` (`agentic-x`, PyPI `agentic-twitter`)
- `Agentic Threads` (`agentic-threads`, PyPI `agentic-threads`) — in progress
- **`Agentic Reddit` (`agentic-reddit`, PyPI `agentic-reddit`)** ← this project

Each is a **CLI of single-target primitives** plus a **Claude Code skill** that chains those primitives to answer multi-hop questions. The CLI does fast structured retrieval; the *skill* (i.e. Claude) does the navigation reasoning.

**The end goal, stated by the user:** Claude should be able to explore Reddit *the way a person does* — land somewhere, read the room, follow an interesting commenter to their history, jump to a related subreddit, search for the thread everyone is referencing, and come back with an answer. That is why v1 ships the full primitive set (D3) rather than an MVP subset: the value is in the *chaining*, and a missing primitive silently amputates a whole class of question. There is deliberately no `crawl` command — the chaining is the skill's job, not a batch flag's.

## Why a CLI and not browser-use / WebFetch

- **WebFetch / WebSearch**: only surfaces the sliver of Reddit that portals index, with no schema. (`WebFetch` on `reddit.com` is outright blocked — verified 2026-07-24.)
- **browser-use (visual)**: slow (screenshot-observe loops) and can't return clean, structured post/author/date/comment fields.
- **This CLI**: returns Reddit's own `Listing` JSON — a defined, ~15-year-stable schema — per request. LLMs are language machines; hand them language-shaped data.

## The central finding (recon-proven, see `02-recon-findings.md`)

**Reddit is not "the easy one with no login." It has the hardest _access_ story of the four siblings and the easiest _data_ story.** Live recon on 2026-07-24 established:

1. **Non-browser HTTP is blocked.** `curl` from the user's own residential IP to `www.reddit.com/….json` (and `old.reddit.com`, and `oauth.reddit.com` without a token) returns **HTTP 403** with a ~190 KB JavaScript anti-bot challenge, regardless of User-Agent. The sibling pattern ("harvest cookies, replay over pure `httpx`") does not port.

2. **The official OAuth Data API is approval-gated, and therefore unusable for a distributable package.** Reddit's *Responsible Builder Policy*: *"Approval is required: You must request access and get explicit approval before accessing any Reddit data through our API."* The `prefs/apps` form still renders but the backend refuses — **verified empirically on two different Reddit accounts**. Approval is also **per-user**, so even a granted approval would not let anyone else install and run the tool.

3. **But inside a real browser, the data is pristine — and it works logged out.** A same-origin `fetch('/r/python/hot.json')` from a loaded reddit.com page returns **HTTP 200 and a clean `Listing`** — the *identical* schema the OAuth API serves. **Verified anonymously (logged out) across every v1 endpoint.**

**Consequence — the architecture:** use a **browser as the transport that carries anti-bot clearance**, then call the JSON endpoints *from inside the page*. This is **not** HTML scraping: we get the same structured `Listing`/`thing` objects, so the entire parse/model/retrieve/CLI layer is independent of the transport choice.

## Goals (v1)

1. `setup` (provision the isolated browser + warm a persistent profile past the JS challenge); `status`; `doctor`. **No `login`, no account, no credentials** (D2).
2. Read primitives, all writing schema'd JSON to a file: `subreddit <name>`, `post <url|id>` (post + adaptive comment tree), `user <name>`, `search <query>` (`--type link|sr|user`, `--subreddit`), `subreddits <query>`, `subreddit-info <name>`.
3. `catalog` (self-describing CLI, generated from the parser) + `schema` (output object schema, generated from the model).
4. **Budget-aware adaptive pacing** driven by Reddit's own `x-ratelimit-*` headers (measured: **100 requests per ~600s window**), on top of a non-bypassable floor. PII discipline. Typed errors + an exit-code contract.
5. Ship to PyPI via GitHub Actions Trusted Publishing (already configured and proven: repo `tjdwls101010/Agentic-Reddit`, workflow `publish.yml`, environment `pypi`; the `0.0.1` placeholder is already on PyPI).

## Non-goals (v1)

- **No writes** — no posting, commenting, voting, subscribing, saving, DMs. Read-only.
- **No login / no account / no personalized data** — no home feed of *your* subscriptions, no `mysubreddits`, `saved`, `upvoted`, `inbox`. `r/all` / `r/popular` cover the front-page need. Anonymous-only is a *feature* for a distributable package (D2).
- **No OAuth transport** — approval-gated, per-user (D1). Keep the transport swappable so it could return later, but don't build it.
- **No TLS-fingerprint spoofing** to defeat bot detection (e.g. `curl_cffi` impersonation). The browser is a *real* browser; that is the line (D15).
- **No `/api/morechildren`** — proven to return Reddit's HTML-render shape, not `t1` objects (D7, `02` §5.1).
- **No `crawl`/batch/daemon** — single-target primitives only.
- **No `duplicates`, wiki, trophies, multireddits, live threads, awards detail, modqueue** in v1 (candidate v1.1+).
- **The Claude skill is built in a later session**, after the package is on PyPI (`07-skill-plan.md`), using the `harness-creator` skill.

## Recon status: all gates closed

Unusually for this family, **every load-bearing unknown was closed during planning**, not deferred to implementation:

| Question | Status |
|---|---|
| Anonymous (logged-out) reads work? | ✅ **PASS** — all v1 endpoints verified logged out |
| Comment-tree expansion mechanism | ✅ `/api/morechildren` rejected; permalink-subtree GET verified |
| Pagination | ✅ `after` cursor verified, zero page overlap |
| Search types | ✅ `link`→`t3`, `sr`→`t5`, `user`→`t2` verified |
| Rate-limit model | ✅ 100 req / ~600s window, headers exposed |
| NSFW reach | ✅ Accessible anonymously (contrary to initial assumption) |
| OAuth viability | ✅ Definitively closed (2 accounts refused) |

What remains for Phase 0 is **cold-start verification under scrapling** (a genuinely fresh browser profile passing the challenge, headless vs headed) — see `06`.

## Success criteria

Every implementation phase in `06-implementation-phases.md` carries an explicit verify gate. The package is "done" for v1 when: all read primitives return schema-valid JSON from an anonymous browser session; unit tests are green offline (no network/browser in CI); and `agentic-reddit` publishes to PyPI on a GitHub Release.

## Repo / PyPI facts (verified 2026-07-24)

| Item | Value |
|---|---|
| GitHub | `https://github.com/tjdwls101010/Agentic-Reddit` (branch `main`) |
| PyPI dist | `agentic-reddit` (`0.0.1` placeholder already published) |
| Publish workflow | `.github/workflows/publish.yml`, `on: release: published`, environment `pypi`, PyPI Trusted Publishing (OIDC). **Keep this filename + environment name.** Harden to the sibling standard — see `05`. |
