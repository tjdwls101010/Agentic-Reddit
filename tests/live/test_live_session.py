"""Opt-in, bounded browser transport smoke tests."""

from __future__ import annotations

import os
from collections.abc import Mapping

import pytest

from agentic_reddit.session import BrowserSession

pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTIC_REDDIT_LIVE") != "1",
    reason="set AGENTIC_REDDIT_LIVE=1 to run live Reddit browser checks",
)


def _assert_listing(body: object) -> None:
    assert isinstance(body, Mapping)
    assert body.get("kind") == "Listing"
    assert isinstance(body.get("data"), Mapping)


def test_live_listing_surfaces(tmp_path):
    with BrowserSession(
        profile_dir_override=tmp_path,
        warm_timeout_seconds=30,
    ) as browser:
        browser.warm()
        subreddit = browser.get_json("/r/python/hot.json?limit=1")
        user = browser.get_json("/user/spez/overview.json?limit=1")
        link_search = browser.get_json("/search.json?q=python&type=link&limit=1")

    _assert_listing(subreddit)
    _assert_listing(user)
    _assert_listing(link_search)


def test_live_post_and_subreddit_surfaces(tmp_path):
    with BrowserSession(
        profile_dir_override=tmp_path,
        warm_timeout_seconds=30,
    ) as browser:
        browser.warm()
        post = browser.get_json("/r/reddit/comments/12qwagm.json?limit=1&depth=0")
        subreddit_search = browser.get_json("/subreddits/search.json?q=python&limit=1")
        about = browser.get_json("/r/python/about.json")

    assert isinstance(post, list)
    assert len(post) == 2
    for listing in post:
        _assert_listing(listing)
    _assert_listing(subreddit_search)
    assert isinstance(about, Mapping)
    assert about.get("kind") == "t5"
    assert isinstance(about.get("data"), Mapping)
