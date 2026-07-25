import pytest

from agentic_reddit.endpoints import (
    about_path,
    comment_subtree_path,
    post_path,
    search_path,
    subreddit_path,
    subreddits_search_path,
    user_path,
)
from agentic_reddit.errors import InvalidIdentifierError


def test_subreddit_path_includes_pagination_and_time_in_stable_order():
    assert (
        subreddit_path("r/python", sort="top", limit=25, after="t3_abc", count=25, time="week")
        == "/r/python/top.json?limit=25&after=t3_abc&count=25&t=week"
    )


def test_post_and_comment_subtree_paths():
    assert post_path("python", "t3_abc123", limit=50, depth=3, sort="top") == (
        "/r/python/comments/abc123.json?limit=50&depth=3&sort=top"
    )
    assert comment_subtree_path("python", "abc123", "def456", limit=100, depth=5) == (
        "/r/python/comments/abc123/_/def456.json?limit=100&depth=5"
    )
    assert "/api/morechildren" not in comment_subtree_path("python", "abc123", "def456")


def test_user_path_includes_sort_time_and_cursor():
    assert user_path(
        "u/spez", listing_type="submitted", sort="top", time="year", after="t3_a", count=10
    ) == ("/user/spez/submitted.json?sort=top&t=year&after=t3_a&count=10")


def test_search_paths_encode_deterministically():
    assert search_path(
        "c++ & python", sort="new", time="week", type="user", after="t2_a", count=2
    ) == ("/search.json?q=c%2B%2B+%26+python&sort=new&t=week&type=user&after=t2_a&count=2")
    assert search_path("async io", subreddit="r/python", sort="new") == (
        "/r/python/search.json?q=async+io&restrict_sr=1&sort=new"
    )
    assert (
        subreddits_search_path("data science", after="t5_data", count=3, limit=3)
        == "/subreddits/search.json?q=data+science&after=t5_data&count=3&limit=3"
    )
    assert about_path("https://sh.reddit.com/r/python/") == "/r/python/about.json"


def test_restricted_search_requires_link_type():
    with pytest.raises(InvalidIdentifierError):
        search_path("python", subreddit="python", type="user")
