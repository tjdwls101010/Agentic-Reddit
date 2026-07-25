"""Strict walkers for Reddit's stable Listing and comment-tree envelopes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .errors import EnvelopeParseError
from .model import (
    Comment,
    Post,
    Subreddit,
    User,
    build_comment,
    build_post,
    build_subreddit,
    build_user,
)

_THING_KINDS = frozenset({"t1", "t2", "t3", "t5", "more"})
_MISSING = object()


def _drift(path: str, expected: str) -> EnvelopeParseError:
    return EnvelopeParseError(f"response envelope drift at {path}: expected {expected}")


def _thing(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _drift(path, "a thing object")
    kind = value.get("kind")
    if kind not in _THING_KINDS:
        raise _drift(f"{path}.kind", "t1, t2, t3, t5, or more")
    if not isinstance(value.get("data"), dict):
        raise _drift(f"{path}.data", "an object")
    return value


def _listing(value: object, path: str = "response") -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(value, dict):
        raise _drift(path, "a Listing object")
    if value.get("kind") != "Listing":
        raise _drift(f"{path}.kind", "Listing")
    data = value.get("data")
    if not isinstance(data, dict):
        raise _drift(f"{path}.data", "an object")
    children = data.get("children")
    if not isinstance(children, list):
        raise _drift(f"{path}.data.children", "a list")
    after = data.get("after")
    if after is not None and not isinstance(after, str):
        raise _drift(f"{path}.data.after", "a string or null")
    return [
        _thing(child, f"{path}.data.children[{index}]") for index, child in enumerate(children)
    ], after


def walk_listing(response: object) -> tuple[list[dict[str, Any]], str | None]:
    """Return Listing thing data and its fullname ``after`` cursor."""
    children, after = _listing(response)
    return [child["data"] for child in children], after


def walk_listing_nodes(response: object) -> tuple[list[dict[str, Any]], str | None]:
    """Return raw Listing things when callers must retain ``kind`` and ``more``."""
    return _listing(response)


def parse_thing(
    thing: object, *, captured_at: datetime | None = None, include_raw: bool = False
) -> Post | Comment | Subreddit | User:
    """Normalize one concrete Reddit thing through the authoritative builders.

    ``more`` is a structural pointer rather than an output object and must be
    handled with :func:`collect_more` instead.
    """
    node = _thing(thing, "thing")
    data = node["data"]
    kind = node["kind"]
    if kind == "t1":
        return build_comment(data, captured_at=captured_at, include_raw=include_raw)
    if kind == "t2":
        return build_user(data, captured_at=captured_at, include_raw=include_raw)
    if kind == "t3":
        return build_post(data, captured_at=captured_at, include_raw=include_raw)
    if kind == "t5":
        return build_subreddit(data, captured_at=captured_at, include_raw=include_raw)
    raise _drift("thing.kind", "a concrete t1, t2, t3, or t5 thing")


def _reply_children(comment: dict[str, Any], path: str) -> list[dict[str, Any]]:
    replies = comment.get("replies", _MISSING)
    if replies is _MISSING:
        raise _drift(f"{path}.replies", "an empty string or a Listing")
    if replies == "":
        return []
    children, _ = _listing(replies, f"{path}.replies")
    for index, child in enumerate(children):
        if child["kind"] not in {"t1", "more"}:
            raise _drift(f"{path}.replies.data.children[{index}].kind", "t1 or more")
    return children


def _validate_comment_forest(nodes: list[dict[str, Any]], path: str) -> None:
    for index, node in enumerate(nodes):
        node_path = f"{path}[{index}]"
        if node["kind"] not in {"t1", "more"}:
            raise _drift(f"{node_path}.kind", "t1 or more")
        if node["kind"] == "t1":
            _validate_comment_forest(
                _reply_children(node["data"], node_path + ".data"), node_path + ".replies"
            )
        else:
            parent_id = node["data"].get("parent_id")
            count = node["data"].get("count")
            if not isinstance(parent_id, str) or not parent_id.startswith(("t1_", "t3_")):
                raise _drift(f"{node_path}.data.parent_id", "a t1_ or t3_ fullname")
            if isinstance(count, bool) or not isinstance(count, int):
                raise _drift(f"{node_path}.data.count", "an integer")


def parse_post_response(response: object) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Split the anchored two-Listing post response into post data and a forest."""
    if not isinstance(response, list) or len(response) != 2:
        raise _drift("response", "a two-element array")
    post_nodes, _ = _listing(response[0], "response[0]")
    if len(post_nodes) != 1 or post_nodes[0]["kind"] != "t3":
        raise _drift("response[0].data.children", "exactly one t3 thing")
    comment_nodes, _ = _listing(response[1], "response[1]")
    _validate_comment_forest(comment_nodes, "response[1].data.children")
    return post_nodes[0]["data"], comment_nodes


def parse_subtree_response(response: object) -> dict[str, Any]:
    """Return the rooted ``t1`` from a permalink-subtree two-Listing response."""
    if not isinstance(response, list) or len(response) != 2:
        raise _drift("response", "a two-element array")
    posts, _ = _listing(response[0], "response[0]")
    if len(posts) != 1 or posts[0]["kind"] != "t3":
        raise _drift("response[0].data.children", "exactly one t3 thing")
    roots, _ = _listing(response[1], "response[1]")
    if len(roots) != 1 or roots[0]["kind"] != "t1":
        raise _drift("response[1].data.children", "exactly one t1 thing")
    root = roots[0]
    _validate_comment_forest(
        _reply_children(root["data"], "response[1].data.children[0].data"),
        "response[1].data.children[0].data.replies",
    )
    return root


def collect_more(comment_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``more`` data objects in depth-first display order."""
    _validate_comment_forest(comment_nodes, "comment_nodes")
    result: list[dict[str, Any]] = []

    def visit(nodes: list[dict[str, Any]], path: str) -> None:
        for index, node in enumerate(nodes):
            if node["kind"] == "more":
                result.append(node["data"])
            else:
                visit(
                    _reply_children(node["data"], f"{path}[{index}].data"),
                    f"{path}[{index}].replies",
                )

    visit(comment_nodes, "comment_nodes")
    return result


def _fullname(data: dict[str, Any], prefix: str) -> str:
    name = data.get("name")
    if isinstance(name, str) and name.startswith(prefix):
        return name
    identifier = data.get("id")
    return f"{prefix}{identifier}" if isinstance(identifier, str) else ""


def _more_identity(node: dict[str, Any]) -> tuple[str, int, int | None]:
    data = node["data"]
    count = data["count"]
    depth = data.get("depth")
    return (
        data["parent_id"],
        count,
        depth if isinstance(depth, int) and not isinstance(depth, bool) else None,
    )


def _merge_replies(existing: dict[str, Any], returned: dict[str, Any]) -> None:
    existing_children = _reply_children(existing, "existing")
    returned_children = _reply_children(returned, "returned")
    existing_by_fullname = {
        _fullname(node["data"], "t1_"): node for node in existing_children if node["kind"] == "t1"
    }
    existing_mores = {_more_identity(node) for node in existing_children if node["kind"] == "more"}
    for node in returned_children:
        if node["kind"] != "t1":
            continue
        duplicate = existing_by_fullname.get(_fullname(node["data"], "t1_"))
        if duplicate is not None:
            _merge_replies(duplicate["data"], node["data"])
    additions = [
        node
        for node in returned_children
        if (node["kind"] == "t1" and _fullname(node["data"], "t1_") not in existing_by_fullname)
        or (node["kind"] == "more" and _more_identity(node) not in existing_mores)
    ]
    if not additions:
        return
    parent_id = _fullname(existing, "t1_")
    for index, child in enumerate(existing_children):
        if child["kind"] == "more" and child["data"].get("parent_id") == parent_id:
            existing["replies"]["data"]["children"][index : index + 1] = additions
            return
    existing["replies"]["data"]["children"].extend(additions)


def splice_subtree(
    comment_nodes: list[dict[str, Any]], parent_id: str, subtree: dict[str, Any]
) -> bool:
    """Merge a subtree response at its ``t1``-parented ``more`` slot.

    Already-visible reply siblings retain their display order.  Returned overlap is
    reconciled recursively, while only new reply nodes replace the selected pointer.
    """
    _validate_comment_forest(comment_nodes, "comment_nodes")
    root = _thing(subtree, "subtree")
    if root["kind"] != "t1":
        raise _drift("subtree.kind", "t1")
    if not isinstance(parent_id, str) or not parent_id.startswith("t1_"):
        return False
    if _fullname(root["data"], "t1_") != parent_id:
        raise _drift("subtree.data", f"the requested parent {parent_id!r}")
    replacement = _reply_children(root["data"], "subtree.data")

    def visit(nodes: list[dict[str, Any]]) -> bool:
        for node in nodes:
            if node["kind"] != "t1":
                continue
            data = node["data"]
            if _fullname(data, "t1_") == parent_id:
                replies = data.get("replies", _MISSING)
                if replies == "":
                    return False
                children, _ = _listing(replies, "parent.replies")
                visible = {
                    _fullname(child["data"], "t1_"): child
                    for child in children
                    if child["kind"] == "t1"
                }
                visible_mores = {
                    _more_identity(child) for child in children if child["kind"] == "more"
                }
                for child in replacement:
                    if child["kind"] == "t1":
                        duplicate = visible.get(_fullname(child["data"], "t1_"))
                        if duplicate is not None:
                            _merge_replies(duplicate["data"], child["data"])
                additions = [
                    child
                    for child in replacement
                    if (child["kind"] == "t1" and _fullname(child["data"], "t1_") not in visible)
                    or (child["kind"] == "more" and _more_identity(child) not in visible_mores)
                ]
                for index, child in enumerate(children):
                    if child["kind"] == "more" and child["data"].get("parent_id") == parent_id:
                        if additions:
                            replies["data"]["children"][index : index + 1] = additions
                        return True
                return False
            if visit(_reply_children(data, "comment.data")):
                return True
        return False

    return visit(comment_nodes)
