from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agentic_reddit.errors import EnvelopeParseError
from agentic_reddit.model import Comment, Post, User
from agentic_reddit.parse import (
    collect_more,
    parse_post_response,
    parse_subtree_response,
    parse_thing,
    splice_subtree,
    walk_listing,
    walk_listing_nodes,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> object:
    return json.loads((_FIXTURES / name).read_text())


def test_walk_listing_preserves_data_and_after_cursor() -> None:
    children, after = walk_listing(load_fixture("user_overview.json"))

    assert [child["name"] for child in children] == ["t3_overview01", "t1_comment01"]
    assert after == "t1_comment01"


def test_walk_listing_rejects_html_and_decoy_listing() -> None:
    with pytest.raises(EnvelopeParseError):
        walk_listing("<!doctype html><html>challenge</html>")
    with pytest.raises(EnvelopeParseError):
        walk_listing({"payload": load_fixture("user_overview.json")})


def test_kind_dispatch_uses_model_builders() -> None:
    overview, _ = walk_listing_nodes(load_fixture("user_overview.json"))
    users, _ = walk_listing_nodes(load_fixture("search_user.json"))

    assert isinstance(parse_thing(overview[0]), Post)
    assert isinstance(parse_thing(overview[1]), Comment)
    assert isinstance(parse_thing(users[0]), User)
    with pytest.raises(EnvelopeParseError):
        parse_thing({"kind": "more", "data": {}})


def test_post_response_collects_nested_and_top_level_more_in_tree_order() -> None:
    _, forest = parse_post_response(load_fixture("post_with_comment_tree.json"))

    more = collect_more(forest)

    assert [node["parent_id"] for node in more] == ["t1_comment01", "t3_tree001"]


def test_splice_subtree_replaces_t1_more_in_place() -> None:
    _, forest = parse_post_response(load_fixture("post_with_comment_tree.json"))
    subtree = parse_subtree_response(load_fixture("comment_subtree.json"))

    assert splice_subtree(forest, "t1_comment01", subtree) is True
    replies = forest[0]["data"]["replies"]["data"]["children"]
    assert [node["data"]["id"] for node in replies] == ["comment02", "comment03"]
    assert [node["parent_id"] for node in collect_more(forest)] == ["t3_tree001"]


def test_splice_subtree_keeps_visible_order_and_deduplicates_overlap() -> None:
    _, forest = parse_post_response(load_fixture("post_with_comment_tree.json"))
    subtree = parse_subtree_response(load_fixture("comment_subtree.json"))
    visible = copy.deepcopy(forest[0]["data"]["replies"]["data"]["children"][0])
    subtree["data"]["replies"]["data"]["children"].insert(0, visible)

    assert splice_subtree(forest, "t1_comment01", subtree) is True
    replies = forest[0]["data"]["replies"]["data"]["children"]
    assert [node["data"]["id"] for node in replies] == ["comment02", "comment03"]


def test_splice_subtree_leaves_t3_parented_more_for_retrieve_to_report() -> None:
    _, forest = parse_post_response(load_fixture("post_with_comment_tree.json"))
    subtree = parse_subtree_response(load_fixture("comment_subtree.json"))

    assert splice_subtree(forest, "t3_tree001", subtree) is False
    assert [node["parent_id"] for node in collect_more(forest)] == ["t1_comment01", "t3_tree001"]


def test_post_and_subtree_envelopes_fail_closed() -> None:
    post = load_fixture("post_with_comment_tree.json")
    post[0]["data"]["children"].append({"kind": "t3", "data": {}})
    with pytest.raises(EnvelopeParseError):
        parse_post_response(post)

    subtree = load_fixture("comment_subtree.json")
    subtree[1]["data"]["children"][0]["data"]["replies"] = {"children": []}
    with pytest.raises(EnvelopeParseError):
        parse_subtree_response(subtree)
