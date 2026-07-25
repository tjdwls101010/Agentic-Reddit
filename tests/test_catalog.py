"""Parser-derived catalog contract tests."""

from __future__ import annotations

from agentic_reddit import cli

_READ_OUTPUTS = {
    "subreddit": "Post",
    "post": "Post | Comment",
    "comment": "Post | Comment",
    "user": "Post | Comment",
    "search": "Post | Subreddit | User",
    "subreddits": "Subreddit",
    "subreddit-info": "Subreddit",
    "user-info": "User",
    "related": "Post",
}


def test_catalog_covers_every_handler_and_declares_read_outputs() -> None:
    catalog = cli.build_catalog()
    commands = {command["name"]: command for command in catalog["commands"]}

    assert set(commands) == set(cli._HANDLERS)
    assert {name: commands[name]["output"] for name in _READ_OUTPUTS} == _READ_OUTPUTS
    assert {name: commands[name]["output"] for name in commands if name not in _READ_OUTPUTS} == {
        "setup": None,
        "status": None,
        "doctor": None,
        "catalog": None,
        "schema": None,
    }


def test_catalog_arguments_preserve_parser_contract() -> None:
    catalog = cli.build_catalog()
    commands = {command["name"]: command for command in catalog["commands"]}
    subreddit = {argument["name"]: argument for argument in commands["subreddit"]["arguments"]}
    post = {argument["name"]: argument for argument in commands["post"]["arguments"]}
    user = {argument["name"]: argument for argument in commands["user"]["arguments"]}
    search = {argument["name"]: argument for argument in commands["search"]["arguments"]}

    assert subreddit["sort"]["choices"] == [
        "hot",
        "new",
        "top",
        "rising",
        "controversial",
    ]
    assert subreddit["sort"]["default"] == "hot"
    assert subreddit["time"]["choices"] == ["hour", "day", "week", "month", "year", "all"]
    assert subreddit["time"]["default"] == "day"
    assert post["comment_sort"]["choices"] == [
        "confidence",
        "top",
        "best",
        "new",
        "controversial",
        "old",
        "qa",
    ]
    assert post["comment_limit"]["default"] == 500
    assert user["type"]["choices"] == ["overview", "submitted", "comments", "top"]
    assert user["type"]["default"] == "overview"
    assert user["sort"]["choices"] == ["new", "hot", "top", "controversial"]
    assert user["time"]["choices"] == ["hour", "day", "week", "month", "year", "all"]
    assert search["type"]["choices"] == ["link", "sr", "user"]
    assert search["type"]["default"] == "link"
    assert search["sort"]["choices"] == ["relevance", "hot", "top", "new", "comments"]
    assert search["time"]["choices"] == ["hour", "day", "week", "month", "year", "all"]
    assert catalog["exit_codes"] == {
        str(code): text for code, text in cli.errors.EXIT_CODES.items()
    }
    assert catalog["output_schema"] == "agentic-reddit schema --json"


def test_catalog_matches_handler_capabilities_and_help() -> None:
    catalog = cli.build_catalog()
    commands = {command["name"]: command for command in catalog["commands"]}
    arguments = {
        name: {argument["name"] for argument in command["arguments"]}
        for name, command in commands.items()
    }

    assert {"limit", "since", "until"} <= arguments["subreddit"]
    assert {"limit", "since", "until"} <= arguments["user"]
    assert {"limit", "since", "until"} <= arguments["search"]
    assert "limit" in arguments["subreddits"]
    assert {"since", "until"}.isdisjoint(arguments["subreddits"])
    assert {"limit", "since", "until"}.isdisjoint(arguments["post"])
    assert {"limit", "since", "until"}.isdisjoint(arguments["subreddit-info"])
    assert {"depth", "comment_limit"} <= arguments["post"]
    assert all(
        isinstance(argument["help"], str) and argument["help"].strip()
        for command in catalog["commands"]
        for argument in command["arguments"]
    )
