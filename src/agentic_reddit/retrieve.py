"""Transport-agnostic Reddit read orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from . import config, endpoints, parse
from .errors import EnvelopeParseError, RateLimitedError
from .model import Comment, Post, Subreddit, User, build_comment, build_post

Item = Post | Comment | Subreddit | User

STOP_REASONS = frozenset(
    {
        "limit_reached",
        "listing_exhausted",
        "no_matches",
        "since_crossed",
        "tree_complete",
        "depth_capped",
        "comment_limit",
        "rate_limited",
        "max_requests",
    }
)


@dataclass
class RetrieveResult:
    """The normalized output and the honest reason a retrieval stopped."""

    items: list[Item]
    stop_reason: str
    requests_made: int
    since_target_crossed: bool = False

    @property
    def posts(self) -> list[Post]:
        return [item for item in self.items if isinstance(item, Post)]

    @property
    def comments(self) -> list[Comment]:
        return [item for item in self.items if isinstance(item, Comment)]

    @property
    def subreddits(self) -> list[Subreddit]:
        return [item for item in self.items if isinstance(item, Subreddit)]

    @property
    def users(self) -> list[User]:
        return [item for item in self.items if isinstance(item, User)]


@dataclass
class _Run:
    session: object
    max_requests: int
    requests_made: int = 0

    def get(self, path: str) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
        if self.requests_made >= self.max_requests:
            return None, "max_requests"
        try:
            body = self.session.get_json(path)
        except RateLimitedError:
            return None, "rate_limited"
        self.requests_made += 1
        if not isinstance(body, (dict, list)):
            raise EnvelopeParseError("Reddit endpoint returned a non-JSON envelope")
        return body, None


def _run(session: object, max_requests: int | None) -> _Run:
    budget = config.DEFAULT_MAX_REQUESTS if max_requests is None else max_requests
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ValueError("max_requests must be a non-negative integer")
    return _Run(session, budget)


def _bounds(
    since: datetime | date | None, until: datetime | date | None
) -> tuple[datetime | None, datetime | None]:
    def normalize(value: datetime | date | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=UTC)
        raise ValueError("date bounds must be dates or datetimes")

    since, until = normalize(since), normalize(until)
    if since is not None and until is not None and since > until:
        raise ValueError("since must not be later than until")
    return since, until


def _validate_limit(limit: int | None, name: str = "limit") -> None:
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
        raise ValueError(f"{name} must be a non-negative integer")


def _result(
    items: list[Item], reason: str, run: _Run, *, since_crossed: bool = False
) -> RetrieveResult:
    if reason not in STOP_REASONS:
        raise AssertionError(f"unknown stop reason: {reason}")
    return RetrieveResult(items, reason, run.requests_made, since_crossed)


def _paginate(
    run: _Run,
    path_for_page: Callable[[str | None, int], str],
    *,
    allowed_kinds: set[str],
    limit: int | None,
    since: datetime | None,
    until: datetime | None,
    raw: bool,
) -> RetrieveResult:
    items: list[Item] = []
    seen: set[str] = set()
    cursor: str | None = None
    seen_cursors: set[str] = set()
    since_crossed = False

    if limit == 0:
        return _result(items, "limit_reached", run)
    while True:
        body, reason = run.get(path_for_page(cursor, len(seen)))
        if reason is not None:
            return _result(items, reason, run, since_crossed=since_crossed)
        assert body is not None
        raw_items, after = parse.walk_listing_nodes(body)
        page_items = _listing_items(raw_items, allowed_kinds=allowed_kinds, raw=raw)
        for index, item in enumerate(page_items):
            fullname = item.fullname
            if fullname in seen:
                continue
            seen.add(fullname)
            created_at = getattr(item, "created_at", None)
            if (since is not None or until is not None) and created_at is None:
                raise EnvelopeParseError("date-bounded listing record is missing created_at")
            if since is not None and created_at < since:
                since_crossed = True
                continue
            if until is not None and created_at > until:
                continue
            items.append(item)
            if limit is not None and len(items) >= limit:
                has_unseen_page_item = any(
                    candidate.fullname not in seen for candidate in page_items[index + 1 :]
                )
                stop_reason = (
                    "limit_reached"
                    if after is not None or has_unseen_page_item
                    else "listing_exhausted"
                )
                return _result(items, stop_reason, run, since_crossed=since_crossed)
        if since_crossed:
            return _result(items, "since_crossed", run, since_crossed=True)
        if after is None:
            # An exhausted listing also confirms there is no older unseen item.
            if since is not None:
                since_crossed = True
            return _result(
                items,
                "no_matches" if not items else "listing_exhausted",
                run,
                since_crossed=since_crossed,
            )
        if after in seen_cursors:
            raise EnvelopeParseError("listing repeated an after cursor")
        seen_cursors.add(after)
        cursor = after


def fetch_subreddit(
    session: object,
    subreddit: str,
    *,
    sort: str = "hot",
    time: str | None = None,
    limit: int | None = None,
    since: datetime | date | None = None,
    until: datetime | date | None = None,
    max_requests: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Fetch a subreddit listing, deduplicated by fullname."""
    subreddit = _required_identifier(subreddit, "subreddit")
    _validate_limit(limit)
    since, until = _bounds(since, until)
    effective_sort = "new" if since is not None or until is not None else sort
    run = _run(session, max_requests)
    return _paginate(
        run,
        lambda after, count: endpoints.subreddit_path(
            subreddit,
            sort=effective_sort,
            time=time,
            limit=100,
            after=after,
            count=count or None,
        ),
        allowed_kinds={"t3"},
        limit=limit,
        since=since,
        until=until,
        raw=raw,
    )


def fetch_user(
    session: object,
    user: str,
    *,
    listing_type: str = "overview",
    sort: str | None = None,
    time: str | None = None,
    limit: int | None = None,
    since: datetime | date | None = None,
    until: datetime | date | None = None,
    max_requests: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Fetch a user's submitted posts, comments, or mixed overview."""
    user = _required_identifier(user, "user")
    _validate_limit(limit)
    since, until = _bounds(since, until)
    effective_sort = "new" if since is not None or until is not None else sort
    run = _run(session, max_requests)
    return _paginate(
        run,
        lambda after, count: endpoints.user_path(
            user,
            listing_type=listing_type,
            sort=effective_sort,
            time=time,
            limit=100,
            after=after,
            count=count or None,
        ),
        allowed_kinds={"t1", "t3"},
        limit=limit,
        since=since,
        until=until,
        raw=raw,
    )


def search(
    session: object,
    query: str,
    *,
    subreddit: str | None = None,
    search_type: str = "link",
    sort: str | None = None,
    time: str | None = None,
    limit: int | None = None,
    since: datetime | date | None = None,
    until: datetime | date | None = None,
    max_requests: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Search globally or within a subreddit."""
    _validate_limit(limit)
    kinds = {"link": {"t3"}, "sr": {"t5"}, "user": {"t2"}}
    if search_type not in kinds:
        raise ValueError("search_type must be one of link, sr, user")
    since, until = _bounds(since, until)
    if (since is not None or until is not None) and search_type != "link":
        raise ValueError("date bounds are only supported for link searches")
    effective_sort = "new" if since is not None or until is not None else sort
    run = _run(session, max_requests)
    return _paginate(
        run,
        lambda after, count: endpoints.search_path(
            query,
            subreddit=subreddit,
            type=search_type,
            sort=effective_sort,
            time=time,
            limit=100,
            after=after,
            count=count or None,
        ),
        allowed_kinds=kinds[search_type],
        limit=limit,
        since=since,
        until=until,
        raw=raw,
    )


def find_subreddits(
    session: object,
    query: str,
    *,
    limit: int | None = None,
    max_requests: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Find subreddits by name or topic."""
    _validate_limit(limit)
    run = _run(session, max_requests)
    return _paginate(
        run,
        lambda after, count: endpoints.subreddits_search_path(
            query, after=after, count=count or None, limit=100
        ),
        allowed_kinds={"t5"},
        limit=limit,
        since=None,
        until=None,
        raw=raw,
    )


def fetch_subreddit_info(
    session: object,
    subreddit: str,
    *,
    max_requests: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Fetch one subreddit's metadata."""
    subreddit = _required_identifier(subreddit, "subreddit")
    run = _run(session, max_requests)
    body, reason = run.get(endpoints.about_path(subreddit))
    if reason is not None:
        return _result([], reason, run)
    if (
        not isinstance(body, dict)
        or body.get("kind") != "t5"
        or not isinstance(body.get("data"), dict)
    ):
        raise EnvelopeParseError("subreddit about response was not a t5 envelope")
    items = _listing_items([body], allowed_kinds={"t5"}, raw=raw)
    return _result(items, "listing_exhausted", run)


def fetch_post(
    session: object,
    post: str,
    *,
    subreddit: str | None = None,
    comment_sort: str = "confidence",
    depth: int | None = None,
    comment_limit: int | None = 500,
    max_requests: int | None = None,
    raw: bool = False,
) -> RetrieveResult:
    """Fetch a post and expand t1-parented ``more`` nodes through permalink GETs."""
    post = _required_identifier(post, "post")
    _validate_limit(depth, "depth")
    _validate_limit(comment_limit, "comment_limit")
    run = _run(session, max_requests)
    body, reason = run.get(
        endpoints.post_path(subreddit, post, limit=comment_limit, depth=depth, sort=comment_sort)
    )
    if reason is not None:
        return _result([], reason, run)
    assert body is not None
    root_data, comment_nodes = parse.parse_post_response(body)
    root, comments = _post_models(root_data, comment_nodes, raw=raw)
    if comment_limit == 0:
        return _result([root], "comment_limit", run)
    if _cap_comment_forest(comment_nodes, comment_limit, root.fullname):
        root, comments = _post_models(root_data, comment_nodes, raw=raw)
        return _result([root, *comments], "comment_limit", run)

    while True:
        mores = parse.collect_more(comment_nodes)
        if not mores:
            return _result([root, *comments], "tree_complete", run)
        current_count = _comment_count(comments)
        expandable = next(
            (
                more
                for more in mores
                if _more_parent(more).startswith("t1_")
                and (_more_depth(more) is None or depth is None or _more_depth(more) < depth)
            ),
            None,
        )
        if expandable is None:
            if any(_more_parent(more).startswith("t3_") for more in mores):
                return _result([root, *comments], "comment_limit", run)
            if any(_more_parent(more).startswith("t1_") for more in mores):
                return _result([root, *comments], "depth_capped", run)
            raise EnvelopeParseError("more node has an invalid parent_id")
        if comment_limit is not None and current_count >= comment_limit:
            return _result([root, *comments], "comment_limit", run)
        parent_id = _more_parent(expandable)
        remaining = None if comment_limit is None else max(1, comment_limit - current_count)
        subtree_path = endpoints.comment_subtree_path(
            root.subreddit,
            root.id,
            parent_id.removeprefix("t1_"),
            limit=remaining,
            depth=None if depth is None else max(0, depth - (_more_depth(expandable) or 0)),
        )
        before = _comment_tree_signature(comment_nodes)
        subtree, reason = run.get(subtree_path)
        if reason is not None:
            return _result([root, *comments], reason, run)
        assert subtree is not None
        subtree_root = parse.parse_subtree_response(subtree)
        if not parse.splice_subtree(comment_nodes, parent_id, subtree_root):
            raise EnvelopeParseError("subtree response could not be spliced into its more node")
        if _comment_tree_signature(comment_nodes) == before:
            raise EnvelopeParseError(
                f"permalink subtree made no progress for {parent_id}: "
                "comment tree signature unchanged"
            )
        capped = _cap_comment_forest(comment_nodes, comment_limit, root.fullname)
        root, comments = _post_models(root_data, comment_nodes, raw=raw)
        if capped:
            return _result([root, *comments], "comment_limit", run)


def _required_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    return value


_STRUCTURAL_LISTING_KINDS = frozenset({"more"})


def _listing_items(
    nodes: list[dict[str, Any]], *, allowed_kinds: set[str], raw: bool
) -> list[Item]:
    items: list[Item] = []
    for node in nodes:
        kind = node["kind"]
        if kind in allowed_kinds:
            items.append(parse.parse_thing(node, include_raw=raw))
        elif kind not in _STRUCTURAL_LISTING_KINDS:
            raise EnvelopeParseError(f"listing contained unexpected {kind} thing for this command")
    return items


def _post_models(
    root_data: dict[str, Any], comment_nodes: list[dict[str, Any]], *, raw: bool
) -> tuple[Post, list[Comment]]:
    return (
        build_post(root_data, include_raw=raw),
        [
            build_comment(node["data"], include_raw=raw)
            for node in comment_nodes
            if node["kind"] == "t1"
        ],
    )


def _node_fullname(node: dict[str, Any]) -> str:
    data = node["data"]
    name = data.get("name")
    if isinstance(name, str) and name.startswith("t1_"):
        return name
    identifier = data.get("id")
    return f"t1_{identifier}" if isinstance(identifier, str) else ""


def _node_more_count(node: dict[str, Any]) -> int:
    if node["kind"] == "more":
        count = node["data"]["count"]
        return count if isinstance(count, int) and not isinstance(count, bool) else 0
    return 1 + sum(_node_more_count(child) for child in _reply_children(node))


def _reply_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    replies = node["data"].get("replies")
    if not isinstance(replies, dict) or replies.get("kind") != "Listing":
        return []
    data = replies.get("data")
    children = data.get("children") if isinstance(data, dict) else None
    return children if isinstance(children, list) else []


def _more_node(parent_id: str, count: int, depth: int | None) -> dict[str, Any]:
    data: dict[str, Any] = {"parent_id": parent_id, "count": count}
    if depth is not None:
        data["depth"] = depth
    return {"kind": "more", "data": data}


def _cap_comment_forest(nodes: list[dict[str, Any]], limit: int | None, root_id: str) -> bool:
    """Cap materialized comments depth-first, retaining an honest remainder pointer."""
    if limit is None:
        return False
    remaining = limit
    truncated = False

    def cap(children: list[dict[str, Any]], parent_id: str, depth: int | None) -> None:
        nonlocal remaining, truncated
        kept: list[dict[str, Any]] = []
        omitted = 0
        for node in children:
            if node["kind"] == "more":
                if omitted:
                    omitted += _node_more_count(node)
                else:
                    kept.append(node)
                continue
            if remaining == 0:
                omitted += _node_more_count(node)
                continue
            kept.append(node)
            remaining -= 1
            child_depth = node["data"].get("depth")
            cap(
                _reply_children(node),
                _node_fullname(node),
                child_depth
                if isinstance(child_depth, int) and not isinstance(child_depth, bool)
                else depth,
            )
        if omitted:
            truncated = True
            kept.append(_more_node(parent_id, omitted, depth))
        children[:] = kept

    cap(nodes, root_id, 0)
    return truncated


def _comment_tree_signature(
    nodes: list[dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[tuple[str, int, int | None], ...]]:
    comments: list[str] = []
    mores: list[tuple[str, int, int | None]] = []

    def visit(children: list[dict[str, Any]]) -> None:
        for node in children:
            if node["kind"] == "t1":
                comments.append(_node_fullname(node))
                visit(_reply_children(node))
            else:
                data = node["data"]
                depth = data.get("depth")
                mores.append(
                    (
                        data["parent_id"],
                        data["count"],
                        depth if isinstance(depth, int) and not isinstance(depth, bool) else None,
                    )
                )

    visit(nodes)
    return tuple(comments), tuple(mores)


def _comment_count(comments: list[Comment]) -> int:
    return sum(1 + _comment_count(comment.replies) for comment in comments)


def _more_parent(more: object) -> str:
    value = getattr(more, "parent_id", None)
    if value is None and isinstance(more, dict):
        value = more.get("parent_id")
    return value if isinstance(value, str) else ""


def _more_depth(more: object) -> int | None:
    value = getattr(more, "depth", None)
    if value is None and isinstance(more, dict):
        value = more.get("depth")
    return value if isinstance(value, int) and not isinstance(value, bool) else None
