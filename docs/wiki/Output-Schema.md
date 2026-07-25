# Output Schema

Read commands save structured data to a file, not stdout. Use `agentic-reddit schema --json` for the authoritative JSON Schema draft 2020-12. Its root is a record `oneOf` `Post`, `Comment`, `Subreddit`, or `User`; definitions include `Media`, referenced by `Post.media`, and recursive `Comment.replies`. The schema is generated from the code's output serializers and field descriptions; this page is a guide, not a second schema definition.

## Files and summaries

`--format json` is the default; `--format ndjson` writes newline-delimited JSON. With no `--output`, the filename is:

```text
<safe_identifier>-<UTC timestampZ>.<json|ndjson>
```

It is placed in the platform data directory's `output/` folder. For `subreddit`, the identifier is the subreddit name; for `post`, it is the base-36 post ID. Each read command writes the file and emits one stderr summary containing counts, date range, stop reason, observed rate budget, and saved path. Mixed post/comment output uses comma-separated nonzero counts, such as `1 post, 2 comments`; homogeneous output uses one count and noun.

Read command object types:

| Command | Objects |
|---|---|
| `subreddit` | Post |
| `post` | Post at index 0, then threaded Comment objects |
| `comment` | Post at index 0, then the anchored Comment with recursive replies |
| `user` | Post and/or Comment, according to `--type` |
| `search` | Post (`link`), Subreddit (`sr`), or User (`user`) |
| `subreddits` | Subreddit |
| `subreddit-info` | One Subreddit |
| `user-info` | One User |
| `related` | Post |

Objects are deduplicated by `fullname`. Datetimes are ISO-8601 UTC values ending in `Z`. `id` is a base-36 ID; `fullname` is the corresponding Reddit fullname such as `t3_…` or `t1_…`.
`Post.over_18` and `Subreddit.over_18` preserve Reddit's explicit NSFW boolean. They are `null` when the upstream `t3.over_18` or `t5.over18` value is absent or malformed; `null` means the NSFW state is unknown, not safe.

## Types

### Post (`t3`)

`id`, `fullname`, `url` (Reddit permalink), `link_url` (external link or null), `subreddit`, `subreddit_prefixed`, `author`, `author_fullname`, `title`, `text`, `created_at`, `edited_at` (or null), `score`, `upvote_ratio`, `num_comments`, `num_crossposts`, `over_18`, `spoiler`, `is_self`, `is_video`, `is_original_content`, `stickied`, `pinned`, `locked`, `distinguished`, `flair`, `domain`, `thumbnail`, `media` (Media array), `total_awards`, `removed`, `captured_at`, and optional `raw`.

### Comment (`t1`)

`id`, `fullname`, `permalink`, `post_id`, `subreddit`, `parent_id`, `author`, `author_fullname`, `text`, `created_at`, `edited_at`, `score`, `depth`, `is_submitter`, `stickied`, `distinguished`, `controversiality`, `collapsed`, `score_hidden`, `total_awards`, `replies` (recursive Comment array), `more_count` (unexpanded remainder when truncated), `captured_at`, and optional `raw`.

### Subreddit (`t5`)

`id`, `fullname`, `name`, `prefixed`, `title`, `public_description`, `description`, `subscribers`, `created_at`, `over_18`, `subreddit_type`, `url`, `lang`, `icon_url`, `quarantine`, `captured_at`, and optional `raw`.

### User (`t2`)

`id`, `fullname`, `name`, `created_at`, `link_karma`, `comment_karma`, `total_karma`, `is_gold`, `is_mod`, `is_employee`, `verified`, `has_verified_email`, `icon_url`, `accept_followers`, `captured_at`, and optional `raw`.

### Media

Each `Post.media` item has `kind` (`image`, `video`, `gallery`, `embed`, or `unknown`), `url`, `width`, and `height`. Galleries can produce several Media items.

## Raw data and incomplete trees

`--raw` adds Reddit's raw `thing.data` alongside normalized fields. It is a debugging feature. By default, redaction is applied recursively to every `raw` attachment, including nested reply data; `--no-redact` disables only that raw-data redaction with a warning. Diagnostics also redact sensitive keys and truncate free-text values. Normalized result fields in the output file are not redacted by design; see [Security and Privacy](Security-and-Privacy.md).

A post result can be structurally incomplete when its summary says `depth_capped` or `comment_limit`. In that case `more_count` identifies unexpanded comment remainder; it does not mean the tree is complete. `tree_complete` means no unexpanded `more` remains.
