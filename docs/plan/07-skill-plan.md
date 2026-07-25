# Skill Plan — `.claude/skills/reddit/` (later session)

Built **after** `agentic-reddit` is on PyPI, in a **fresh session**, using the `harness-creator` skill. It wraps the *installed* CLI, not a repo checkout. Mirror `Agentic X`'s `.claude/skills/x/SKILL.md` as the structural template — but three things differ materially here and the skill must reflect them:

1. **There is no login.** No account, no credentials, no "ask the user to log in." The only human step is a one-time `agentic-reddit setup` (downloads a browser).
2. **The request budget is the scarce resource** (~100 requests / ~10 minutes), not wall-clock time. This changes how Claude must plan a chain.
3. **There is no id-rotation fragility** (no `doc_id`/query-id/transaction-id), so no `doctor --refresh` and less version-staleness urgency than the Meta siblings.

## Shape

- **Single file**: `.claude/skills/reddit/SKILL.md`. No `references/`, no `scripts/` — a retrieval task needs all the rules together (the budget and PII stop-rules must not hide behind a conditionally-loaded file). Plus a `.claude/harness-spec.md` design record.
- **Frontmatter**:
  ```yaml
  name: Reddit retrieval
  description: Read Reddit via the agentic-reddit CLI — a subreddit's listing, a post and its
    comment tree, a redditor's posts/comments, search (posts/subreddits/people), find
    subreddits, or subreddit metadata — and chain those to answer multi-hop questions. Use
    whenever the user wants something off Reddit, however they phrase it ("what's r/X saying
    about Y", "top posts in r/Z this week", "find subreddits about W", "what has u/V posted",
    "what do redditors think of …"), or hands over a reddit.com URL. NOT for developing the
    agentic-reddit package itself, and not for any other social network.
  allowed-tools: Bash(agentic-reddit:*), Bash(uv:*), Bash(pipx:*), Bash(curl:*), Read
  ```
  Engineer the `description` to trigger on intent and to name near-misses out of scope (developing the package = ordinary repo work; Facebook/X/Threads have their own tools).

## Body (workflow, not a flag reference)

1. **Get the tool.** Check `agentic-reddit --version` against the PyPI **simple index** (`curl -s https://pypi.org/simple/agentic-reddit/`), not the JSON API (it lags). Install/upgrade via `uv tool`/`pipx`, never a shared `pip` (scrapling pins Playwright). Unlike the Meta siblings, Reddit's schema is stable — staleness is a lower-grade risk here, but keep the habit.

2. **`agentic-reddit catalog`** — learn every command/flag/exit-code/output-type in one call. Work from what it says; never restate the flag list in the skill (it would drift).

3. **`agentic-reddit status`** — exit 0 ready. Exit 2 means the browser isn't provisioned: run `agentic-reddit setup` (a one-time download; **Claude can run it** — there is no login and no human step beyond waiting). Say plainly that no Reddit account or API key is involved.

4. **Budget before breadth — the rule that matters most here.** The ceiling is ~100 requests per ~10 minutes, shared across everything. Each listing page, each comment-subtree expansion, and each chained hop spends from it. **Decide the shape of the investigation before starting it**: e.g. "top 3 subreddits × 25 posts each, then the single most-discussed thread" — not "read everything." The stderr summary reports the remaining budget; read it and adapt. Exit 3 means the window is spent — stop and either wait or report what was gathered. Never launch parallel `agentic-reddit` processes to fake concurrency; they share the same budget and will simply 429 each other.

5. **The file trap** — every read command writes a JSON *file* and prints only a stderr summary. Always pass `--output`, then `Read` the file.

6. **Four object types** — `subreddit`/`search --type link` emit `Post`; `post` emits a `Post` plus a threaded `Comment` tree; `user` emits `Post` and/or `Comment` per `--type`; `search --type sr`/`subreddits`/`subreddit-info` emit `Subreddit`; `search --type user` emits `User`. `captured_at` is scrape-time, not an event time. Run `agentic-reddit schema` for the field list.

7. **What each primitive is for + chaining** — the judgment the catalog can't carry:
   - `subreddit` = one community's listing (`--sort`/`--time`); `all`/`popular` is the front page.
   - `post` = a post *and its discussion* — the highest-value primitive, and the most expensive.
   - `user` = a redditor's history (`--type overview` mixes posts and comments).
   - `search` = discovery across posts, subreddits, or people.
   - `subreddits` = find communities by topic; `subreddit-info` = size/type/description before committing budget to one.

   Worked chains: *"What does Reddit think of X?"* → `search "X" --type link --sort top --time year` → pick the 2–3 most-commented → `post` each → synthesize. *"Which communities discuss X?"* → `subreddits "X"` → `subreddit-info` each to rank by subscribers → `subreddit` the best one. *"Who is this commenter?"* → from a `Comment`'s `author` → `user <author> --type overview`.

   **Bound the fan-out before starting; report the shape of what you did.** A chain that silently sampled 3 of 40 threads is a wrong answer wearing a confident summary.

8. **`stop_reason` semantics** — `limit_reached`/`listing_exhausted`/`no_matches`/`since_crossed`/`rate_limited`/`max_requests`, plus the comment-tree ones: `tree_complete` (you saw the whole discussion) vs **`depth_capped`/`comment_limit` (you did NOT — say so)**. Large threads (thousands of comments) are physically unexpandable within the budget; report the sample honestly. Also the exit-7 `--since` caveat.

9. **ToS and risk — state it, don't bury it.** Reddit's *Responsible Builder Policy* requires explicit approval for programmatic access and this tool does not have it (the OAuth path is approval-gated and per-user). Personal/research use only; **never** use the output to build bulk or ML-training datasets, and never for commercial scraping. Exit 3 = stop, don't retry-loop.

10. **Third-party data + NSFW.** Output is other people's public-but-personal data; `user --type overview` in particular makes aggregation-based de-anonymisation easy. Write to temp, never `git add`, delete when done, and quote named individuals only when the question needs it. **NSFW is reachable anonymously** and will appear unfiltered — check `over_18` on `Post`/`Subreddit` rather than assuming a safe surface. `--raw`/`--no-redact` are debug-only.

11. **Failure playbook** — exit 2 → `agentic-reddit setup`; exit 3 → budget spent, wait or report; exit 4 → an anti-bot challenge or envelope drift (`agentic-reddit doctor`, re-run `setup`, or upgrade); exit 5 → private/banned/quarantined/suspended/deleted, not retryable; "invalid choice" → out-of-date install (step 1).

## harness-spec.md

Record: one skill (not per-command), single-file rationale, a behavior inventory, the `allowed-tools` reasoning, the **budget-first planning policy** (the main way this skill differs from its siblings), the **no-login / no-credentials** property, the absence of id-rotation (hence no `doctor --refresh`), the ToS posture, and a live e2e validation log (scenarios pass, including correctly NOT triggering on repo-work or on Facebook/X/Threads requests).
