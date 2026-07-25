---
name: Reddit retrieval
description: Read Reddit via the agentic-reddit CLI — a subreddit's listing, a post and its comment tree, one comment's subthread from its permalink, a redditor's posts, comments and profile, search (posts, subreddits, or people), subreddit discovery, subreddit metadata, and the other communities discussing the same link — and chain those results to answer multi-hop questions. Use whenever the user wants something off Reddit, however they phrase it: "what is r/<sub> saying about <topic>", "top posts in r/<sub> this week", "find subreddits about <topic>", "what has u/<name> posted", "who is this redditor", "what do redditors think of <thing>", "summarize this thread", "what is this comment replying to", "where else is this being discussed". Also use when the user hands over a reddit.com, old.reddit.com, or redd.it URL — a subreddit, a post, or a comment permalink — and wants its contents, including when they never say the word "Reddit" at all. NOT for developing or testing the agentic-reddit package itself (that is ordinary repo work), and not for Facebook, X/Twitter, Threads, or any other social network.
allowed-tools: Bash(agentic-reddit:*), Bash(uv:*), Bash(pipx:*), Bash(curl:*), Read
---

# Reddit retrieval

`agentic-reddit` reads Reddit anonymously and hands you structured JSON. **You supply the navigation.** The CLI is deliberately a set of single-target primitives with no `crawl` command — deciding which thread to open next is your job, and it is the whole reason this skill exists.

Two things make this tool unlike its `agentic-facebook` / `agentic-x` / `agentic-threads` siblings, and both change how you work:

- **There is no account.** No login, no credentials, no API key, nothing for the user to authorize. Every read is anonymous.
- **The scarce resource is requests, not time.** Roughly 100 requests per 10 minutes, shared by everything you do. That ceiling shapes the plan before it shapes the results.

## Step 1 — get the tool, and get the current one

```bash
agentic-reddit --version                                  # -> "agentic-reddit 0.3.0"
curl -s https://pypi.org/simple/agentic-reddit/ | grep -oE 'agentic[_-]reddit-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/.*-//' | sort -V | tail -1
```

If the installed version is behind, say so in one line and upgrade before doing the user's actual work — don't ask, and don't do it silently, because a mid-task version change has to be diagnosable if results later look strange:

> agentic-reddit 0.3.0 is installed, 0.3.1 is on PyPI — upgrading first.

```bash
uv tool install --upgrade --no-cache agentic-reddit     # or: pipx upgrade agentic-reddit
```

**If it isn't installed at all** (`command not found`):

```bash
uv tool install agentic-reddit          # or: pipx install agentic-reddit
```

No extras. Unlike the X and Threads siblings — where the browser is an optional `[browser]` extra because their reads are pure HTTP — a browser is `agentic-reddit`'s *only* transport, so `scrapling[fetchers]` is a required dependency and comes with the base install. If you catch yourself typing `agentic-reddit[browser]`, that's a sibling's habit, not this package.

Use `uv tool` or `pipx`, **not** `pip install` into a shared virtualenv: `scrapling[fetchers]` pins exact Playwright/patchright versions, and dropping that into a shared environment can fail to resolve or silently break another Playwright-based tool living there.

Check once, at the start. The installed version can't change under you unless you change it, so re-checking between commands buys nothing.

Read the PyPI version from the **simple index** as above, not from `pypi.org/pypi/agentic-reddit/json`: for minutes after a release the JSON endpoint can still report the previous version while the simple index is already correct. The same lag can leave an upgrade one release short — verify with `agentic-reddit --version` afterwards rather than assuming it landed, and re-run if the index was mid-propagation.

**How much this matters here, honestly:** less than it does for the siblings. X rotates GraphQL query-ids every few weeks and Threads rotates `doc_id`s on every client build, so those packages rot on a schedule. Reddit's `.json` endpoints are stable, and this package has no reverse-engineered id to go stale. The check is still worth its ~40ms — response-shape drift (exit 4) is real and its fix ships as a release — but if you're weighing a version check against getting the user's answer, this is not the family member where staleness is the likely culprit.

A repo checkout and the installed CLI are **different things**: `PYTHONPATH=src python -m agentic_reddit.cli` can be a completely different version from whatever `agentic-reddit` on PATH resolves to. The one on PATH is the one that counts.

## Step 2 — ask the CLI what it can do

```bash
agentic-reddit catalog          # always JSON; --json only makes it compact instead of indented
```

One call gives you every command, its real flags with types and defaults, the exit-code contract, and which object type each command emits. **Work from what it says.**

This file deliberately does not restate that list. The catalog is generated from the CLI's own argument parser, so it is correct for the version actually installed; a table copied into this file would silently describe the wrong version the moment the package updates, and you'd trust the copy over the truth. Anything you need in order to *call* a command comes from the catalog. What follows is only what the catalog cannot carry: how to decide what to call, and how to read what comes back.

## Step 3 — check readiness, and provision if needed

```bash
agentic-reddit status           # exit 0 = ready; exit 2 = browser/profile not provisioned
```

**Exit 2 is not a login problem — there is no login.** It means the isolated browser hasn't been downloaded, or its profile hasn't been warmed against reddit.com yet. **You can fix this yourself; no human is needed.** Say so in one line, then run it:

> The Reddit browser isn't provisioned yet — running `agentic-reddit setup` first. It downloads an isolated browser (a few hundred MB), so give it a few minutes.

```bash
agentic-reddit setup            # --headed if a visible window is needed; --force to re-provision
```

Announce it rather than running it silently: a multi-hundred-megabyte download nobody mentioned is a bad surprise, and if something later goes wrong the user needs to know the environment changed mid-task. But don't stop to ask permission — there is nothing the user can contribute to the answer, and they'd say yes every time.

When a user asks whether this needs their Reddit account, the answer is flatly no: **no account, no password, no API key, no OAuth.** The package will not accept credentials even if offered.

One reading trap: `status --json` writes **nothing to stdout when it isn't ready** — the message goes to stderr and the exit code carries the verdict. Piping it into a JSON parser on exit 2 gets you an empty-input error that looks like a bug and is just "not set up yet." Read the exit code first.

## The one thing that will trip you up

**Every read command writes its results to a *file* — JSON, or NDJSON with `--format ndjson` — and prints only a one-line summary to stderr. Nothing useful goes to stdout.**

```bash
agentic-reddit subreddit python --sort top --time week --limit 25 --output /tmp/reddit-python.json
# stderr: "25 posts, range 2026-07-18T09:14:02+00:00..2026-07-25T21:40:55+00:00,
#          stop reason: limit_reached, budget 97.0/3.0. Saved to /tmp/reddit-python.json"
```

The timestamps are full ISO-8601 with offsets, not dates, and they read `none..none` when nothing in the result carries a `created_at`.

Then `Read /tmp/reddit-python.json`. Always pass `--output` with a path you choose, and keep it in `/tmp`, not the repo (see Third-party data). Without `--output` the file lands under the platform data directory with a timestamped name you'd then have to hunt for.

## Budget before breadth — the rule that matters most here

Anonymous Reddit gives you about **100 requests per 10 minutes**, and everything spends from it: every listing page, every comment-subtree expansion, every hop in a chain. Reddit reports the real numbers in its own rate-limit headers, and the package paces itself against them.

**The trap is that one command can spend everything.** A single invocation's own request cap is *also* 100 — the same number as the whole window. So one `agentic-reddit post` on a big thread can legitimately run itself out and stop with `stop_reason: max_requests`, having done nothing wrong, after spending most of what the four hops you were planning would have needed. Nothing warns you in advance.

Note what `max_requests` actually proves, though: the *invocation's* cap was reached. It is not a statement about Reddit's window — that could still have room, or be nearly gone. The budget field is what tells you which.

So **decide the shape of the investigation before you start it.** Not "read everything about X" but "the three most relevant threads, top-sorted, two levels deep" — a shape you can price roughly (a listing page is about one request; a comment tree costs one per expanded `more` pointer, which is where the budget actually goes) and then check against reality as you go.

The check is free: **every stderr summary carries `budget {remaining}/{used}`** just before the saved path. `budget 87.0/13.0` means 87 requests left in this window and 13 spent — *not* 87 of 13, and not 87 of some total you're tracking yourself. It reads `budget unknown/unknown` when the response carried no rate headers, which means you are flying blind rather than that you have room. Read it after each command and adapt the rest of the plan to what's actually left.

Two things that look like ways around the ceiling and aren't. **Don't launch parallel `agentic-reddit` processes** — each one still paces itself, but they don't know about each other, so their governors happily spend the same Reddit-side window several times faster than any single one would, and then all of them 429. And **don't retry into a rate limit**; exit 3 means the window is spent, not that the command was wrong.

**On exit 3, stop and report.** Say what you gathered, what's left undone, and roughly how long the window takes to reset. `--wait-on-limit` (with `--max-wait`) exists for when waiting is genuinely right, but a reset can be most of ten minutes, and a session that silently stalls that long is worse than one that hands back partial results and lets the user choose. Waiting is the user's call, not yours.

## Four object types, not one

`Post`, `Comment`, `Subreddit`, `User`. The catalog names which one each command emits, in an `output` field per command — read it there rather than guessing from the command's name.

**The trap is that a file is not one type.** `post` and `comment` both write the root `Post` first and then the discussion, so `items[0]` and `items[1]` are different shapes; `user` mixes `Post` and `Comment` depending on `--type`. Check what you're holding before you index into it: a `Subreddit` has no `text`, a `Comment` has no `title`, and a `Post`'s author is a plain `author` **string**, not a nested object the way the sibling packages' authors are.

The comment tree is **nested, not flat**: each `Comment` carries its own `replies` array of further `Comment`s. So the file `post` writes is `[Post, top-level Comment, top-level Comment, …]`, and counting that array's length gives you the number of top-level comments, not the size of the discussion. Walk `replies` recursively when you need the real total.

Run `agentic-reddit schema` for the full field list. Prefer that over assuming — it's generated from the code, so it can't drift the way a copy here would.

Two fields mislead if you skim. **`captured_at` is when *you* scraped it**, not when anything happened on Reddit — sorting or deduping by it produces an ordering that looks plausible and means nothing (`id` dedups, `created_at` orders). And several fields are **nullable in a way that matters**: `over_18` is `true`/`false`/**`null`**, where `null` means Reddit never marked the record either way — not that it's safe. A plain falsy check silently collapses "unknown" into "fine". `created_at` and `num_comments` are nullable too, so filter before you compare or sort.

## What each primitive is *for*

The catalog gives you the flags; this is the judgment about which to reach for, and what each one costs.

**One request each — use them to decide where to spend the rest:**

- **`subreddit-info <name>`** — a community's metadata: subscribers, type, description, `over_18`, quarantine state. Ask it *before* committing budget to a community, and use it as the existence check (see exit 5).
- **`user-info <name>`** — a redditor's profile: karma split, account age, moderator/employee/verified flags. The existence check for a person, and the cheap way to size someone up before pulling their history.
- **`related <url|id>`** — Reddit's own "other discussions": the same link submitted to other communities. The cheapest source of cross-community perspective there is.

**Listings, roughly a page per request:**

- **`subreddit <name>`** — one community's listing. `subreddit all` and `subreddit popular` are Reddit's public front pages, which is what this package has instead of a `feed` command (no account means no personalized feed to read). It also takes a **combined name** — `subreddit python+django+learnpython` reads several communities in one listing, at one request per page rather than one per community.
- **`search <query>`** — discovery, across posts, subreddits, or people.
- **`subreddits <query>`** — find communities by topic.
- **`user <name>`** — a redditor's public activity. `--type overview` mixes their posts and comments, which is usually what "what is this person about" wants.

**Comment trees — the expensive end, and the way around it:**

- **`post <url|id>`** — one post *and its discussion*. The highest-value primitive and by far the most expensive; see below.
- **`comment <permalink>`** — one comment and the replies under it. This is the *cheap* way into a specific exchange inside a huge thread: it fetches that branch instead of the tree. Reach for it whenever the link you were handed points at a comment.

  A comment permalink given to `post` is **rejected**, not quietly widened into the whole thread — "what does this comment say" and "what does this thread say" are different questions with very different prices, so the CLI makes you pick. And a reply read alone is often unintelligible: `--context` walks up the ancestors so you can see what it was answering.

### Reading a big thread without spending the window

`post` expands the comment tree adaptively, one request per `more` pointer it opens. A thread with thousands of comments **cannot** be fully expanded inside a ten-minute budget, and trying is how you end up with a truncated tree and no budget left to do anything else. Going **deeper on less** — a couple of levels rather than every branch — costs a fraction of a complete enumeration. Reach for full expansion only when the question genuinely needs every branch, and say what it will cost before you start.

**But the comment sort you pick selects your evidence, not just your spend, and that is the easier mistake to make.** `top` gives you the positions that were seen and rewarded — which answers "what reads as the consensus in this room", not "what do people here think". Ranking is shaped by when a comment landed, who was around to see it, and what this particular room upvotes; the long tail it hides is not noise by default. `new` shows where an evolving thread currently stands. `controversial` goes straight to the disagreement, which is often the real answer when the question is contested. The default `confidence` is Reddit's blended ranking and a fair neutral choice; `top` is the more predictable *spend*, which is a different virtue from being the more representative sample.

So name the sort when you report. "The top-ranked comments say X" is a claim the data supports. "Reddit thinks X", from the same file, is not.

## Chaining — the actual work

Every object carries the handles for the next hop, and knowing which field feeds which command is most of the skill:

- a post's **`id`** or **`url`** → `post`, `related`
- a comment's **`permalink`** → `comment`
- a post's or comment's **`author`** → `user`, `user-info`
- a post's **`subreddit`**, or a `Subreddit`'s **`name`** → `subreddit`, `subreddit-info`

**Choosing what to open next is the part worth thinking about**, and the failures are consistent enough to name:

- **`num_comments` measures engagement, not relevance.** The biggest thread is often the least informative — a pile-on, a joke thread, or a duplicate of a better one. Read the titles and pick for fit to the question, not for size.
- **One subreddit is one community, not Reddit.** Its norms, moderation and demographics shape both what gets said and what survives being said. Two communities disagreeing usually tells you more than twice as many threads in one of them — and that is cheap here: `related` finds the same link's other discussions, and a combined `subreddit a+b+c` listing costs one request per page rather than one per community.
- **Recency matters exactly as much as the subject moves.** A question about a tool's current state is badly served by the year's top thread; a long-running controversy is badly served by today's.
- **Pinned, moderator and megathread posts behave differently** from organic discussion — good for rules and announcements, misleading as opinion.

The `--limit` values you choose are part of the plan, not a default to copy from an example. Size every one from the question: "is this community active" needs a handful of posts; "what has this argument looked like this month" needs a date window and more. A number carried over from an example is a number nobody chose.

Two rules keep a chain from turning into a crawl. **Bound the fan-out before you start it** — decide the shape, not "everyone", because each hop spends from a budget the next hop also needs. And **report the shape of what you did**: which threads you opened, how many you skipped, and why. A chain that silently sampled 3 of 40 threads but presents itself as "what Reddit thinks" is a wrong answer wearing a confident summary.

## `stop_reason` — how complete is this result?

The stderr summary carries a `stop_reason`, and it is the difference between "here is the answer" and "here is part of the answer." Never report a result without having read it.

**Genuinely finished:**

- **`listing_exhausted`** — Reddit had nothing more to give.
- **`no_matches`** — a real, reportable empty result.
- **`since_crossed`** — the run reached the `--since` boundary you asked for.
- **`tree_complete`** — no `more` pointer was left unexpanded in what Reddit served. This is the only stop reason that licenses "the thread says…" without a truncation caveat. It is a claim about the retrieval, not about the discussion's history: it does not promise every comment ever written is in the file.

  Which shows up as a caveat that looks alarming and isn't: `tree_complete` routinely returns **far fewer comments than the post's `num_comments`** — 44 against a counter of 147 is an ordinary result. The usual reason is that the counter includes deleted and removed comments, which are no longer served. So don't re-run with a bigger budget chasing the difference; just note the gap when it is large enough to matter, without asserting more about its cause than you can see.

**Stopped short — say so:**

- **`limit_reached`** — your `--limit` stopped it. There is more.
- **`max_requests`** — the invocation's own request cap stopped it, not the data.
- **`rate_limited`** — the window is spent (exit 3). Stop; don't retry-loop.
- **`depth_capped`** — replies exist below what was fetched. Usually your `--depth`; sometimes a branch Reddit itself declines to expand any further, which the run abandons rather than retrying.
- **`comment_limit`** — material was left out because the comment budget ran out. Note what this does *not* say: the omission may be **top-level**, not only deeper. A thread with thousands of comments returns an unexpanded top-level remainder, and it lands here — so this can mean whole branches of the conversation are missing, not just their tails.

Both of the last two mean **you did not see the whole thread.** Summarizing them as if they were the full discussion is the single easiest way to be confidently wrong here, because a truncated tree reads exactly like a complete one.

Exit **7** is the related trap: `--since` was requested but the run stopped before confirming it reached that date. Whatever items you have are real, but you cannot claim they are all of them — and on an early stop there may be none at all, so check before reporting an empty file as an empty result. Note that exit 7 takes precedence over exit 3 — a run can be both rate-limited and `--since`-unconfirmed, and reports the latter.

## Terms of service — state it, don't bury it

Reddit's *Responsible Builder Policy* requires explicit approval for programmatic access to Reddit data. **This tool does not have that approval** — the official OAuth path is approval-gated and per-user, which is why this package reads anonymously instead.

That places it in a gray zone, and the honest framing is: personal or research use only, non-commercial, and **never** as a source of bulk or ML-training data. If a user's request is really "collect a dataset", say plainly that this isn't the tool for it rather than doing it in small pieces. Exit 3 means stop, not retry.

There is no account to ban here, which removes the risk the siblings carry — but an IP can still be blocked, and repeatedly hammering a spent window is how that happens.

## Third-party data — why the output is sensitive

Scraped output is other people's data: usernames, full post and comment text, karma, account age, posting history. "Public" is not the same as "not personal", and collecting it can make the *user* a data controller under GDPR/CCPA.

Reddit sharpens this in a way the siblings don't. Accounts here are **pseudonymous**, and pseudonymity is routinely broken by aggregating someone's history — which is exactly what `user --type overview` makes trivial. Treat a redditor's history as more sensitive than a public figure's timeline, not less, and pull it only when the question actually needs it.

So: **write output to `/tmp`, never into the repo**, and never `git add` it — a scrape committed to a repo outlives the question it was collected for, and this repo tracks synthetic JSON fixtures rather than blanket-ignoring `*.json`, so a capture saved into the working tree would not be caught by `.gitignore`. Delete intermediate files when you're done. Quote named individuals only when the question needs the quote; a summary usually answers it with less exposure.

`--raw` embeds the unparsed source payload and is redacted by default; `--no-redact` disables even that. Neither belongs in normal use — they are debugging aids for working on the scraper itself.

## NSFW — reachable, and not filtered

**Anonymous access reaches NSFW content freely.** This was measured, not assumed: adult subreddits return full listings logged out. Nothing is filtered, and there is no safe-mode flag.

`Post` and `Subreddit` both carry **`over_18`**, and it is `true` / `false` / `null` — **`null` means Reddit never marked the record, not that it's clean.** Check it explicitly rather than assuming a surface is safe: a general-topic search can return adult results, a subreddit name gives you no reliable signal, and a falsy test quietly treats "unknown" as "fine". When it comes back true, note it in what you report so the user isn't surprised by what they asked for. Don't refuse and don't demand confirmation: filtering is the caller's judgment, and a user who deliberately named an adult community doesn't need to be asked twice. `subreddit-info` is the cheap way to check before committing budget.

## When something fails

`agentic-reddit catalog` prints what each exit code *means*. This is what to *do* — and the theme is that most failures here are informative, not transient. **Retrying the same command is rarely the fix.**

**Exit 2 — not provisioned.** Run `agentic-reddit setup` yourself (Step 3). If it recurs after a successful setup, `agentic-reddit doctor` runs a bounded diagnostic, and `setup --force` re-downloads the browser and warms the profile again.

Know what `--force` does *not* do, because it is the thing people assume: it re-installs the browser and re-warms the named profile, but it does not wipe that profile's directory. If the profile itself is the problem, the clean reset is **a profile name you have never used** — `--profile <something-new>` on `setup` and on the read that follows starts from an empty directory.

**Exit 3 — the window is spent.** Stop that line of work and report what you have. See Budget before breadth.

**Exit 4 — Reddit returned something that isn't the JSON we expected**: an anti-bot challenge page, or a changed response shape. The code cannot tell you which, so try `agentic-reddit doctor`, then `agentic-reddit setup --force` to re-warm the profile — a stale profile that has lost its challenge clearance is the usual cause, and a fresh `--profile` name is the stronger version of the same move. **There is no local self-heal beyond that.** Unlike the Threads sibling, `doctor` has no `--refresh` flag and there are no persisted query ids to re-anchor; if a re-warm doesn't fix it, the response shape genuinely drifted and the fix ships as a release. Check Step 1, and if you're already current, say the tool needs a newer version rather than retrying.

Exit 4 means drift, so **a mistyped name does not land here** — it exits 5. Don't spend a `doctor` / `setup --force` cycle on a target problem.

**Exit 5 — the target doesn't exist, or was refused**: a deleted post, a suspended or nonexistent user, a private or banned community, or a subreddit that simply isn't there. Not retryable. Report it, and use `subreddits <query>` if it looks like a typo.

`subreddit-info <name>` is therefore your **existence check** for a community, and `user-info <name>` is the same thing for a person: both exit 5 on a name that isn't there. The listing paths deliberately don't — `subreddit <name>` on a nonexistent community exits 0 with `no_matches`, because Reddit answers an unknown name's listing with the same empty listing a real-but-quiet community returns, and the two are genuinely indistinguishable from one request. So `no_matches` means "nothing to show", not "no such place"; ask the `-info` command when you need to know which.

**Exit 7 — `--since` unconfirmed.** See `stop_reason`. The data you have is real but the range is not guaranteed complete.

**Exit 1 — usage error.** Read the message; it says what argparse rejected. `invalid choice: '<name>'` followed by the list of real subcommands means the command you reached for isn't in this install — almost always an **out-of-date install**, so go back to Step 1. Never work around a missing command by improvising a different one.

If that error arrives as `[REDACTED diagnostic text: N chars]` instead of readable text, you are on a pre-0.2.0 build, which over-redacted its own usage errors. That is itself the out-of-date signal, and the same fix applies. The usage line above the error lists the valid subcommands either way.

**Not a bug, though it looks like one:** `--since`/`--until` are rejected for `search --type sr` and `--type user` (only `--type link` supports a date window), and passing a date window forces `new` ordering, overriding `--sort`. Both are intentional.
