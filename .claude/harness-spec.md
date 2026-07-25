# Harness Spec — agentic-reddit

## Context

Python 3.11+ package (`agentic-reddit`, CLI `agentic-reddit`, PyPI dist `agentic-reddit`), hatchling build, pytest + ruff, single maintainer. Published to PyPI; v0.1.0 shipped 2026-07-25. The repo already carried a project-specific `CLAUDE.md` (package constraints: read-only, anonymous-only, no evasion, lazy browser imports, PII discipline) before this pass; this pass adds `.claude/skills/` and this spec. Interview in Korean; generated harness in English (matches the three siblings and all CLI output). User is fluent in Claude Code vocabulary and reasons about tradeoffs directly.

**Sibling precedent.** This is the fourth retrieval skill in the family after `agentic-facebook`, `agentic-x`, and `agentic-threads`. `agentic-x`'s `x/SKILL.md` is the structural template. But Reddit is the family member that diverges most, and the divergences are load-bearing rather than cosmetic — see D3 through D6. The planning session verified each sibling-inherited claim against the shipped CLI rather than porting it, and three claims did not survive (recorded in `docs/plan/07-skill-plan.md` §2.2).

**Planning/implementation split.** The design was settled in a dedicated planning session that produced `docs/plan/07-skill-plan.md` (the plan and its decision log), `07a-SKILL-md-draft.md` (a complete SKILL.md draft), and `07b-harness-spec-draft.md` (this file's source). Those three documents are the authoritative rationale; this spec is the summary `harness-creator` audits against.

## Goals

Let Claude read Reddit through the published `agentic-reddit` CLI and **chain the primitives itself** — the CLI has no `crawl` command by design, so deciding which thread or community to open next is the skill's whole reason to exist.

The skill must NOT restate the CLI's flags — `agentic-reddit catalog` is generated from the parser and is correct for whatever version is installed, so a copy in the skill would describe the wrong version the moment the package updates.

The `description` must trigger on any "get something off Reddit" phrasing **including a bare reddit.com / redd.it URL with no mention of Reddit in the sentence**, and must correctly not trigger on two near-misses: developing the package itself (ordinary repo work), and the three sibling networks plus any other social network.

## Behavior inventory

| id | behavior/knowledge/constraint | layer | component | status |
|----|-------------------------------|-------|-----------|--------|
| B1 | Install into an isolated env (`uv tool`/`pipx`), never shared `pip` — scrapling pins Playwright | skill | reddit | generated |
| B2 | Check installed version against the PyPI **simple index** at task start; if behind, announce + upgrade | skill | reddit | generated |
| B3 | **No `[browser]` extra** — scrapling is a required dependency here, not optional as in X/Threads | skill | reddit | generated |
| B4 | Staleness risk is genuinely lower than the siblings' (no id rotation); say so rather than over-applying their urgency | skill | reddit | generated |
| B5 | `catalog` / `schema` are the flag and output contracts; never restate them in prose | skill | reddit | generated |
| B6 | **No account, no login, no credentials, ever** — exit 2 is provisioning, not authentication | skill | reddit | generated |
| B7 | Claude runs `setup` itself: announce in one line (hundreds of MB, minutes), then run; don't ask, don't hide | skill | reddit | generated |
| B8 | `status --json` writes nothing to stdout on exit 2 — read the exit code, not a JSON parse | skill | reddit | generated |
| B9 | Every read writes a JSON **file**; stdout carries nothing. Always pass `--output` to `/tmp`, then `Read` | skill | reddit | generated |
| B10 | **Four object types** — `Post`, `Comment`, `Subreddit`, `User`; `post` emits `Post` + `Comment` in one file | skill | reddit | generated |
| B10a | `Comment.replies` nests recursively — array length is top-level comments, not discussion size | skill | reddit | generated |
| B10b | `over_18` is tri-state (`true`/`false`/**`null`**); a falsy check collapses "unknown" into "safe" | skill | reddit | generated |
| B11 | **The per-invocation request cap (100) equals the whole 10-minute window** — one command can spend everything | skill | reddit | generated |
| B12 | The stderr budget field is `{remaining}/{used}`, not remaining-of-total | skill | reddit | generated |
| B13 | Decide the shape of the investigation before starting; read the budget field and adapt | skill | reddit | generated |
| B14 | exit 3 ⇒ stop and report; never wait autonomously; never fake concurrency with parallel processes | skill | reddit | generated |
| B15 | Big threads: `--comment-sort top` and go deeper on less, rather than shallow across everything | skill | reddit | generated |
| B16 | Chaining handles: which field feeds which next command; `subreddit-info` is the cheap pre-flight check | skill | reddit | generated |
| B17 | Bound the fan-out before starting it, and report the shape of what was actually done | skill | reddit | generated |
| B18 | `stop_reason` semantics — `tree_complete` vs `depth_capped`/`comment_limit`; exit 7 outranks exit 3 | skill | reddit | generated |
| B19 | ToS: no Responsible-Builder approval; personal/research only; never bulk or ML-training data | skill | reddit | generated |
| B20 | Third-party PII, sharpened by Reddit **pseudonymity** — `user --type overview` enables de-anonymisation | skill | reddit | generated |
| B21 | NSFW is reachable anonymously and unfiltered; check `over_18`, report it, never gate or refuse | skill | reddit | generated |
| B22 | **Argparse errors over 80 chars are redacted wholesale**, so the siblings' `invalid choice` rule cannot fire — read the usage line instead | skill | reddit | generated |
| B23 | exit 4 has **no local self-heal** (`doctor` has no `--refresh`); re-warm via `setup --force`, else it needs a release | skill | reddit | generated |
| B24 | A repo checkout and the installed CLI are different versions; the one on PATH counts | skill | reddit | generated |
| B25 | A **nonexistent subreddit also exits 4** from `subreddit-info`; run a known-good control before believing "drift", and `subreddit <name>` returns `no_matches` instead | skill | reddit | generated (from e2e V7b) |
| B26 | `tree_complete` routinely returns far fewer comments than `num_comments` — the gap is deleted/removed content, not truncation; don't chase it with a bigger budget | skill | reddit | generated (from e2e V2) |

## Component specs

**Skill `reddit`** — `.claude/skills/reddit/SKILL.md`, single file, no `references/`, no `scripts/`.

- **Single file, deliberately.** A retrieval task needs the budget rule, the file trap, the object-type map, the completeness semantics, and the failure playbook together on every invocation — the model never picks one of several variants, so there is no seam to split on. Splitting by length alone would add a routing decision with nothing saved, and the budget and PII stop-rules must not hide behind a conditionally-loaded file.
- **`description`** triggers on any "get something off Reddit" phrasing plus a bare reddit.com / old.reddit.com / redd.it URL, explicitly including the case where the user never says "Reddit", and names two near-misses out of scope: developing the package, and other networks.
- **`allowed-tools`**: `Bash(agentic-reddit:*)`, `Bash(uv:*)`, `Bash(pipx:*)`, `Bash(curl:*)`, `Read` — the commands the body actually calls, including the version check and the upgrade.
- **Language:** English.

**Nothing else is generated.** No hooks, no permissions block, no agents, no workflows — see D7.

## Design rationale

**D1 — one skill, not several.** Install, readiness, retrieval, chaining, budget, PII, and failure handling all trigger from the same situation ("the user wants something off Reddit") and read as one job. Splitting would spend the shared description budget several times over for no triggering benefit.

**D2 — repo-local, not `~/.claude/skills/`.** Put explicitly to the user, who chose consistency with the three siblings over reach. **The honest consequence: the skill loads only in sessions opened in this repo**, even though wanting to read Reddit from some *other* project is the more common situation. The fix, if that ever bites, is a single symlink into `~/.claude/skills/` — the pattern `harness-creator` and `repo-wiki` already use on this machine — not a redesign. This decision has now been made per-repo four times; a family-wide pass is logged as a follow-up rather than re-litigated here.

**D3 — the no-account property changes the whole session shape, not just one paragraph. (Highest-value divergence.)** All three siblings are built around a human-in-the-loop login: exit 2 means "ask the user to open a browser and sign in", and every one of them carries ban-risk language about throwaway accounts. Reddit has none of that. Exit 2 means "the browser isn't downloaded yet", and **Claude can fix it unaided**. Porting a sibling's exit-2 handling verbatim would produce a skill that stops and asks a user to log into an account that does not exist — a dead end in a tool whose entire first-run story is `install → setup → read`. The chosen posture (D4) follows from this.

**D4 — `setup` is announced, then run.** Not silent, because it downloads hundreds of megabytes and a mid-task environment change has to be diagnosable if results later look strange. Not gated on a question, because there is nothing the user can contribute to the answer and they would approve it every time. This mirrors the family's version-upgrade policy exactly, which is the closest existing precedent for "heavy, unattended, but necessary."

**D5 — budget is the organizing constraint, and the ceiling is sharper than it looks.** `DEFAULT_MAX_REQUESTS = 100` is the per-invocation cap, and Reddit's anonymous window is *also* about 100 requests per 10 minutes. **One command can therefore legitimately consume the entire window** and stop with `max_requests`, leaving nothing for the rest of a planned chain, with no advance warning. This is the fact that makes "decide the shape before starting" a rule rather than a platitude here.

Deliberately **not** included: a measured per-command request-cost table. It was offered and declined, and the reasoning holds — the cost model is structural (roughly one request per listing page, one per expanded comment branch) and states in a sentence, whereas measured numbers invite false precision about a budget Reddit reports live on stderr in every response. The skill teaches the shape and points at the live number.

**D6 — exit 3 never triggers an autonomous wait.** `--wait-on-limit` is mentioned but framed as the user's call. A reset window runs to ten minutes; a session that silently stalls that long is worse than one that reports partial results and offers to wait.

**D7 — no hooks, no permissions, no agents, no workflows.** Every command is read-only by construction, and the package clamps a non-bypassable 1.0s request floor plus a header-driven budget governor **in code**. There is nothing left to enforce deterministically that the package does not already guarantee; a hook here would be enforcement theatre.

**D8 — the `invalid choice` staleness rule is corrected, not inherited. (Highest-risk divergence.)** All three siblings teach "exit 1 saying `invalid choice` means an out-of-date install." On `agentic-reddit` that string is **never printed**: `cli.py:28` routes every argparse error through `redact.scrub_diagnostic()`, which replaces any message over `_DIAGNOSTIC_TEXT_MAX_LEN = 80` characters with `[REDACTED diagnostic text: N chars]` — and `invalid choice` is long precisely because it enumerates all eleven subcommands, so it will always exceed the threshold. Verified by running it against the installed CLI. The skill therefore teaches reading the **usage line's subcommand list**, which does survive. Porting the sibling wording would have shipped a diagnostic that provably never fires. (The over-redaction itself is arguably a package bug — a usage error is not scraped content — and is logged as a follow-up in the plan, not fixed in this pass.)

**D9 — exit 4 has no local self-heal, so its playbook is shaped differently from Threads'.** Threads leads with `doctor --refresh`, which re-anchors rotated `doc_id`s over HTTP without a release. `agentic-reddit doctor` has **no `--refresh` flag** and there are no persisted query ids to re-anchor. The realistic local move is `setup --force` to re-warm a profile that lost its challenge clearance; past that, genuine response drift ships as a release.

**D10 — tool-boundary policy is enforced by the `description`, not by body prose.** An explicit "don't use WebFetch on reddit.com" paragraph was proposed and declined. Once the skill triggers, its body already routes every read through `agentic-reddit`, so the only real exposure is the skill *failing to trigger* — a description-quality problem, validated by scenario V6 rather than argued in the body. **Known future collision:** `Ultra Fetch` claims to be the default reader for bot-protected pages and names only `scrape-x`/`scrape-fb` as exceptions, so an anonymous Reddit URL falls inside its stated scope. The two never co-load today (each lives in its own repo), so this is a follow-up, not a blocker.

**D11 — NSFW is reported, never gated.** Anonymous access reaches adult content freely (measured during package recon, correcting an earlier assumption that it would be largely absent). The skill checks and surfaces `over_18` but adds no filter, warning gate, or confirmation prompt — consistent with package decision D6 that filtering is the caller's judgment, and avoiding obstruction of a user who deliberately named an adult community. The failure mode being defended against is the model *assuming* a safe surface, not the user seeing what they asked for.

**D12 — third-party-data wording is sharpened for pseudonymity.** The siblings' PII language is inherited, plus one Reddit-specific escalation: accounts are pseudonymous, and pseudonymity is routinely broken by aggregating an account's history — exactly what `user --type overview` makes trivial. Also note this repo tracks synthetic JSON fixtures rather than blanket-ignoring `*.json`, so a capture saved into the working tree would **not** be caught by `.gitignore`; keeping captures in `/tmp` is the actual safeguard.

## Validation

Structural: **`validate_harness.py` — PASS** (0 errors, 0 warnings; 2026-07-25). No hooks were generated, so `test_hook.py` does not apply.

Description quality: **reviewed manually** against `harness-creator`'s `references/skills.md` triggering guidance, since `validate_harness.py` does not grade trigger quality or near-miss coverage. The description names the underlying intent rather than only the keyword ("what do redditors think of…", "summarize this thread"), explicitly covers the bare-URL case including when the user never says "Reddit", and names both near-misses (package development; the three sibling networks). No sibling skill co-loads in this repo, so there is no description-vs-description competition to resolve here.

**Live e2e — 7 of 7 scenarios passed** (2026-07-25), against the installed `agentic-reddit 0.1.0` on the user's real model (`claude-opus-5[1m]`), via `run_e2e.py`. Reddit is the first sibling where live e2e is cheap and safe: no account means no ban risk, and the only cost is request budget that refills in ten minutes. (The Threads pass could only run 3 of 5 for want of a logged-in session; there was no such excuse here.) All captures were written to `/tmp`, never the repo, and deleted afterward. Live scenarios were spaced across rate-limit windows so no run failed merely because a previous one had spent the budget — total spend stayed low enough that the window never actually ran out.

**Two mechanical notes for whoever runs this next.** First, `run_e2e.py --isolate` **crashed** on this repo: `shutil.copytree` aborts on the dead sockets and broken symlinks that live browser profiles leave behind in the gitignored `scratch/` directory. The workaround was a manual `rsync -a --exclude 'scratch/' --exclude '.venv/' --exclude '.git/'` copy, then `run_e2e.py` pointed at that copy without `--isolate`. Second, the headless `claude -p` mechanism that `references/e2e-testing.md` flags as never having been watched to work **did work here** — every scenario authenticated and ran to completion, so that caveat is settled for this project.

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| V1 | "What are the top posts in r/python this week?" | Trigger; readiness check; `--output` to `/tmp`; read the file; cite real posts | **PASS** — `skill_invocations: ["reddit"]`; ran `--version` + PyPI simple index, `status`, `catalog`, then `subreddit python --sort top --time week --limit 25 --output /tmp/…`; answer cited five real posts with scores, comment counts and links |
| V2 | "Summarize the discussion on this thread: `<r/Python permalink, 147 comments>`" | `post` with sized flags; distinguishes complete from truncated **in the user-visible answer** | **PASS** — used `--comment-sort top` unprompted (B15); closed with "the CLI reported `tree_complete`… but that yielded 44 comments against Reddit's own counter of 147. The gap is deleted/removed content." Also reported budget spend and that captures were deleted |
| V3 | "What do redditors think about uv replacing pip?" | `search` → pick threads → `post` each → synthesize; state the shape | **PASS** — first search returned junk, so it re-scoped with `--subreddit Python`; read 4 threads at `--comment-sort top --depth 2`; reported "70 of 220 comments, 65 of 165, 41 of 83, 16 of 46… all four stopped at `depth_capped`… This is a representative sample, not the full picture", and flagged that two large threads failed to load, biasing the sample |
| V4 | "Add a `--csv` output option to agentic-reddit's subreddit command." | Must NOT trigger — ordinary repo work | **PASS** — `skill_invocations: []`; read `CLAUDE.md`, `cli.py`, `model.py`, then stopped to flag that a third output format conflicts with CLAUDE.md's JSON/NDJSON contract before writing code. Real repo untouched |
| V5 | "What has @zuck been posting on Threads lately?" | Must NOT trigger — sibling network | **PASS** — `skill_invocations: []`, one turn, no `agentic-reddit` calls; reply named the boundary explicitly ("the `reddit` skill… is explicitly scoped to Reddit only, and its description rules out Facebook, X/Twitter, and Threads") |
| V6 | A bare reddit.com permalink + "what's this about?" | Must trigger on the URL alone, no "Reddit" keyword in the sentence | **PASS** — `skill_invocations: ["reddit"]`. This was the S6/D10 bet, and it held: triggering alone kept the model off WebFetch without any body prose about it. Also reported `tree_complete` with a 43-of-46 gap, and declined to repeat an unverifiable claim from the thread |
| V7b | "Read r/`<valid-format nonexistent subreddit>`" | Nonexistent target reported, not retried, no wasted budget | **PASS** — hit exit 2, **ran `setup` itself and said so** (live confirmation of D4/B7); then cross-checked three ways and ran `subreddit-info python` as a control to separate transport failure from target failure; reported 5 requests spent |

**V7 was rewritten mid-run, and the first version is worth recording.** The original prompt used a 30-character subreddit name, which `identity.py`'s `[A-Za-z0-9_]{3,21}` rejects locally — so the run exited 1 on client-side validation and never reached Reddit, testing nothing about exit 5. The session itself diagnosed this correctly (it read `identity.py` and measured the name length), which is a good sign about the harness, but the scenario was invalid, so it was re-run as V7b with a conforming name. A scenario that passes for the wrong reason is a scenario that didn't run.

**Two SKILL.md corrections came out of e2e, not out of planning** — the concrete argument for having run it:

- **B25, from V7b.** The draft claimed a "misspelled subreddit" produces exit 5. It does not: Reddit answers `/r/<nonexistent>/about.json` with a non-`t5` body rather than a 404, so `subreddit-info` falls through to **exit 4**, whose documented remedy is `doctor` / `setup --force` — pure wasted work on a typo. Verified directly afterward, and traced to `session.py:231-233`, where exit 5 requires an actual 404/403 or an explicit unavailable body shape. The skill now teaches running a known-good control to separate "transport broken" from "target missing", and notes that the listing path returns `no_matches` for the same case.
- **B26, from V2.** `tree_complete` with 44 of 147 comments looks like silent truncation and isn't — Reddit's counter includes deleted and removed comments. Without this, a model would plausibly re-run with a bigger budget chasing comments that no longer exist.

Not run by design, and recorded as such rather than omitted: **exit 3** (budget spent) would cost a full ten-minute window to demonstrate a rule the skill states plainly. **Exit 4** was originally listed as unprovokable — that turned out to be wrong twice over: V7b provoked it with a nonexistent subreddit, and V3 hit it organically on two large threads. Both are now covered by real evidence rather than by inspection.

## Change history

- **2026-07-25 — new.** First harness pass, implementing the plan merged as PR #13. Created `.claude/` from scratch for a repo that already carried a project-specific CLAUDE.md but no `.claude/` directory, then generated the `reddit` retrieval skill and this spec.

  **Reconciliation against the installed CLI.** The plan was written against `agentic-reddit 0.1.0` and the global install resolved to the same version (`/Users/seongjin/.local/bin/agentic-reddit`, matching the PyPI simple index), so every factual claim was re-checked and **all reproduced** — no corrections were needed. Specifically re-verified: the argparse-redaction behaviour (D8) reproduced exactly, including that the usage line's subcommand list survives while the `invalid choice` text does not; `doctor` still has no `--refresh` (D9); `post` still carries `--comment-sort`; `status --json` still writes zero bytes to stdout on exit 2; the catalog still reports four object types and the 0/1/2/3/4/5/7 exit contract.

  **Notable:** three of the family's inherited claims had already been corrected during planning rather than here (see `docs/plan/07-skill-plan.md` §2.2), which is why the *catalog-level* facts needed no rework — that verification happened before the drafts were written. D4 was exercised for real twice: once by this session (`agentic-reddit setup` ran unattended to completion, browser and Playwright dependencies installed) and once inside e2e scenario V7b, where a headless session hit exit 2, provisioned the browser itself, and announced it — the no-human-step assumption holds end to end.

  **What the drafts got wrong, and only e2e caught.** Two corrections were made to the SKILL.md *after* the drafts were placed, both driven by live runs rather than by reading: the exit-4/exit-5 boundary (B25) and the `tree_complete`-vs-`num_comments` gap (B26). Details in Validation. The shipped `.claude/skills/reddit/SKILL.md` therefore diverges from `docs/plan/07a-SKILL-md-draft.md` in three places — those two sections plus the stderr budget example, which the draft wrote as integers (`budget 87/13`) where the CLI actually emits floats (`budget 99.0/1.0`). The draft is left as the historical planning artifact; **the shipped file is the truth.** The lesson worth carrying to the remaining siblings: planning verified everything a `catalog` or a source read can show, and still missed two facts that only appeared when a real session tried to act on them.
