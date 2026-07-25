import pytest

from agentic_reddit.errors import InvalidIdentifierError
from agentic_reddit.identity import (
    normalize_comment_identifier,
    normalize_permalink,
    normalize_post_identifier,
    normalize_subreddit_group,
    normalize_subreddit_identifier,
    normalize_user_identifier,
    permalink_identifiers,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("python", ("subreddit", "python")),
        ("r/python", ("subreddit", "python")),
        ("/r/python", ("subreddit", "python")),
        ("https://old.reddit.com/r/python/", ("subreddit", "python")),
    ],
)
def test_normalize_subreddit_forms(raw, expected):
    assert normalize_subreddit_identifier(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abc", ("subreddits", "abc")),
        ("abc+Def", ("subreddits", "abc+Def")),
        ("r/abc+Def", ("subreddits", "abc+Def")),
        ("https://old.reddit.com/r/abc+Def/", ("subreddits", "abc+Def")),
    ],
)
def test_normalize_subreddit_group(raw, expected):
    assert normalize_subreddit_group(raw) == expected


def test_normalize_subreddit_group_rejects_invalid_groups():
    with pytest.raises(InvalidIdentifierError, match="too many subreddits"):
        normalize_subreddit_group("+".join(["abc"] * 11))
    with pytest.raises(InvalidIdentifierError, match="invalid subreddit name"):
        normalize_subreddit_group("abc++def")
    with pytest.raises(InvalidIdentifierError, match="invalid subreddit name"):
        normalize_subreddit_identifier("abc+def")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("spez", ("user", "spez")),
        ("u/spez", ("user", "spez")),
        ("/user/spez", ("user", "spez")),
        ("https://np.reddit.com/user/spez/", ("user", "spez")),
    ],
)
def test_normalize_user_forms(raw, expected):
    assert normalize_user_identifier(raw) == expected


def test_normalize_post_and_comment_permalinks():
    post_url = "https://www.reddit.com/r/python/comments/abc123/a_title/"
    comment_url = f"{post_url}def456/"

    assert normalize_post_identifier("t3_ABC123") == ("post", "abc123")
    assert normalize_post_identifier(post_url) == ("post", "abc123")
    assert normalize_comment_identifier(comment_url) == ("comment", "def456")
    assert normalize_permalink(comment_url) == ("comment", "def456")
    assert permalink_identifiers(comment_url) == ("python", "abc123", "def456")


@pytest.mark.parametrize(
    "raw",
    [
        "https://reddit.com.evil.example/r/python",
        "https://evil.example/r/python",
        "ftp://www.reddit.com/r/python",
        "https://www.reddit.com/r/no-dashes",
        "https://www.reddit.com/r/python/comments/not-an-id!/title",
    ],
)
def test_rejects_foreign_hosts_and_malformed_identifiers(raw):
    with pytest.raises(InvalidIdentifierError):
        normalize_subreddit_identifier(raw)
