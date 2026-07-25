# FAQ and Troubleshooting

## How do I prepare the browser?

Run:

```bash
agentic-reddit setup
agentic-reddit status
```

Setup installs the isolated browser and warms a persistent profile without credentials. `status` performs one inexpensive readiness read. Use `agentic-reddit doctor` for deeper diagnostics. Exit code 2 means the browser is missing, the profile is not warmed, or the session is not ready; run `setup` for the same profile and profile root used by the read command.

## A challenge page appeared instead of JSON

This is exit code 4. It is treated as a hard challenge/drift signal and is not automatically retried. Run `agentic-reddit doctor`, then re-run `agentic-reddit setup` for the selected profile. `setup --headed` can provide a visible browser for legitimate setup diagnosis. Do not bypass or automate challenge evasion.

## The command is rate-limited

Exit code 3 means Reddit reported an exhausted budget or returned HTTP 429. The stderr summary reports the remaining and used budget. Stop and wait for the reset, or use `--wait-on-limit --max-wait SECONDS` when a bounded wait is appropriate. The client always keeps its one-second minimum request pause and does not retry HTTP 429 in a loop.

## My target is unavailable

Exit code 5 covers a nonexistent, private, banned, quarantined, suspended, or deleted subreddit, user, or post. Confirm that the target is public and available in an ordinary browser. The package is anonymous and read-only; it cannot log in or access restricted targets.

## I received a schema-drift or envelope error

Exit code 4 also covers a Reddit response whose expected listing or post/comment envelope no longer matches. Run `doctor` to distinguish a challenge from a changed response, re-run `setup` if the profile is not ready, and upgrade when a compatible release is available. Include the command, version, exit code, and redacted diagnostic information in a bug report. Never include profile data, cookies, credentials, or raw third-party content.

## Why did a `post` result stop before all comments?

A summary of `depth_capped` or `comment_limit` means requested limits stopped adaptive comment-tree expansion; `more_count` records the remaining unexpanded comments. It is not a complete tree. `tree_complete` means there are no unexpanded `more` nodes. The client expands comment subtrees through public permalink-subtree reads; it does not use `/api/morechildren`.

## Why did a date-bounded run exit 7?

Exit code 7 means `--since` was requested but the run stopped before it could establish that the boundary was reached, often because of request-budget or rate-limit stopping. Narrow the input, reduce the necessary range, or resume after the rate budget is available.

## Why is there no output on stdout?

Read commands write JSON or NDJSON to a file and put one concise result summary on stderr. Use `--output PATH` to choose a destination. Without it, files are stored under the platform data directory's `output/` folder. See [Output Schema](Output-Schema.md).

## Why did the command return exit 1?

Exit code 1 means invalid command usage or identifier, or an unexpected/setup failure. Use `--help` to check valid input forms. Subreddit inputs accept names, `r/name`, `/r/name`, or a subreddit URL; user inputs accept names, `u/name`, `/user/name`, or a profile URL; post inputs accept an allowed Reddit URL, `t3_<id36>`, or bare `<id36>`.

## Does the package use credentials or login?

No. It accepts no Reddit credentials, OAuth client, cookie import, or login. The only persisted state is the app-owned browser profile used for public anonymous browsing. Reddit has not approved this package; follow its Terms of Service and applicable community rules.

## Can results include sensitive or NSFW material?

Yes. Output is unredacted by design and may contain third-party personal information or NSFW and otherwise disturbing public content. Store and share files accordingly. See [Security and Privacy](Security-and-Privacy.md).
