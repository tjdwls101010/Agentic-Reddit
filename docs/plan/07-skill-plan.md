# Skill Plan — `.claude/skills/reddit/`

**Status:** implementation-ready. Planned 2026-07-25 in a dedicated planning session (Korean interview, English artifacts), against the **shipped** `agentic-reddit 0.1.0` — published to PyPI and tagged `v0.1.0` in this repo.

This supersedes the short sketch that lived at this path during the package-planning session. That sketch was written *before* the package existed; this document is written *after*, and every factual claim below was re-verified against the installed CLI rather than carried over on trust. Three of the sketch's claims turned out to be wrong — they are recorded in §2.2 rather than quietly deleted, because the next session should know which kinds of claims did not survive contact with the implementation.

Companion documents, to be read together:

- **`07a-SKILL-md-draft.md`** — a complete draft of `.claude/skills/reddit/SKILL.md`, ready to reconcile and place.
- **`07b-harness-spec-draft.md`** — a complete draft of `.claude/harness-spec.md`, the design record `harness-creator` audits against on any later pass.

## 1. What this skill is for, and why it needs to exist

`agentic-reddit` is deliberately a set of single-target read primitives with **no `crawl` command**. Answering a real question — "what does r/python think about type hints" — takes several hops: search for the discussion, look at what came back, pick the two or three threads that actually carry the argument, read each one's comment tree, then synthesize. Choosing those hops is judgment the CLI cannot hold, and supplying it is the entire reason this skill exists.

The skill wraps the **installed** CLI (`uv tool install agentic-reddit`), not a repo checkout. It points at `agentic-reddit catalog` and `agentic-reddit schema` for anything mechanical and spends its own tokens only on what those two cannot carry: which primitive to reach for, how to size a chain against a scarce request budget, how to tell a complete result from a truncated one, and what to do when something fails.

This is the fourth skill in the family (`facebook`, `x`, `threads`, now `reddit`). `Agentic X`'s `x/SKILL.md` is the structural template. **But Reddit differs from all three siblings in ways that make verbatim porting actively harmful** — §2.3 enumerates them, and the drafts already reflect them.

## 2. Ground truth, verified 2026-07-25

Everything in this section was checked against `agentic-reddit 0.1.0` by running the CLI or reading the shipped source. The next session should still re-verify against whatever version is installed *then* — but should treat a disagreement as "the package changed", not as "the plan was sloppy."

### 2.1 Confirmed as the sketch described

- **The file trap.** Every read command writes JSON/NDJSON to a file and prints one summary line to stderr. Nothing useful reaches stdout.
- **No login, no account, no credentials, no API key.** Anonymous only. `setup` takes no credentials of any kind.
- **Exit codes** `0/1/2/3/4/5/7` exactly as the catalog reports them.
- **Nine `stop_reason` values**: `limit_reached`, `listing_exhausted`, `no_matches`, `since_crossed`, `tree_complete`, `depth_capped`, `comment_limit`, `rate_limited`, `max_requests` (`src/agentic_reddit/retrieve.py:18-26`).
- **NSFW is reachable anonymously and is not filtered**; `over_18` is populated on `Post` and `Subreddit`.
- **Four object types** — `Post`, `Comment`, `Subreddit`, `User` — confirmed from `agentic-reddit schema --json`.
- **The rate budget** is roughly 100 requests per 10 minutes, observed from Reddit's own `x-ratelimit-*` headers.

### 2.2 Where the sketch was wrong

| # | The sketch claimed | Reality | Why it matters |
|---|---|---|---|
| C1 | "`post` supports `--depth` and `--comment-limit` only" | `post` also has **`--comment-sort`** with seven choices (`confidence` default, plus `top`, `best`, `new`, `controversial`, `old`, `qa`) | Not a trivia correction. Under a tight request budget, *which* comments you materialize matters more than how many — `--comment-sort top` buys representative opinion for a fraction of the requests a full expansion costs. This is exactly the sort of judgment the skill exists to carry. |
| C2 | "Exit 1 with `invalid choice` → out-of-date install" (inherited from all three siblings) | **That string is never printed.** See §2.3-D. | The sibling's staleness diagnostic cannot fire here. Porting it verbatim would ship advice that silently never triggers. |
| C3 | "`doctor --refresh`" is not needed here because there is no id rotation | Correct conclusion, but worth stating positively: **`doctor` has no `--refresh` flag at all** (`unrecognized arguments: --refresh`) | Threads' skill leads its exit-4 playbook with `doctor --refresh`. Reddit has **no local self-heal path** for exit 4, so its playbook has to be shaped differently, not just reworded. |

### 2.3 Reddit-specific findings that no sibling skill contains

These are the paragraphs worth their tokens. Each was measured, and none is derivable from general competence or from the other three skills.

**A. The per-invocation cap equals the entire rate window.** `config.py:21` sets `DEFAULT_MAX_REQUESTS = 100`, and every read command is wired to it (`cli.py:451,470,493,516,532,546`). Reddit's anonymous window is *also* about 100 requests per 10 minutes. So a single `agentic-reddit post` on a large thread can legitimately consume **the whole window** and leave nothing for the rest of the chain — it will stop with `stop_reason: max_requests` having done nothing wrong. Budget is therefore not a background concern to be handled when it bites; it is the thing that has to be planned before the first command runs.

**B. The stderr budget field reads `{remaining}/{used}`, not remaining-of-total.** From `cli.py:396-405`, the summary ends `budget 87/13` meaning 87 left and 13 spent. Read as "87 of 13" it is nonsense; read as "87 of 100" it is accidentally right, which is worse, because the habit breaks the moment the window is partly reset. State the format explicitly.

**C. `status --json` prints nothing to stdout when it is not ready.** Verified: exit 2 with stdout empty and `browser profile is not warmed; run agentic-reddit setup` on stderr. Anything that pipes `status --json` into a JSON parser gets an empty-input error and misdiagnoses a perfectly ordinary "browser not provisioned yet."

**D. Argparse errors longer than 80 characters are replaced wholesale.** `cli.py:28` overrides `ArgumentParser.error()` to pass every message through `redact.scrub_diagnostic()`, which at `redact.py:113` swaps any text over `_DIAGNOSTIC_TEXT_MAX_LEN = 80` for the literal `[REDACTED diagnostic text: N chars]`. Measured:

```
$ agentic-reddit nosuchcmd
agentic-reddit: error: [REDACTED diagnostic text: 157 chars]      # invalid choice — swallowed

$ agentic-reddit post abc123 --limit 5
agentic-reddit: error: unrecognized arguments: --limit 5          # 39 chars — survives
```

The `invalid choice` message is long **because it enumerates all eleven subcommands**, so it will exceed 80 characters for as long as this CLI has a meaningful command surface. The staleness signal has to come from somewhere else: the **usage line above the error still lists the valid subcommands**, so the recoverable diagnostic is "compare what you typed against the subcommand list in the usage block." The draft in `07a` teaches that instead of the sibling wording.

*(This is arguably an over-redaction bug — a usage error is not scraped content — but fixing it is package work, out of scope for the skill pass. Logged as a follow-up in §8.)*

**E. `scrapling[fetchers]` is a required dependency, not an optional extra.** X and Threads gate the browser behind a `[browser]` extra because their read path is pure HTTP; Reddit's only transport *is* the browser. So the install line is plain `uv tool install agentic-reddit` with no extras — and any "install the browser extra if you need it" phrasing ported from a sibling is wrong here.

**F. `--since`/`--until` are rejected for non-`link` searches** at `cli.py:588`, and that message (53 chars) is short enough to survive redaction, so it is visible when it fires.

**G. `post` writes the root `Post` first, then its `Comment`s**, into one file (`retrieve.py:371-379`). A reader that assumes one object type per file will mis-handle it.

**H. `catalog` emits JSON whether or not `--json` is passed** — the flag is accepted and is a no-op, same as Threads.

**J. `over_18` is tri-state, and `Comment.replies` nests recursively.** From `agentic-reddit schema --json`: `over_18` is `true`/`false`/**`null`**, where null means Reddit never marked the record — so a falsy check silently collapses "unknown" into "safe", which is the exact wrong direction for the one field whose job is to warn. `created_at` and `num_comments` are nullable too, so a sort or comparison that doesn't filter first will throw or mis-order. Separately, `Comment` carries its own `replies: Comment[]`, so the array `post` writes is `[Post, top-level Comment, …]` and its length is the count of *top-level* comments, not of the discussion — anything reporting "N comments" from the array length undercounts, often by an order of magnitude.

**I. This machine has no `pipx`; only `uv` is present.** And the two older siblings are still installed under their **pre-rebrand** names (`scraper-for-x`, `scraper-for-facebook`), so their skills point at CLIs that are not on PATH. The Reddit skill should keep mentioning `pipx` as a portable alternative — it is written for anyone, not only this laptop — but the next session must not be surprised when only `uv` is available locally, and should not "fix" the sibling installs as part of this pass.

## 3. Decisions from this session's interview

Each records the choice and the reasoning, so a later session can re-derive intent for a case this plan did not enumerate.

**S1 — Location: this repo only, `.claude/skills/reddit/`.** Same as all three siblings. The tradeoff was put explicitly to the user: a `~/.claude/skills/` symlink would make Reddit readable from any project (the pattern `harness-creator` and `repo-wiki` already use on this machine), at the cost of diverging from the family. The user chose family consistency. **Consequence to state honestly in the skill's own spec:** it loads only in sessions opened in this repo. If that becomes annoying, the fix is one symlink, not a redesign.

**S2 — `setup` is Claude's job: announce in one line, then run it.** Unlike the siblings, there is no human step — no login window, nothing for the user to type. `setup` downloads an isolated browser (hundreds of MB) and warms a profile, which takes minutes. The chosen posture mirrors the family's version-upgrade policy: **not silent** (a multi-hundred-megabyte download the user did not see is a bad surprise, and a mid-task environment change has to be diagnosable) and **not gated on a question** the user would answer "yes" to every single time.

**S3 — Budget: teach the principle, not a cost table.** A measured per-command request-cost table was offered and declined. The reasoning holds up: the cost model is *structural* (one request per listing page, one per expanded `more` node) and the skill can state that shape in a sentence, whereas a table of measured numbers invites false precision about a budget that Reddit itself reports live in every response. The skill teaches "decide the shape of the investigation before starting it, then read the `budget` field and adapt" — and leans on the fact that the real number is always on stderr, fresher than any table could be.

**S4 — exit 3: stop and report. Never wait autonomously.** `--wait-on-limit` exists and the skill should say so, but a reset window is up to ten minutes and a session that silently stalls that long is worse than one that reports "budget spent, here is what I got, say the word and I'll wait." Waiting is the user's call.

**S5 — NSFW: report, never filter or gate.** `over_18` gets checked and surfaced faithfully; nothing is blocked and no confirmation is demanded. This matches package decision D6 (filtering is the caller's judgment) and avoids obstructing a user who deliberately named an adult subreddit. The skill's job is to make sure the model *knows* — since anonymous access reaches NSFW freely, assuming a safe surface is the actual failure mode.

**S6 — Tool boundary: rely on the `description`, do not lecture about WebFetch.** An explicit "don't use WebFetch on reddit.com" paragraph was proposed and declined, and on reflection the decline is right: once the skill triggers, its body already directs every read through `agentic-reddit`, so the only real exposure is the skill *failing to trigger* — which is a `description`-quality problem, not a body-content problem. It is therefore handled where it belongs, in **validation scenario V6** (a bare `reddit.com` URL must trigger the skill). Noted for the record: **Ultra Fetch is a genuine future collision** — it claims to be the default reader for bot-protected pages and names only `scrape-x`/`scrape-fb` as exceptions, so an anonymous Reddit URL falls inside its stated scope. Today the two never co-load (each lives in its own repo), so this is a follow-up (§8), not a blocker.

**S7 — Version policy: identical to the siblings.** Check `agentic-reddit --version` against the PyPI **simple index** at task start; if behind, say so in one line and upgrade before doing the user's actual work. Reddit's staleness risk is genuinely lower than X's or Threads' (no `doc_id`/transaction-id rotation to chase), and that asymmetry is worth stating in the skill so the model does not over-apply urgency — but the check costs ~40ms, response-shape drift (exit 4) still ships its fix as a release, and family consistency has its own value.

**S8 — Teach `--comment-sort` as judgment, not as a flag.** The skill does not restate the seven choices (the catalog has them). It teaches the decision: on a thread too large to expand within budget, sorting by `top` and going *deeper on less* beats spreading a shallow pass across everything, because the question is almost always "what does this community think", not "enumerate every comment."

**S9 — Single file, no `references/`, no `scripts/`.** A retrieval task needs the budget rule, the file trap, the object-type map, the completeness semantics, and the failure playbook *together*, on every invocation. There is no branch point where the model would pick one variant over another, so there is no seam to split on; splitting on length alone would add a routing decision that buys nothing and would risk the budget and PII stop-rules hiding behind a conditionally-loaded file.

**S10 — English artifact, Korean interview.** Package decision D12, unchanged.

## 4. Component spec

**One skill.** `.claude/skills/reddit/SKILL.md`, single file. Plus `.claude/harness-spec.md` as the design record.

**No hooks, no permissions, no agents, no workflows.** Every command is read-only by construction, and the package clamps its own non-bypassable 1.0s request floor plus a header-driven budget governor in code. There is nothing left to enforce deterministically that the package does not already guarantee; a hook here would be enforcement theatre.

**Frontmatter** — full text in `07a`. Shape:

- `name: Reddit retrieval`
- `description:` triggers on any "get something off Reddit" phrasing plus a bare `reddit.com` / `redd.it` URL, and names the near-misses out of scope: developing the package itself, and Facebook / X / Threads / other networks.
- `allowed-tools: Bash(agentic-reddit:*), Bash(uv:*), Bash(pipx:*), Bash(curl:*), Read` — exactly the commands the body calls, including the version check and the upgrade.

**Body outline** (drafted in full in `07a`):

1. Step 1 — get the tool, and get the current one (S7; plain install, no extras, per §2.3-E)
2. Step 2 — ask the CLI what it can do (`catalog`; never restate flags)
3. Step 3 — readiness and `setup` (S2; no account anywhere in the picture; §2.3-C)
4. The file trap
5. Four object types, not two (§2.3-G; `captured_at` is scrape time)
6. **Budget before breadth** — the section that most distinguishes this skill (§2.3-A, §2.3-B, S3, S4)
7. What each primitive is for, and chaining (S8; worked chains; bound the fan-out, report the shape)
8. `stop_reason` — complete vs truncated (`tree_complete` vs `depth_capped`/`comment_limit`; exit 7)
9. ToS posture (package D14 — state it plainly, do not soften)
10. Third-party data and NSFW (package D10, S5)
11. When something fails (§2.3-D; exit 4 has no local self-heal, §2.3-C)

## 5. Implementation steps for the next session

Because `07a` and `07b` are complete drafts, the next session's job is reconciliation and proof, not composition. In order:

1. **Install the real thing.** `uv tool install agentic-reddit`, then `agentic-reddit --version`. Confirm it resolves on PATH and is ≥ the PyPI simple-index version. *Verify:* `which agentic-reddit` is not the repo `.venv`.
2. **Re-verify every factual claim in `07a`** against that install — `catalog`, `schema`, `--version`, the redaction behaviour in §2.3-D, and `status`'s exit code. *Verify:* each of §2.1 and §2.3 either reproduces or is corrected in the draft **and** noted in the harness-spec's change history. Do not skip this because the plan looks confident; the plan was written against `0.1.0` and the install may not be.
3. **Provision the browser.** `agentic-reddit setup` (this is also live coverage of S2). *Verify:* `agentic-reddit status` exits 0.
4. **Place the files.** `.claude/skills/reddit/SKILL.md` from `07a`, `.claude/harness-spec.md` from `07b`, with any corrections from step 2 folded in. *Verify:* both files exist and the frontmatter parses.
5. **Validate structurally.** `python3 "/Users/seongjin/.claude/skills/harness-creator/scripts/validate_harness.py" --path .` *Verify:* exits 0 with zero errors. `test_hook.py` does not apply — no hooks are generated.
6. **Re-read the `description` against `harness-creator`'s `references/skills.md`** triggering guidance. `validate_harness.py` does not grade trigger quality, so this is a manual pass. *Verify:* the description names the near-misses and would fire on a bare URL.
7. **Run the seven e2e scenarios** in §6. *Verify:* results recorded in the harness-spec's validation table, honestly, including anything that fails or is skipped.
8. **Git flow** per §7.

## 6. Validation plan — seven scenarios

Reddit is the first of the four siblings where **live e2e is genuinely cheap and safe**: there is no account, so there is no ban risk, and the only cost is request budget that refills in ten minutes. Threads could only run 3 of its 5 scenarios because it had no logged-in session; Reddit has no such excuse and should run all seven.

Practical notes for whoever runs these: keep every capture in `/tmp`, never in the repo. Space the live scenarios so they do not collide inside one 10-minute window — V1 through V3 together can plausibly approach the budget, and a scenario that fails because a *previous scenario* spent the window is a false negative. Use `run_e2e.py --isolate` for the non-trigger scenarios so package-development work happens in a throwaway copy.

| # | Scenario | What it proves | Expected |
|---|---|---|---|
| V1 | "What are the top posts in r/python this week?" | The happy path end to end: trigger, readiness check, `--output` to `/tmp`, `Read` the file, summarize | Skill triggers; `subreddit python --sort top --time week --limit N --output /tmp/…`; answer cites real posts; capture cleaned up |
| V2 | "Summarize the discussion on this thread: `<a real reddit.com permalink>`" | The comment tree, the four-object-type reading, and **honest completeness reporting** | `post <url>` with a sized `--depth`/`--comment-limit`; the reply distinguishes `tree_complete` from `depth_capped`/`comment_limit` **in the user-visible answer**, not just internally |
| V3 | "What do redditors think about `<topic>`? Find the discussion and summarize it." | The multi-hop chain that justifies the skill, and budget-shaped planning | `search --type link` → pick 2–3 by `num_comments` → `post` each → synthesize; the reply states the shape ("read 3 of 27 threads") rather than implying completeness |
| V4 | "Add a `--csv` output option to agentic-reddit's subreddit command." | Non-trigger: developing the package is ordinary repo work | Skill does **not** trigger; the session edits `src/` in the isolated copy and never invokes retrieval |
| V5 | "What has `<person>` been posting on Threads lately?" | Non-trigger: sibling-network confusion, the most likely false positive in a family of four | Reddit skill does **not** trigger |
| V6 | A bare `https://www.reddit.com/r/<sub>/comments/<id>/…` URL with "what's this about?" | **The S6 bet.** Trigger quality is the only thing standing between the model and reaching for WebFetch | Skill triggers on the URL alone, with no "reddit" keyword in the sentence |
| V7 | "Read r/`<a subreddit that does not exist>`" | The failure playbook, on the one exit code that is cheap to provoke deliberately | Exit 5; reported as unavailable and **not retried**; no wasted budget |

Scenarios that are deliberately **not** in the list, and why: provoking exit 3 (budget spent) would cost a full ten-minute window to prove a rule the skill states plainly, and exit 4 (response drift) cannot be provoked at all without Reddit changing its response shape. Both are covered by inspection of the draft's failure section rather than by a live run — record them that way in the harness-spec, honestly labelled, rather than omitting them.

## 7. Git, PR, and release plan

Following the Threads precedent exactly (its plan landed as PR #4, its skill as PR #5):

- **This session:** branch `docs/reddit-skill-plan` → commit these three documents → push → PR → merge. Nothing else changes; no code, no version bump.
- **Next session:** branch `feat/reddit-skill` → the `.claude/` files → PR → merge.
- **No PyPI release for either.** `.claude/` is not part of the wheel (`[tool.hatch.build.targets.wheel] packages = ["src/agentic_reddit"]`), so the skill ships no Python artifact and the installed CLI is unaffected. A version bump would advertise a change to users who cannot observe one.
- **CHANGELOG:** the skill pass may add an `### Added` line under `[Unreleased]`, since the repo does document non-code additions there. A plan-document PR does not need one.
- **CLAUDE.md:** leave it alone. None of the three siblings' CLAUDE.md files mention their skill, and this repo's CLAUDE.md is a list of package constraints that a skill file does not change. Adding a pointer would break family consistency for no gain — `harness-creator`'s "update CLAUDE.md pointers if needed" resolves to "not needed" here.

## 8. Follow-ups — noted, deliberately not done in this pass

1. **Over-redaction of argparse usage errors** (§2.3-D). `cli.py:28` routes usage errors through a scrubber meant for scraped-content diagnostics, so any message over 80 characters — including every `invalid choice` — is destroyed. Worth a package fix: exempt argparse's own errors, or redact by pattern rather than by length. Package work; not part of the skill pass.
2. **Ultra Fetch boundary** (S6). Add a "Reddit → use `agentic-reddit`" exception to Ultra Fetch's `description`, alongside its existing `scrape-x`/`scrape-fb` exceptions, whenever Ultra Fetch is next touched.
3. **Stale sibling installs** (§2.3-I). `scraper-for-x` and `scraper-for-facebook` are installed under pre-rebrand names, so the `x` and `facebook` skills reference CLIs that are not on PATH. Unrelated to Reddit; fix when convenient.
4. **Family-wide skill location** (S1). Decided per-repo for the fourth time. If reading these networks from arbitrary projects ever becomes the norm, symlink all four into `~/.claude/skills/` in one pass rather than deciding again per package.
