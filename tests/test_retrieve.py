from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentic_reddit.errors import EnvelopeParseError, NotFoundError, TargetUnavailableError
from agentic_reddit.retrieve import (
    fetch_comment,
    fetch_post,
    fetch_related,
    fetch_subreddit,
    fetch_subreddit_info,
    fetch_user,
    fetch_user_info,
    find_subreddits,
    search,
)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.paths = []

    def get_json(self, path):
        self.paths.append(path)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def listing(children, after=None):
    return {"kind": "Listing", "data": {"children": children, "after": after}}


def thing(kind, data):
    return {"kind": kind, "data": data}


def post(identifier, created=1000, **extra):
    return thing(
        "t3",
        {
            "id": identifier,
            "name": f"t3_{identifier}",
            "permalink": f"/r/python/comments/{identifier}/title",
            "subreddit": "python",
            "subreddit_name_prefixed": "r/python",
            "title": identifier,
            "created_utc": created,
            **extra,
        },
    )


def comment(identifier, *, replies="", depth=0):
    return thing(
        "t1",
        {
            "id": identifier,
            "name": f"t1_{identifier}",
            "permalink": f"/r/python/comments/post/_/{identifier}",
            "link_id": "t3_post",
            "subreddit": "python",
            "parent_id": "t3_post",
            "body": identifier,
            "created_utc": 1000,
            "depth": depth,
            "replies": replies,
        },
    )


def more(parent_id, count=1, depth=1):
    return thing("more", {"parent_id": parent_id, "count": count, "depth": depth})


def post_response(comments):
    return [listing([post("post")]), listing(comments)]


def test_subreddit_paginates_deduplicates_and_stops_at_eof():
    session = FakeSession(
        [
            listing([post("one"), post("two")], after="t3_two"),
            listing([post("two"), post("three")]),
        ]
    )

    result = fetch_subreddit(session, "python", limit=10)

    assert [item.fullname for item in result.items] == ["t3_one", "t3_two", "t3_three"]
    assert result.stop_reason == "listing_exhausted"
    assert result.requests_made == 2
    assert "after=t3_two" in session.paths[1]


def test_listing_limit_and_date_bounds_are_composed_honestly():
    session = FakeSession([listing([post("new", 300), post("old", 100)])])
    since = datetime.fromtimestamp(200, UTC)

    result = fetch_subreddit(session, "python", since=since, until=datetime.fromtimestamp(400, UTC))

    assert [item.id for item in result.posts] == ["new"]
    assert result.stop_reason == "since_crossed"
    assert result.since_target_crossed
    assert session.paths == ["/r/python/new.json?limit=100"]
    limited = fetch_subreddit(
        FakeSession([listing([post("one"), post("two")], after="t3_two")]), "python", limit=1
    )
    assert limited.stop_reason == "limit_reached"
    assert len(limited.items) == 1


def test_listing_limit_reports_exhaustion_when_the_last_page_item_is_accepted():
    result = fetch_subreddit(FakeSession([listing([post("one")])]), "python", limit=1)

    assert result.stop_reason == "listing_exhausted"


@pytest.mark.parametrize(
    ("operation", "response"),
    [
        (lambda session: fetch_subreddit(session, "python"), listing([comment("reply")])),
        (lambda session: fetch_user(session, "person"), listing([thing("t5", {"id": "sub"})])),
        (lambda session: search(session, "python", search_type="user"), listing([post("post")])),
        (lambda session: find_subreddits(session, "python"), listing([post("post")])),
    ],
)
def test_listing_commands_reject_incompatible_concrete_kinds(operation, response):
    with pytest.raises(EnvelopeParseError, match="unexpected"):
        operation(FakeSession([response]))


def test_find_subreddits_paginates_deduplicates_and_detects_repeated_cursors():
    subreddit_one = thing(
        "t5", {"id": "one", "name": "t5_one", "display_name": "one", "url": "/r/one/"}
    )
    subreddit_two = thing(
        "t5", {"id": "two", "name": "t5_two", "display_name": "two", "url": "/r/two/"}
    )
    session = FakeSession(
        [
            listing([subreddit_one], after="t5_one"),
            listing([subreddit_one, subreddit_two]),
        ]
    )

    result = find_subreddits(session, "python", limit=10)

    assert [item.fullname for item in result.items] == ["t5_one", "t5_two"]
    assert result.stop_reason == "listing_exhausted"
    assert result.requests_made == 2
    assert "after=t5_one" in session.paths[1]
    assert "count=1" in session.paths[1]
    budgeted = find_subreddits(
        FakeSession([listing([subreddit_one], after="t5_one")]),
        "python",
        max_requests=1,
    )
    assert budgeted.stop_reason == "max_requests"

    with pytest.raises(EnvelopeParseError, match="repeated an after cursor"):
        find_subreddits(
            FakeSession([listing([subreddit_one], after="t5_one"), listing([], after="t5_one")]),
            "python",
        )


def test_find_subreddits_limit_zero_avoids_io_and_exact_limit_reports_exhaustion():
    zero_session = FakeSession([])
    zero = find_subreddits(zero_session, "python", limit=0)
    subreddit = thing(
        "t5", {"id": "sub", "name": "t5_sub", "display_name": "python", "url": "/r/python/"}
    )
    exact = find_subreddits(FakeSession([listing([subreddit])]), "python", limit=1)

    assert zero.items == []
    assert zero.stop_reason == "limit_reached"
    assert zero.requests_made == 0
    assert zero_session.paths == []
    assert exact.stop_reason == "listing_exhausted"


def test_date_bounds_force_new_sort_for_user_and_link_search():
    since = datetime.fromtimestamp(200, UTC)

    user_session = FakeSession([listing([post("one")])])
    fetch_user(user_session, "person", sort="hot", since=since)
    assert user_session.paths == ["/user/person/overview.json?sort=new&limit=100"]

    search_session = FakeSession([listing([post("one")])])
    search(search_session, "python", sort="relevance", until=since)
    assert search_session.paths == ["/search.json?q=python&sort=new&type=link&limit=100"]


@pytest.mark.parametrize("search_type", ["sr", "user"])
def test_date_bounds_reject_non_link_searches(search_type):
    with pytest.raises(ValueError, match="date bounds are only supported for link searches"):
        search(FakeSession([]), "python", search_type=search_type, since=datetime.now(UTC))


def test_request_budget_and_unavailable_target_propagate():
    exhausted = fetch_subreddit(
        FakeSession([listing([post("one")], after="t3_one")]), "python", max_requests=1
    )
    assert exhausted.stop_reason == "max_requests"

    with pytest.raises(TargetUnavailableError):
        fetch_subreddit(FakeSession([TargetUnavailableError("private")]), "python")


def test_user_search_subreddits_and_info_return_their_declared_kinds():
    user_item = thing("t2", {"id": "user", "name": "person", "created_utc": 1})
    subreddit_item = thing(
        "t5", {"id": "sub", "name": "t5_sub", "display_name": "python", "url": "/r/python/"}
    )
    mixed = fetch_user(
        FakeSession([listing([post("one"), comment("reply")])]), "person", listing_type="overview"
    )
    people = search(FakeSession([listing([user_item])]), "person", search_type="user")
    communities = find_subreddits(FakeSession([listing([subreddit_item])]), "python")
    about = fetch_subreddit_info(FakeSession([subreddit_item]), "python")

    assert {type(item).__name__ for item in mixed.items} == {"Post", "Comment"}
    assert [type(item).__name__ for item in people.items] == ["User"]
    assert [type(item).__name__ for item in communities.items] == ["Subreddit"]
    assert [type(item).__name__ for item in about.items] == ["Subreddit"]


def test_subreddit_info_separates_a_missing_subreddit_from_envelope_drift():
    with pytest.raises(NotFoundError):
        fetch_subreddit_info(FakeSession([listing([])]), "zqxnope12345")

    drifted = (
        listing([thing("t5", {"id": "sub"})]),
        thing("t3", {"id": "post"}),
        {"kind": "Listing", "data": []},
    )
    for response in drifted:
        with pytest.raises(EnvelopeParseError, match="t5 envelope"):
            fetch_subreddit_info(FakeSession([response]), "python")


def test_post_splices_t1_more_with_permalink_subtree():
    parent_replies = listing([more("t1_parent")])
    parent = comment("parent", replies=parent_replies)
    subtree_parent = comment("parent", replies=listing([comment("child", depth=1)]))
    subtree = [listing([post("post")]), listing([subtree_parent])]

    result = fetch_post(
        FakeSession([post_response([parent]), subtree]), "post", comment_limit=10, max_requests=3
    )

    assert result.stop_reason == "tree_complete"
    assert result.comments[0].replies[0].id == "child"
    assert result.requests_made == 2


def test_comment_expands_nested_more_and_uses_returned_parent():
    root = comment("root", replies=listing([more("t1_root")]))
    root["data"]["parent_id"] = "t1_ancestor"
    subtree_root = comment("root", replies=listing([comment("child", depth=1)]))
    subtree = [listing([post("post")]), listing([subtree_root])]
    session = FakeSession([post_response([root]), subtree])

    result = fetch_comment(
        session, "python", "post", "root", comment_limit=10, context=1, max_requests=3
    )

    assert [type(item).__name__ for item in result.items] == ["Post", "Comment"]
    assert result.comments[0].replies[0].id == "child"
    assert "sort=confidence&context=1" in session.paths[0]


def test_comment_reports_a_missing_comment_rather_than_the_whole_thread():
    # Reddit answers an anchored request for a comment that is not in the post with
    # the post's ordinary top-level listing, so the requested id must be found in
    # what came back.  Shape alone is not enough: a post with a single top-level
    # comment returns the same one-t1 forest a genuine anchor does, and accepting
    # it would hand back an unrelated comment as the requested one.
    for fallback in (
        post_response([comment("first"), comment("second")]),
        post_response([comment("only")]),
    ):
        with pytest.raises(NotFoundError, match="comment does not exist"):
            fetch_comment(FakeSession([fallback]), "python", "post", "missing")


def test_comment_accepts_a_requested_comment_nested_under_a_context_ancestor():
    anchor = comment("ancestor", replies=listing([comment("target", depth=1)]))
    result = fetch_comment(
        FakeSession([post_response([anchor])]), "python", "post", "TARGET", context=3
    )
    assert result.comments[0].id == "ancestor"
    assert result.comments[0].replies[0].id == "target"


def test_user_info_requires_and_returns_t2():
    result = fetch_user_info(
        FakeSession([thing("t2", {"id": "synthetic", "name": "t2_synthetic"})]), "synthetic"
    )
    assert [item.fullname for item in result.users] == ["t2_synthetic"]
    with pytest.raises(EnvelopeParseError, match="not a t2 envelope"):
        fetch_user_info(FakeSession([listing([])]), "synthetic")


def test_related_selects_second_listing_and_deduplicates():
    response = [listing([post("original")]), listing([post("other"), post("other")])]
    result = fetch_related(FakeSession([response]), "original")

    assert [item.id for item in result.posts] == ["other"]
    assert result.stop_reason == "listing_exhausted"


def test_post_expands_nested_mores_before_reporting_top_level_remainder():
    first = comment("first", replies=listing([more("t1_first")]))
    second = comment("second", replies=listing([more("t1_second")]))
    first_subtree = [
        listing([post("post")]),
        listing([comment("first", replies=listing([comment("one")]))]),
    ]
    second_subtree = [
        listing([post("post")]),
        listing([comment("second", replies=listing([comment("two")]))]),
    ]
    session = FakeSession(
        [post_response([more("t3_post"), first, second]), first_subtree, second_subtree]
    )

    result = fetch_post(session, "post", comment_limit=10)

    assert result.stop_reason == "comment_limit"
    assert [reply.id for reply in result.comments[0].replies] == ["one"]
    assert [reply.id for reply in result.comments[1].replies] == ["two"]
    assert session.paths == [
        "/comments/post.json?limit=10&sort=confidence",
        "/r/python/comments/post/_/first.json?limit=8",
        "/r/python/comments/post/_/second.json?limit=7",
    ]


def test_post_reports_top_level_more_depth_and_comment_caps():
    top_level = fetch_post(
        FakeSession([post_response([more("t3_post", count=10)])]), "post", comment_limit=10
    )
    assert top_level.stop_reason == "comment_limit"

    nested = comment("parent", replies=listing([more("t1_parent", depth=1)]))
    depth_capped = fetch_post(
        FakeSession([post_response([nested])]), "post", depth=1, comment_limit=10
    )
    assert depth_capped.stop_reason == "depth_capped"

    comment_capped = fetch_post(FakeSession([post_response([nested])]), "post", comment_limit=1)
    assert comment_capped.stop_reason == "comment_limit"


def test_post_comment_limit_caps_oversized_initial_and_subtree_forests():
    nested = comment("parent", replies=listing([comment("one"), comment("two")]))
    initial = fetch_post(FakeSession([post_response([nested])]), "post", comment_limit=2)
    assert initial.stop_reason == "comment_limit"
    assert [reply.id for reply in initial.comments[0].replies] == ["one"]
    assert initial.comments[0].more_count == 1

    parent = comment("parent", replies=listing([more("t1_parent", count=3)]))
    subtree = [
        listing([post("post")]),
        listing(
            [comment("parent", replies=listing([comment("one"), comment("two"), comment("three")]))]
        ),
    ]
    expanded = fetch_post(
        FakeSession([post_response([parent]), subtree]), "post", comment_limit=2, max_requests=3
    )
    assert expanded.stop_reason == "comment_limit"
    assert [reply.id for reply in expanded.comments[0].replies] == ["one"]
    assert expanded.comments[0].more_count == 2


def test_post_reports_a_permalink_subtree_that_makes_no_progress_as_incomplete():
    # Measured against Reddit 2026-07-26: some deep branches answer their own
    # permalink with exactly what is already visible, so the more node never
    # clears.  That is a dead end in one thread, not response drift, and reporting
    # it as drift sent the caller into a pointless doctor / setup --force cycle.
    # The branch is abandoned once, and the tree is reported as incomplete.
    parent = comment("parent", replies=listing([more("t1_parent")]))
    repeated = [
        listing([post("post")]),
        listing([comment("parent", replies=listing([more("t1_parent")]))]),
    ]
    session = FakeSession([post_response([parent]), repeated])

    result = fetch_post(session, "post", comment_limit=10, max_requests=10)

    assert result.stop_reason == "depth_capped"
    assert [item.id for item in result.comments] == ["parent"]
    assert session.paths == [
        "/comments/post.json?limit=10&sort=confidence",
        "/r/python/comments/post/_/parent.json?limit=9",
    ]


def test_date_bounded_listing_rejects_undated_records():
    undated = post("undated")
    del undated["data"]["created_utc"]

    with pytest.raises(EnvelopeParseError, match="missing created_at"):
        fetch_subreddit(FakeSession([listing([undated])]), "python", since=datetime.now(UTC))


@pytest.mark.parametrize(
    ("operation", "args", "kwargs"),
    [
        (fetch_subreddit, (FakeSession([]), "python"), {"name": "python"}),
        (fetch_subreddit, (FakeSession([]), "python"), {"include_raw": True}),
        (fetch_user, (FakeSession([]), "person"), {"activity_type": "comments"}),
        (fetch_user, (FakeSession([]), "person"), {"name": "person"}),
        (fetch_user, (FakeSession([]), "person"), {"include_raw": True}),
        (search, (FakeSession([]), "python"), {"include_raw": True}),
        (find_subreddits, (FakeSession([]), "python"), {"include_raw": True}),
        (fetch_subreddit_info, (FakeSession([]), "python"), {"name": "python"}),
        (fetch_subreddit_info, (FakeSession([]), "python"), {"include_raw": True}),
        (fetch_post, (FakeSession([]), "post"), {"include_raw": True}),
        (find_subreddits, (FakeSession([]), "python"), {"since": datetime.now(UTC)}),
        (find_subreddits, (FakeSession([]), "python"), {"until": datetime.now(UTC)}),
        (fetch_subreddit_info, (FakeSession([]), "python"), {"limit": 1}),
        (fetch_subreddit_info, (FakeSession([]), "python"), {"since": datetime.now(UTC)}),
        (fetch_subreddit_info, (FakeSession([]), "python"), {"until": datetime.now(UTC)}),
        (fetch_post, (FakeSession([]), "post"), {"identifier": "post"}),
        (fetch_post, (FakeSession([]), "post"), {"limit": 1}),
        (fetch_post, (FakeSession([]), "post"), {"since": datetime.now(UTC)}),
        (fetch_post, (FakeSession([]), "post"), {"until": datetime.now(UTC)}),
    ],
)
def test_retrieval_rejects_undocumented_keywords(operation, args, kwargs):
    with pytest.raises(TypeError):
        operation(*args, **kwargs)
