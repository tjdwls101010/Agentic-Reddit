"""Reddit identifier normalization and validation."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from .errors import InvalidIdentifierError

_ALLOWED_HOSTS = frozenset(
    {"reddit.com", "www.reddit.com", "old.reddit.com", "np.reddit.com", "sh.reddit.com"}
)
_SUBREDDIT_RE = re.compile(r"[A-Za-z0-9_]{3,21}")
_USERNAME_RE = re.compile(r"[A-Za-z0-9_-]{3,20}")
_ID36_RE = re.compile(r"[0-9A-Za-z]{1,10}")


def normalize_subreddit_identifier(raw: str) -> tuple[str, str]:
    """Return a validated subreddit identifier as ``("subreddit", name)``."""
    value = _require_text(raw, "subreddit")
    if _looks_like_url(value):
        segments = _reddit_url_segments(value)
        if len(segments) != 2 or segments[0].casefold() != "r":
            raise InvalidIdentifierError("expected a subreddit URL")
        name = segments[1]
    else:
        parts = [part for part in value.split("/") if part]
        if len(parts) == 1:
            name = parts[0]
        elif len(parts) == 2 and parts[0].casefold() == "r":
            name = parts[1]
        else:
            raise InvalidIdentifierError("invalid subreddit identifier")
    if not _SUBREDDIT_RE.fullmatch(name):
        raise InvalidIdentifierError("invalid subreddit name")
    return "subreddit", name


def normalize_subreddit_group(raw: str) -> tuple[str, str]:
    """Return a validated combined subreddit listing identifier."""
    value = _require_text(raw, "subreddit")
    if _looks_like_url(value):
        segments = _reddit_url_segments(value)
        if len(segments) != 2 or segments[0].casefold() != "r":
            raise InvalidIdentifierError("expected a subreddit URL")
        name = segments[1]
    else:
        parts = [part for part in value.split("/") if part]
        if len(parts) == 1:
            name = parts[0]
        elif len(parts) == 2 and parts[0].casefold() == "r":
            name = parts[1]
        else:
            raise InvalidIdentifierError("invalid subreddit identifier")
    names = name.split("+")
    if len(names) > 10:
        raise InvalidIdentifierError("too many subreddits in a combined listing")
    if any(not part or not _SUBREDDIT_RE.fullmatch(part) for part in names):
        raise InvalidIdentifierError("invalid subreddit name")
    return "subreddits", name


def normalize_user_identifier(raw: str) -> tuple[str, str]:
    """Return a validated Reddit user identifier as ``("user", name)``."""
    value = _require_text(raw, "user")
    if _looks_like_url(value):
        segments = _reddit_url_segments(value)
        if len(segments) != 2 or segments[0].casefold() not in {"u", "user"}:
            raise InvalidIdentifierError("expected a Reddit user URL")
        name = segments[1]
    else:
        parts = [part for part in value.split("/") if part]
        if len(parts) == 1:
            name = parts[0]
        elif len(parts) == 2 and parts[0].casefold() in {"u", "user"}:
            name = parts[1]
        else:
            raise InvalidIdentifierError("invalid user identifier")
    if not _USERNAME_RE.fullmatch(name):
        raise InvalidIdentifierError("invalid Reddit username")
    return "user", name


def normalize_post_identifier(raw: str) -> tuple[str, str]:
    """Return a validated post identifier as ``("post", id36)``."""
    value = _require_text(raw, "post")
    if _looks_like_url(value):
        _, post_id, _ = _permalink_parts(value)
    else:
        post_id = value.removeprefix("t3_").removeprefix("T3_")
    return "post", _normalize_id36(post_id, "post")


def normalize_comment_identifier(raw: str) -> tuple[str, str]:
    """Return a comment permalink identifier as ``("comment", id36)``."""
    value = _require_text(raw, "comment")
    if not _looks_like_url(value):
        raise InvalidIdentifierError("a comment identifier must be a Reddit permalink")
    _, _, comment_id = _permalink_parts(value)
    if comment_id is None:
        raise InvalidIdentifierError("expected a Reddit comment permalink")
    return "comment", comment_id


def normalize_permalink(raw: str) -> tuple[str, str]:
    """Classify a Reddit post or comment permalink as a ``(kind, id36)`` pair."""
    value = _require_text(raw, "permalink")
    if not _looks_like_url(value):
        raise InvalidIdentifierError("a permalink must be a Reddit URL")
    _, post_id, comment_id = _permalink_parts(value)
    if comment_id is not None:
        return "comment", comment_id
    return "post", post_id


def permalink_identifiers(raw: str) -> tuple[str, str, str | None]:
    """Return ``(subreddit, post_id36, comment_id36_or_none)`` for a permalink."""
    return _permalink_parts(_require_text(raw, "permalink"))


def _require_text(raw: str, label: str) -> str:
    if not isinstance(raw, str):
        raise InvalidIdentifierError(f"{label} identifier must be text")
    value = raw.strip()
    if not value:
        raise InvalidIdentifierError(f"{label} identifier is empty")
    return value


def _looks_like_url(value: str) -> bool:
    lowered = value.casefold()
    return "://" in value or any(lowered.startswith(f"{host}/") for host in _ALLOWED_HOSTS)


def _reddit_url_segments(value: str) -> list[str]:
    candidate = value if "://" in value else f"https://{value}"
    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise InvalidIdentifierError("malformed Reddit URL") from exc
    if parts.scheme.casefold() not in {"http", "https"}:
        raise InvalidIdentifierError("only http/https Reddit URLs are accepted")
    if parts.username is not None or parts.password is not None:
        raise InvalidIdentifierError("Reddit URLs must not contain credentials")
    if parts.hostname is None or parts.hostname.casefold() not in _ALLOWED_HOSTS:
        raise InvalidIdentifierError("URL host must be an allowed Reddit host")
    try:
        path = unquote(parts.path, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidIdentifierError("malformed Reddit URL path") from exc
    return [segment for segment in path.split("/") if segment]


def _permalink_parts(value: str) -> tuple[str, str, str | None]:
    segments = _reddit_url_segments(value)
    if len(segments) < 4 or segments[0].casefold() != "r" or segments[2].casefold() != "comments":
        raise InvalidIdentifierError("expected a Reddit post permalink")
    _, subreddit = normalize_subreddit_identifier(f"r/{segments[1]}")
    post_id = _normalize_id36(segments[3], "post")
    tail = segments[4:]
    if not tail:
        return subreddit, post_id, None
    if len(tail) == 1:
        return subreddit, post_id, None
    if tail[0] == "_":
        if len(tail) != 2:
            raise InvalidIdentifierError("invalid Reddit comment permalink")
        comment_id = tail[1]
    else:
        if len(tail) != 2:
            raise InvalidIdentifierError("invalid Reddit comment permalink")
        comment_id = tail[1]
    return subreddit, post_id, _normalize_id36(comment_id, "comment")


def _normalize_id36(value: str, label: str) -> str:
    if not _ID36_RE.fullmatch(value):
        raise InvalidIdentifierError(f"invalid {label} id")
    return value.casefold()
