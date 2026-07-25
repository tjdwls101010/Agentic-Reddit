# Draft — `.claude/harness-spec.md`

Ready-to-place draft written 2026-07-25. The next session copies everything below the marker into `.claude/harness-spec.md`, then **fills in the two sections that can only be completed by doing the work**: the Validation table's Result column, and the Change history entry. Leaving those as drafted would be a false record — `harness-creator` audits future passes against this file, so a spec claiming validation that never ran is worse than no spec.

---

<!-- ==================== BEGIN harness-spec.md ==================== -->

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
| B1 | Install into an isolated env (`uv tool`/`pipx`), never shared `pip` — scrapling pins Playwright | skill | reddit | planned |
| B2 | Check installed version against the PyPI **simple index** at task start; if behind, announce + upgrade | skill | reddit | planned |
| B3 | **No `[browser]` extra** — scrapling is a required dependency here, not optional as in X/Threads | skill | reddit | planned |
| B4 | Staleness risk is genuinely lower than the siblings' (no id rotation); say so rather than over-applying their urgency | skill | reddit | planned |
| B5 | `catalog` / `schema` are the flag and output contracts; never restate them in prose | skill | reddit | planned |
| B6 | **No account, no login, no credentials, ever** — exit 2 is provisioning, not authentication | skill | reddit | planned |
| B7 | Claude runs `setup` itself: announce in one line (hundreds of MB, minutes), then run; don't ask, don't hide | skill | reddit | planned |
| B8 | `status --json` writes nothing to stdout on exit 2 — read the exit code, not a JSON parse | skill | reddit | planned |
| B9 | Every read writes a JSON **file**; stdout carries nothing. Always pass `--output` to `/tmp`, then `Read` | skill | reddit | planned |
| B10 | **Four object types** — `Post`, `Comment`, `Subreddit`, `User`; `post` emits `Post` + `Comment` in one file | skill | reddit | planned |
| B10a | `Comment.replies` nests recursively — array length is top-level comments, not discussion size | skill | reddit | planned |
| B10b | `over_18` is tri-state (`true`/`false`/**`null`**); a falsy check collapses "unknown" into "safe" | skill | reddit | planned |
| B11 | **The per-invocation request cap (100) equals the whole 10-minute window** — one command can spend everything | skill | reddit | planned |
| B12 | The stderr budget field is `{remaining}/{used}`, not remaining-of-total | skill | reddit | planned |
| B13 | Decide the shape of the investigation before starting; read the budget field and adapt | skill | reddit | planned |
| B14 | exit 3 ⇒ stop and report; never wait autonomously; never fake concurrency with parallel processes | skill | reddit | planned |
| B15 | Big threads: `--comment-sort top` and go deeper on less, rather than shallow across everything | skill | reddit | planned |
| B16 | Chaining handles: which field feeds which next command; `subreddit-info` is the cheap pre-flight check | skill | reddit | planned |
| B17 | Bound the fan-out before starting it, and report the shape of what was actually done | skill | reddit | planned |
| B18 | `stop_reason` semantics — `tree_complete` vs `depth_capped`/`comment_limit`; exit 7 outranks exit 3 | skill | reddit | planned |
| B19 | ToS: no Responsible-Builder approval; personal/research only; never bulk or ML-training data | skill | reddit | planned |
| B20 | Third-party PII, sharpened by Reddit **pseudonymity** — `user --type overview` enables de-anonymisation | skill | reddit | planned |
| B21 | NSFW is reachable anonymously and unfiltered; check `over_18`, report it, never gate or refuse | skill | reddit | planned |
| B22 | **Argparse errors over 80 chars are redacted wholesale**, so the siblings' `invalid choice` rule cannot fire — read the usage line instead | skill | reddit | planned |
| B23 | exit 4 has **no local self-heal** (`doctor` has no `--refresh`); re-warm via `setup --force`, else it needs a release | skill | reddit | planned |
| B24 | A repo checkout and the installed CLI are different versions; the one on PATH counts | skill | reddit | planned |

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

**D8 — the `invalid choice` staleness rule is corrected, not inherited. (Highest-risk divergence.)** All three siblings teach "exit 1 saying `invalid choice` means an out-of-date install." On `agentic-reddit` that string is **never printed**: `cli.py:28` routes every argparse error through `redact.scrub_diagnostic()`, which replaces any message over `_DIAGNOSTIC_TEXT_MAX_LEN = 80` characters with `[REDACTED diagnostic text: N chars]` — and `invalid choice` is long precisely because it enumerates all eleven subcommands, so it will always exceed the threshold. Verified by running it. The skill therefore teaches reading the **usage line's subcommand list**, which does survive. Porting the sibling wording would have shipped a diagnostic that provably never fires. (The over-redaction itself is arguably a package bug — a usage error is not scraped content — and is logged as a follow-up in the plan, not fixed in this pass.)

**D9 — exit 4 has no local self-heal, so its playbook is shaped differently from Threads'.** Threads leads with `doctor --refresh`, which re-anchors rotated `doc_id`s over HTTP without a release. `agentic-reddit doctor` has **no `--refresh` flag** and there are no persisted query ids to re-anchor. The realistic local move is `setup --force` to re-warm a profile that lost its challenge clearance; past that, genuine response drift ships as a release.

**D10 — tool-boundary policy is enforced by the `description`, not by body prose.** An explicit "don't use WebFetch on reddit.com" paragraph was proposed and declined. Once the skill triggers, its body already routes every read through `agentic-reddit`, so the only real exposure is the skill *failing to trigger* — a description-quality problem, validated by scenario V6 rather than argued in the body. **Known future collision:** `Ultra Fetch` claims to be the default reader for bot-protected pages and names only `scrape-x`/`scrape-fb` as exceptions, so an anonymous Reddit URL falls inside its stated scope. The two never co-load today (each lives in its own repo), so this is a follow-up, not a blocker.

**D11 — NSFW is reported, never gated.** Anonymous access reaches adult content freely (measured during package recon, correcting an earlier assumption that it would be largely absent). The skill checks and surfaces `over_18` but adds no filter, warning gate, or confirmation prompt — consistent with package decision D6 that filtering is the caller's judgment, and avoiding obstruction of a user who deliberately named an adult community. The failure mode being defended against is the model *assuming* a safe surface, not the user seeing what they asked for.

**D12 — third-party-data wording is sharpened for pseudonymity.** The siblings' PII language is inherited, plus one Reddit-specific escalation: accounts are pseudonymous, and pseudonymity is routinely broken by aggregating an account's history — exactly what `user --type overview` makes trivial. Also note this repo tracks synthetic JSON fixtures rather than blanket-ignoring `*.json`, so a capture saved into the working tree would **not** be caught by `.gitignore`; keeping captures in `/tmp` is the actual safeguard.

## Validation

Structural: **`validate_harness.py` — [TO BE FILLED: PASS/FAIL, error and warning counts, date].** No hooks are generated, so `test_hook.py` does not apply.

Description quality: **[TO BE FILLED]** — `validate_harness.py` does not grade trigger quality or near-miss coverage, so the description was re-read against `harness-creator`'s `references/skills.md` guidance as a separate manual pass.

**Live e2e — [TO BE FILLED: N of 7 run].** Reddit is the first sibling where live e2e is cheap and safe: no account means no ban risk, and the only cost is request budget that refills in ten minutes. Unlike the Threads pass — which could only run 3 of 5 scenarios for want of a logged-in session — all seven scenarios here are runnable, and anything skipped needs a stated reason. Captures belong in `/tmp` and should be deleted afterward; non-trigger scenarios run in isolated project copies via `run_e2e.py --isolate`. Space the live scenarios so one does not fail merely because a previous scenario spent the ten-minute window.

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| V1 | "What are the top posts in r/python this week?" | Trigger; readiness check; `--output` to `/tmp`; read the file; cite real posts; clean up | **[TO BE FILLED]** |
| V2 | "Summarize the discussion on this thread: `<real permalink>`" | `post` with sized `--depth`/`--comment-limit`; distinguishes `tree_complete` from `depth_capped`/`comment_limit` **in the user-visible answer** | **[TO BE FILLED]** |
| V3 | "What do redditors think about `<topic>`?" | `search --type link` → pick 2–3 by `num_comments` → `post` each → synthesize; states the shape ("read 3 of 27 threads") | **[TO BE FILLED]** |
| V4 | "Add a `--csv` output option to agentic-reddit's subreddit command." | Must NOT trigger — ordinary repo work | **[TO BE FILLED]** |
| V5 | "What has `<person>` been posting on Threads lately?" | Must NOT trigger — sibling network | **[TO BE FILLED]** |
| V6 | A bare reddit.com permalink + "what's this about?" | Must trigger on the URL alone, with no "Reddit" keyword in the sentence | **[TO BE FILLED]** |
| V7 | "Read r/`<nonexistent subreddit>`" | Exit 5; reported as unavailable, not retried, no wasted budget | **[TO BE FILLED]** |

Not run by design, and recorded as such rather than omitted: **exit 3** (budget spent) would cost a full ten-minute window to demonstrate a rule the skill states plainly, and **exit 4** (response drift) cannot be provoked without Reddit changing its response shape. Both are covered by inspection of the SKILL.md failure section.

## Change history

- **[TO BE FILLED — date] — new.** First harness pass. **[Record: what was created; which of the plan's factual claims reproduced against the installed version and which were corrected; any decision revisited during implementation and why; the e2e outcome including anything that failed or was skipped.]**

<!-- ==================== END harness-spec.md ==================== -->
