"""Pure builders for Reddit's read-only JSON endpoints."""

from __future__ import annotations

from urllib.parse import urlencode

from .errors import InvalidIdentifierError
from .identity import (
    normalize_post_identifier,
    normalize_subreddit_group,
    normalize_subreddit_identifier,
    normalize_user_identifier,
)

_SUBREDDIT_SORTS = frozenset({"hot", "new", "top", "rising", "controversial"})
_COMMENT_SORTS = frozenset({"confidence", "top", "best", "new", "controversial", "old", "qa"})
_USER_TYPES = frozenset({"overview", "submitted", "comments", "top"})
_USER_SORTS = frozenset({"new", "hot", "top", "controversial"})
_SEARCH_TYPES = frozenset({"link", "sr", "user"})
_SEARCH_SORTS = frozenset({"relevance", "hot", "top", "new", "comments"})
_TIMES = frozenset({"hour", "day", "week", "month", "year", "all"})
_DUPLICATES_SORTS = frozenset({"num_comments", "new"})


def subreddit_path(
    subreddit: str,
    *,
    sort: str = "hot",
    limit: int | None = None,
    after: str | None = None,
    count: int | None = None,
    time: str | None = None,
) -> str:
    """Build a subreddit listing path."""
    _, name = normalize_subreddit_group(subreddit)
    _choice(sort, _SUBREDDIT_SORTS, "subreddit sort")
    if time is not None:
        _choice(time, _TIMES, "time")
    return _with_query(
        f"/r/{name}/{sort}.json",
        (("limit", limit), ("after", after), ("count", count), ("t", time)),
    )


def post_path(
    subreddit: str | None,
    post_id: str | None = None,
    *,
    limit: int | None = None,
    depth: int | None = None,
    sort: str | None = None,
) -> str:
    """Build a post-and-comments path.

    When only one positional argument is supplied it is a bare post id and the
    host's ``/comments/<id>`` form is used.
    """
    if post_id is None:
        post_id = subreddit
        subreddit = None
    _, normalized_post_id = normalize_post_identifier(_required_text(post_id, "post"))
    if subreddit is None:
        path = f"/comments/{normalized_post_id}.json"
    else:
        _, name = normalize_subreddit_identifier(subreddit)
        path = f"/r/{name}/comments/{normalized_post_id}.json"
    if sort is not None:
        _choice(sort, _COMMENT_SORTS, "comment sort")
    return _with_query(path, (("limit", limit), ("depth", depth), ("sort", sort)))


def comment_subtree_path(
    subreddit: str,
    post_id: str,
    comment_id: str,
    *,
    limit: int | None = None,
    depth: int | None = None,
    sort: str | None = None,
    context: int | None = None,
) -> str:
    """Build a comment-permalink subtree path without using ``morechildren``."""
    _, name = normalize_subreddit_identifier(subreddit)
    _, normalized_post_id = normalize_post_identifier(post_id)
    _, normalized_comment_id = normalize_post_identifier(comment_id)
    if sort is not None:
        _choice(sort, _COMMENT_SORTS, "comment sort")
    if context is not None and (
        not isinstance(context, int) or isinstance(context, bool) or context < 0
    ):
        raise InvalidIdentifierError("invalid comment context")
    return _with_query(
        f"/r/{name}/comments/{normalized_post_id}/_/{normalized_comment_id}.json",
        (("limit", limit), ("depth", depth), ("sort", sort), ("context", context)),
    )


def user_path(
    user: str,
    *,
    listing_type: str = "overview",
    sort: str | None = None,
    time: str | None = None,
    after: str | None = None,
    count: int | None = None,
    limit: int | None = None,
) -> str:
    """Build a user's activity listing path."""
    _, name = normalize_user_identifier(user)
    _choice(listing_type, _USER_TYPES, "user listing type")
    if sort is not None:
        _choice(sort, _USER_SORTS, "user sort")
    if time is not None:
        _choice(time, _TIMES, "time")
    return _with_query(
        f"/user/{name}/{listing_type}.json",
        (("sort", sort), ("t", time), ("after", after), ("count", count), ("limit", limit)),
    )


def user_about_path(user: str) -> str:
    """Build a Reddit user metadata path."""
    _, name = normalize_user_identifier(user)
    return f"/user/{name}/about.json"


def duplicates_path(
    post: str,
    *,
    sort: str | None = None,
    crossposts_only: bool = False,
    after: str | None = None,
    count: int | None = None,
    limit: int | None = None,
) -> str:
    """Build a post's other-discussions listing path."""
    _, post_id = normalize_post_identifier(post)
    if sort is not None:
        _choice(sort, _DUPLICATES_SORTS, "duplicates sort")
    return _with_query(
        f"/duplicates/{post_id}.json",
        (
            ("sort", sort),
            ("crossposts_only", 1 if crossposts_only else None),
            ("after", after),
            ("count", count),
            ("limit", limit),
        ),
    )


def search_path(
    query: str,
    *,
    subreddit: str | None = None,
    sort: str | None = None,
    time: str | None = None,
    type: str = "link",
    after: str | None = None,
    count: int | None = None,
    limit: int | None = None,
) -> str:
    """Build a global or subreddit-restricted search path."""
    query = _required_text(query, "search query")
    if sort is not None:
        _choice(sort, _SEARCH_SORTS, "search sort")
    if time is not None:
        _choice(time, _TIMES, "time")
    _choice(type, _SEARCH_TYPES, "search type")
    if subreddit is None:
        return _with_query(
            "/search.json",
            (
                ("q", query),
                ("sort", sort),
                ("t", time),
                ("type", type),
                ("after", after),
                ("count", count),
                ("limit", limit),
            ),
        )
    _, name = normalize_subreddit_identifier(subreddit)
    if type != "link":
        raise InvalidIdentifierError("subreddit search only supports type 'link'")
    return _with_query(
        f"/r/{name}/search.json",
        (
            ("q", query),
            ("restrict_sr", 1),
            ("sort", sort),
            ("t", time),
            ("after", after),
            ("count", count),
            ("limit", limit),
        ),
    )


def subreddits_search_path(
    query: str,
    *,
    after: str | None = None,
    count: int | None = None,
    limit: int | None = None,
) -> str:
    """Build a subreddit discovery path."""
    return _with_query(
        "/subreddits/search.json",
        (
            ("q", _required_text(query, "search query")),
            ("after", after),
            ("count", count),
            ("limit", limit),
        ),
    )


def about_path(subreddit: str) -> str:
    """Build a subreddit metadata path."""
    _, name = normalize_subreddit_identifier(subreddit)
    return f"/r/{name}/about.json"


def _with_query(path: str, items: tuple[tuple[str, object | None], ...]) -> str:
    params = [(key, value) for key, value in items if value is not None]
    return path if not params else f"{path}?{urlencode(params)}"


def _choice(value: str, choices: frozenset[str], label: str) -> None:
    if value not in choices:
        raise InvalidIdentifierError(f"invalid {label}")


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidIdentifierError(f"{label} is empty")
    return value.strip()
