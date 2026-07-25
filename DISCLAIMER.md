# Disclaimer

## No Reddit approval

Reddit's Responsible Builder Policy requires explicit approval for programmatic access to Reddit data. This tool does **not** have that approval. Use of this tool may violate Reddit's terms or policies. Users accept all consequences, including IP blocks and account or service termination.

## Permitted use

This project is for non-commercial personal or research use only. Do not use it commercially, and do not repurpose its output as bulk data or for ML-training datasets.

## Third-party personal data

Normalized output fields intentionally contain unredacted third-party personal
data, including usernames, posts, comments, and histories. Public availability
does not remove personal-data risk. In particular, aggregating a user's public
history can enable de-anonymisation. Only optional `raw` attachments are
recursively redacted by default; `--raw --no-redact` disables that raw-only
protection and prints a warning.

Treat every output file as third-party personal data: write it outside a
repository, never commit it, limit access, and delete it when no longer needed.

## NSFW content

NSFW content is anonymously reachable on Reddit and can be returned unfiltered by this tool. `over_18` is included on posts and subreddits when Reddit provides it. Callers are responsible for deciding how to handle that content.
