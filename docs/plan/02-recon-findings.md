# Recon Findings — Live Capture 2026-07-24

Empirical grounding for the whole plan. Captured live via **Claude-in-Chrome** on a real Chrome profile — first logged in, then **logged out** for the anonymous verification pass — plus `curl` from the maintainer's own machine (residential IP). Everything below is **observed**, not assumed. The account used for recon plays **no runtime role**: the shipped tool never logs in.

**The `Listing`/`thing` data schema is ~15 years stable and is the safe part. The _access_ layer is the volatile, project-defining part** — §1–§3 are what forced the architecture.

---

## 1. The anti-bot wall

| Request | Result |
|---|---|
| `curl https://www.reddit.com/r/python/hot.json` (browser UA, residential IP) | **403**, ~190 KB JS-challenge HTML |
| `curl …` default UA | **403**, same challenge |
| `curl https://old.reddit.com/r/python/hot.json` (browser UA) | **403**, same challenge |
| `curl https://oauth.reddit.com/r/python/hot` (no token) | **403**, same challenge |
| `curl -d grant_type=client_credentials https://www.reddit.com/api/v1/access_token` | **401** clean JSON, 41 bytes |
| **In-browser, same-origin `fetch('/r/python/hot.json')`** | **200**, clean `Listing` JSON — *both logged in and logged out* |

**Reading:** Reddit fronts programmatic (non-browser) requests to its web hosts with a JavaScript anti-bot challenge — UA-independent and IP-independent (residential still blocked). Only a real browser executes the challenge. The token endpoint is *not* challenged, but see §2 for why that doesn't help.

## 2. The OAuth path is closed (approval-gated) — verified twice

`https://www.reddit.com/prefs/apps` still renders the classic developer form (`web`/`installed`/`script` radios, a reCAPTCHA, a `create app` button). **But the backend refuses to create the app**, returning a pointer to the *Responsible Builder Policy* instead.

**Verified empirically: app creation was refused on two different Reddit accounts** — one 1-day-old (karma 1, email verified) and one established. This is a **policy gate, not an account-quality heuristic.**

Reddit's own policy text confirms it:

- *Responsible Builder Policy* → **"Approval is required: You must request access and get explicit approval before accessing any Reddit data through our API."** Also: **"Be transparent: … This prohibits registering multiple accounts or submitting multiple requests for the same use case."** (Account-shopping is explicitly out.)
- Developers section → non-commercial developers **"should use the Developer Platform ('Devvit') to build apps on Reddit"**; Mod Tools access is **"granted solely for the purpose of performing moderation actions"**; *"If your use case is not supported by Devvit, file a ticket"* (→ `https://support.reddithelp.com/hc/en-us/requests/new`).
- `reddit.com/wiki/api` → only *"some apps are still running on our legacy Data API"*; new Data API apps are for *"a valid moderation use case."*

**Consequence:** OAuth is unusable here — not merely inconvenient. Approval is **per-user**, so even a granted approval would not let anyone else install and run the tool, which is the project's stated goal. (Superseded decision D1-OLD.)

## 3. Anonymous verification pass — ALL v1 ENDPOINTS PASS

The decisive test. The Chrome profile was **logged out** (page shows Log In / Sign Up; `/api/v1/me.json` returns only a `{features}` stub with no `name`), then every v1 read path was exercised same-origin:

| Probe | Result (logged out) |
|---|---|
| `/r/python/new.json?limit=3` | **200** — `kind: Listing`, children all `t3`, `after: t3_…` |
| `…&after=<after>&count=3` (page 2) | **200** — 3 items, **0 overlap** with page 1, fresh `after` |
| `/r/AskReddit/comments/<id>.json?limit=50&depth=3` | **200** — 2-element array, `[0]`=`t3`, `[1]`=32 top-level `t1`, `more` node present (`count: 24`, 13 children, `parent_id: t1_…`) |
| **`/r/AskReddit/comments/<id>/_/<comment_id>.json?limit=100&depth=5`** | **200** — root `kind: t1`, `body` present, clean fields, `replies` = nested `Listing` |
| `/user/spez/submitted.json` / `comments.json` / `overview.json` | **200** — `t3` / `t1` / mixed `t1`+`t3` |
| `/search.json?q=python&type=link` | **200** — `t3`, `after` present |
| `/search.json?q=python&type=sr` | **200** — `t5` |
| `/search.json?q=python&type=user` | **200** — `t2` |
| `/r/python/search.json?q=async&restrict_sr=1&sort=new` | **200** — `t3` |
| `/subreddits/search.json?q=python&limit=3` | **200** — `t5` |
| `/r/python/about.json` | **200** — `t5`, `subscribers: 1,499,183`, `subreddit_type: public` |
| `/r/python/top.json?t=week` | **200** — `t3` |

**Conclusion: D2 (anonymous-only) is verified, not assumed.** No account is needed for any v1 capability.

**Caveat carried into Phase 0:** this profile had already visited Reddit and therefore held anti-bot clearance cookies. It proves *anonymous reads work*; it does **not** prove *a cold, brand-new profile can obtain clearance*. That is Q-1, the one remaining gate — and it is exactly what a real browser exists to do (the earlier logged-out probe was observed being served `?js_challenge=1&token=…`, i.e. the challenge flow engages normally).

## 4. Rate-limit model — measured precisely (drives D8)

Every `.json` response carries budget headers. Three probes 3–4s apart, logged out:

```
x-ratelimit-used:       27  →  28  →  29
x-ratelimit-remaining:  73  →  72  →  71        (used + remaining = 100)
x-ratelimit-reset:     164 → 161 → 157          (real-seconds countdown)
```

A 6-request burst at ~570 ms intervals produced **no 429** and decremented `remaining` by exactly 1 per request.

**Model: ~100 requests per ~600-second window ⇒ ~1 request / 6 s sustained.** Budget is observable in-flight, so the client should govern against the headers rather than guess (D8). Burst is tolerated; sustained over-rate is not.

**Practical consequence:** the request budget — not wall-clock — is the scarce resource. Expanding one deep comment tree and sweeping five subreddits draw on the same ~100 requests.

## 5. Endpoints & the clean schema

The universal envelope is a **`Listing`**: `{"kind":"Listing","data":{"after":<fullname|null>,"before":…,"children":[<thing>…]}}` where each `thing` is `{"kind":"t1|t2|t3|t5|more","data":{…}}`.

| CLI command | Endpoint | Envelope |
|---|---|---|
| `subreddit <name>` | `/r/<name>/{hot,new,top,rising,controversial}.json?limit=&after=&count=&t=` | `Listing` of `t3` |
| `post <url\|id>` | `/r/<sub>/comments/<id36>.json?limit=&depth=&sort=` | 2-element array: `[Listing(t3 ×1), Listing(t1…/more)]` |
| (comment subtree, §6.2) | `/r/<sub>/comments/<post_id36>/_/<comment_id36>.json?limit=&depth=` | 2-element array, root `t1` |
| `user <name>` | `/user/<name>/{overview,submitted,comments,top}.json?sort=&t=&after=` | `Listing` of `t3` and/or `t1` |
| `search <query>` (global) | `/search.json?q=&sort=&t=&type=link\|sr\|user&after=` | `Listing` of `t3` / `t5` / `t2` |
| `search --subreddit <s>` | `/r/<s>/search.json?q=&restrict_sr=1&sort=&t=` | `Listing` of `t3` |
| `subreddits <query>` | `/subreddits/search.json?q=&limit=` | `Listing` of `t5` |
| `subreddit-info <name>` | `/r/<name>/about.json` | single `t5` (`{kind,data}`) |

`t3`=link/post, `t1`=comment, `t2`=account, `t5`=subreddit, `more`=collapsed "load more" pointer. **These prefixes and this envelope have been stable since ~2010.** They are also exactly what `oauth.reddit.com` serves (minus the `.json` suffix), so this table survives any future transport swap.

**Confirmed out of scope (need a real *user* OAuth token; empty even with cookies):** `/best.json` (home feed), `/subreddits/mine/subscriber.json`, `/message/inbox.json` all returned `children: []`; `/api/v1/me.json` returns only a `{features}` stub.

## 6. Comment tree & the `more` node

`post` returns a **two-element array**: `[0]` a `Listing` with the single `t3`, `[1]` a `Listing` of top-level `t1`s. Each `t1.data.replies` is **either `""` (no replies) or a nested `Listing`** of child `t1`s (recursive) — inline up to the response's `depth`/`limit`. Beyond that sit **`more` nodes**, observed live:

```
{"kind":"more","data":{"count":24,"name":"t1_…","id":"…","parent_id":"t1_ozhnvd8","depth":2,
                       "children":["<id36>", …13 ids…]}}
```

### 6.1 `/api/morechildren` is UNUSABLE from the web origin (plan-changing)

Live test against a 13.5k-comment `r/AskReddit` thread: `POST /api/morechildren` with `link_id=t3_<post>&children=<csv>&sort=confidence&api_type=json` returned **HTTP 200, 39 things, `errors: []`** — but every `things[].data` carried the **HTML-render shape**:

```
{parent, content, contentText, contentHTML, link, replies, id}     // NOT a t1 data object
```

Retried with `raw_json=1` and with `renderstyle=json`: **identical rendered shape both times.** From the `www.reddit.com` origin Reddit serves its web UI's rendered variant, not the API's `t1` objects. Using it would drag us back into HTML parsing — exactly what this architecture exists to avoid. **Do not use `/api/morechildren`.**

### 6.2 The permalink-subtree GET is the expansion mechanism (verified clean, logged out)

```
GET /r/<sub>/comments/<post_id36>/_/<comment_id36>.json?limit=100&depth=5
```

Verified: **200**, 2-element array, root child `kind: "t1"` with the full clean field set (`id, body, author, created_utc, score, parent_id, depth, replies`) and `replies` as a **nested `Listing`**. This returns the whole subtree rooted at that comment — exactly the descendants a `more` node was hiding — in the same schema as the rest of the pipeline.

**Expansion rule (D7):** for a `more` whose `parent_id` is `t1_<id36>`, issue one permalink-subtree GET rooted at that parent and splice the returned subtree in place of the `more`. **No `parent_id` re-threading is needed** — the response is already a tree.

**Known limitation — top-level `more`:** when `parent_id` is the post itself (`t3_…`) there is no parent comment to root on. Expanding it would need one GET per child id36. **Phase 0 Q-3 must decide** between raising `limit` on the initial fetch, per-child GETs under budget, or reporting the remainder unexpanded. Report the choice honestly via `stop_reason`.

**Cost model:** one request per expanded `more`, against ~100 requests per 10 minutes (§4). Fully expanding a 13.5k-comment thread is **not feasible** and must not be attempted.

## 7. Pagination

**Not** cursor-opaque like the Meta siblings — Reddit uses **fullname cursors**: `Listing.data.after` (a `t3_…`/`t1_…` fullname) is the next page's `after=`; `count=` tracks the running item count; `limit` per page maxes at **100**. EOF when `after` is null/absent. Verified live: page 2 returned **zero overlapping ids**. Dedup on the item **fullname**, never on `captured_at`.

## 8. Date bounds

Reddit exposes **no server-side `since`/`until`** on listings. Only `top`/`controversial` accept a coarse `t=hour|day|week|month|year|all` (verified: `/r/python/top.json?t=week` → 200). Precise `--since`/`--until` must be applied **client-side** over `--sort new` (walk newest→oldest, stop when older than `--since`; drop items newer than `--until`). Mirror Threads' client-side date-window logic and its exit-7 "since-unconfirmed" caveat.

## 9. NSFW is fully reachable anonymously (corrects an early assumption)

Measured logged out:

| Probe | Result |
|---|---|
| `/r/nsfw/about.json` | **200** — `over18: true`, 4,580,442 subscribers, `subreddit_type: public` |
| `/r/gonewild/about.json` | **200** — `over18: true`, 5,559,898 subscribers |
| `/r/nsfw/hot.json?limit=2` | **200** — items present, `over_18: true` |

The early draft's assumption ("anonymous is not age-verified, so NSFW will be limited") is **false**. Implications: populate `over_18` faithfully (note the spelling split — `t3.over_18` vs `t5.over18`), document in the README that NSFW can be returned, and have the skill check the flag rather than assume a safe surface.

## 10. Real field lists (grounds the data model)

Load-bearing `data` keys from live responses (the selected subset appears in `03`).

- **`t3` (Post):** `id, name, subreddit, subreddit_name_prefixed, subreddit_id, author, author_fullname, title, selftext, selftext_html, url, domain, permalink, created_utc, edited, score, ups, downs, upvote_ratio, num_comments, num_crossposts, over_18, spoiler, stickied, pinned, locked, is_self, is_video, is_original_content, link_flair_text, distinguished, thumbnail, thumbnail_width/height, media, secure_media, media_embed, gallery_data?, total_awards_received, removed_by_category, suggested_sort, hidden, saved, likes` (+ ~40 mod/flair fields we drop).
- **`t1` (Comment):** `id, name, subreddit, subreddit_id, link_id, parent_id, author, author_fullname, body, body_html, created_utc, edited, score, ups, downs, depth, replies (nested Listing | ""), is_submitter, stickied, distinguished, controversiality, collapsed, collapsed_reason, score_hidden, permalink, locked, total_awards_received, removal_reason`.
- **`t5` (Subreddit):** `id, name, display_name, display_name_prefixed, title, public_description, description, description_html, subscribers, created_utc, over18, subreddit_type, url, lang, icon_img, community_icon, banner_img, header_title, submission_type, quarantine, advertiser_category` (+ ~60 user_/mod flags dropped). Note `about` uses **`over18`**, not `over_18`.
- **`t2` (User/about):** `id, name, created_utc, link_karma, comment_karma, total_karma, awardee_karma, awarder_karma, is_gold, is_mod, is_employee, verified, has_verified_email, icon_img, snoovatar_img, accept_followers, is_blocked, is_friend, hide_from_robots, subreddit`.

## 11. Internal web-app API (observed, NOT used)

The new Reddit web app posts to **`https://www.reddit.com/svc/shreddit/graphql`** (same-origin, cookie auth, persisted-query GraphQL), and `/svc/shreddit/session` mints the web app's own bearer token. Both were considered and **rejected**: gnarlier than `.json`, subject to the same anti-bot, tied to Reddit's own web-client identity, and strictly inferior to the stable `Listing` schema. **Do not target `/svc/shreddit/graphql`, and do not harvest the web app's bearer token.**

## 12. What maps from the siblings

- **From `agentic-threads` / `agentic-x` (shape, ~80% of the package):** `config.py` (paths, non-bypassable pause clamp, env prefix), identifier normalize-then-validate, `retrieve.py` (pagination + limit/since/until + `stop_reason` vocabulary + request budget), the `model.py`/`parse.py` split (dataclass + `to_dict` + generated JSON Schema; anchored envelope walk raising `EnvelopeParseError`), `redact.py`, `errors.py` + exit-code contract, `catalog`/`schema` self-describing commands, packaging + trusted publishing + tests/CI scaffold + PII discipline.
- **From `agentic-facebook` (transport idea only):** scrapling browser provisioning, the isolated `PLAYWRIGHT_BROWSERS_PATH` install, and the persistent-context profile dir. **Not** its passive-scroll/HTML-parse read path — we call JSON endpoints instead, which is strictly cleaner.
- **Deliberately NOT ported:** cookie/credential stores and `login` (no account, D2), `docids.py`, `transaction.py`, `gql.py`, `tokens.py`, the `[browser]` extra pattern (browser is a base dep, D16), and any aggressive stealth/evasion layer beyond scrapling's minimal default (D15).
